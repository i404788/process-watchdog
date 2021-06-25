# process-watchdog
Watched python3 multiprocess.Process tasks, and automatically restarts them if needed

## Usage
```py3
from process_watchdog import ManagedTask, watchdog

class MyTask(ManagedTask):
    require_ping = True # Will also check if the task doesn't get stuck
    
    def task(self):
        ... do some work


# Note, this will block create a new process if you want async operation
watchdog([MyTask])
```
