"""
System B - D-Delta - CME Runner - waterwheel
"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from cme.loop import CMELoop
import time, pathlib, os

class DDelta:
    def __init__(self):
        self.name = "System B - D-Delta"
        self.cme = CMELoop()
        self.stages = self.cme.stages

    def run_once(self, event: dict):
        task_class = event.get("task_class","v1.0.0-conversation")
        return self.cme.run(event, task_class)

    def run(self):
        pid_path = pathlib.Path("/tmp/r5-cme.pid")
        try:
            pid_path.unlink()
        except:
            pass
        pid_path.write_text(str(os.getpid()))
        print(f"DDelta PID {os.getpid()} -> {pid_path} spinning: {' -> '.join(self.stages)}")
        while True:
            event = {"type":"heartbeat","task_class":"v1.0.0-conversation"}
            self.run_once(event)
            time.sleep(5)

if __name__ == "__main__":
    p = pathlib.Path("/tmp/r5-cme.pid")
    try:
        p.unlink()
    except:
        pass
    p.write_text(str(os.getpid()))
    print(f"DDelta PID {os.getpid()} written to /tmp/r5-cme.pid")
    DDelta().run()
