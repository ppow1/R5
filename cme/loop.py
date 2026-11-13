"""
R5 CME Loop - 10 stages as registry lookups, not hardcoded logic
Waterwheel tile: Observe Understand Plan Decompose Dispatch Monitor Validate Recover Integrate Learn
"""
from .socket import CMESocket

class CMELoop:
    def __init__(self):
        self.socket = CMESocket()
        self.stages = ["Observe","Understand","Plan","Decompose","Dispatch","Monitor","Validate","Recover","Integrate","Learn"]

    def run(self, event: dict, task_class="v1.0.0-conversation"):
        obs = self.socket.observe(event)
        # Understand = registry capability lookup
        # Plan = process_graph from capabilities.json
        # Decompose = task split
        grant = self.socket.dispatch(event, task_class)
        state = self.socket.monitor()
        return {"observation": obs, "grant": grant, "state": state, "stages": self.stages}
