import multiprocessing
import atexit
import time
import inspect
from typing import Dict, List, Callable, Type
from logging import getLogger

class AutoInit(type):
    def __new__(meta, classname, supers, classdict):
        def wrapper(old_init):
            def autoinit(self, *args, **kwargs):
                formals = inspect.getfullargspec(old_init).args
                for name, value in list(zip(formals[1:], args)) + list(kwargs.items()):
                    setattr(self, name, value)
            return autoinit
        classdict['__init__'] = wrapper(classdict['__init__'])
        return type.__new__(meta, classname, supers, classdict)


class ManagedTask(metaclass=AutoInit):
    require_ping = False

    def __init__(self, pipe: multiprocessing.Pipe, *args, **kwargs):
        pass

    def _run(self):
        while True: 
            self.task()
            if require_ping:
                pipe.send(':alive')

    def task(self):
        raise NotImplementedError("ManagedTask has no task defined")

def run_task(task: Type[ManagedTask], pipe: multiprocessing.Pipe):
    task_instance = task(pipe)
    task_instance._run()

def watchdog(tasks: List[Type[ManagedTask]], watchdog_timeout=300, logger=None):
    # Run all tasks & make sure they stay online
    logger = logger or getLogger('tasks')
    tasks = dict((f.__name__, {'task': f}) for f in tasks) 

    # Handle exit without lingering threads, very important
    @atexit.register
    def exit_handler():
        print("Terminating tasks...")
        for name, taskv in tasks.items():
            if taskv.get('process'):
                print(f"Terminating {name} ({taskv['process'].pid})")
                taskv['process'].terminate()

    while True:
        for name, taskv in tasks.items():
            if taskv.get('process'):
                # Task already exists, just check condition
                process = taskv['process']
                if not process.is_alive() or process.exitcode != None:
                    # Task was terminated at some point, restart+log
                    l = logger.getChild(name)
                    l.warn(f"Process {process.pid} ({name}, errc: {process.exitcode}) was terminated, restarting...")
                    # Will restart in next run
                    del tasks['process']
                elif taskv.require_ping:
                    # Task is alive, lets check for pings (if enabled)
                    pipe = taskv['pipe']
                    while pipe.poll(0.1):
                        obj = pipe.recv()
                        if obj == ':alive':
                            taskv['last_seen'] = time.time()

                    # Possible zombie task, no ping for longer than our timeout
                    if time.time() - taskv['last_seen'] > watchdog_timeout:
                        taskv['process'].terminate()
                        del tasks['process']
            
            else:
                # Create new task
                logger.info(f"Starting task {name}")
                a, b = multiprocessing.Pipe()
                p = multiprocessing.Process(target=run_task, args=(taskv['task'], b), name=name)
                taskv = {**taskv, 'process': p, 'pipe': a, 'last_seen': time.time()}
                p.start()

        time.sleep(5)
