"""
System D - Ring Zero - bare metal guardian - Camrui N95 15W always-on
"""
import pathlib, os, time, json
from typing import Dict

REG = pathlib.Path(__file__).parent.parent / "registries" / "resources.json"

class RingZero:
    def __init__(self):
        self.name = "System D - Ring Zero"
        self.status = "online"

    def observe(self) -> Dict:
        return {"storage":"Healthy","compute":"Online","network":"Normal","security":"Normal","cme":"Online","models":"Online","tools":"Online"}

    def run(self):
        pid_path = pathlib.Path("/tmp/r5-ring0.pid")
        try:
            pid_path.unlink()
        except:
            pass
        pid_path.write_text(str(os.getpid()))
        print(f"Ring0 PID {os.getpid()} -> {pid_path}")
        while True:
            self.observe()
            time.sleep(60)

if __name__ == "__main__":
    p = pathlib.Path("/tmp/r5-ring0.pid")
    try:
        p.unlink()
    except:
        pass
    p.write_text(str(os.getpid()))
    print(f"Ring0 start PID {os.getpid()} written to /tmp/r5-ring0.pid")
    RingZero().run()
