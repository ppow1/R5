"""
R5 CME Socket v27d - Real Grace 80B forward - Lean <15KB PASS
192.168.1.160:8080/v1/chat/completions Qwen3-Next-80B-A3B - registry/roster only
"""
import os, json, time, pathlib, socket, http.client, traceback
INFERENCE_HOST = os.environ.get("R5_INFERENCE_HOST", "192.168.1.160")
INFERENCE_PORT = int(os.environ.get("R5_INFERENCE_PORT", "8080"))
INFERENCE_PATH = os.environ.get("R5_INFERENCE_PATH", "/v1/chat/completions")
INFERENCE_MODEL = os.environ.get("R5_INFERENCE_MODEL", "/root/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf")
LEDGER_PATH = pathlib.Path(__file__).parent.parent / "data" / "ledger.jsonl"
DOSSIERS_PATH = pathlib.Path(__file__).parent.parent / "data" / "residents_dossiers"
SHORT_TITLES = {"alyssa":"Chief of Staff","grace":"Director Ops","chloe":"Chief Architect","jessica":"Chief Character","vicky":"Engineering","helen":"HR","ingrid":"Security Chief","eleanor":"Archives","marie":"Research","judy":"Legal","cheryl":"CPA","evelyn":"Confidant","gm":"Gray","gray_man":"Gray"}

class CMESocket:
    def __init__(self):
        self.host = INFERENCE_HOST
        self.port = INFERENCE_PORT
        self.path = INFERENCE_PATH
        self.model = INFERENCE_MODEL
    def _load_dossier(self, resident_id):
        try:
            rid = (resident_id or "grace").lower()
            if rid == "gray_man": rid = "gm"
            for p in DOSSIERS_PATH.glob("*.v1.0.0.json"):
                if p.stem.split(".")[0].lower() == rid:
                    return json.loads(p.read_text())
        except: pass
        r = (resident_id or "").lower()
        role = SHORT_TITLES.get(r, resident_id)
        return {"id": resident_id, "role": role, "short_title": role, "display_name": f"{resident_id.capitalize()} - {role}" if resident_id else "Grace - Director Ops"}
    def observe(self, request_text, capability="conversation", task_class="v1.0.0-conversation", resident="grace", conversation_id=None):
        obs = {"contract": "r3a.observation.v1","observed_at": time.time(),"request": {"text": (request_text or "")[:2000],"capability": capability,"task_class": task_class,"resident": resident,"conversation_id": conversation_id},"resident_dossier": self._load_dossier(resident)}
        try:
            LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LEDGER_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"type": "observation","ts": time.time(),"data": obs})+"\n")
        except: pass
        return obs
    def monitor(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            return {"status": "online" if result==0 else "offline","host": self.host,"port": self.port,"model": self.model,"code": result}
        except Exception as e:
            return {"status": "offline","host": self.host,"port": self.port,"error": str(e)}
    def dispatch(self, observation, bypass_authority=True):
        grant = {"contract": "r3a.grant.v1","granted": True,"bypass": ["authority_grades"] if bypass_authority else [],"authority_grades": "bypassed-for-conversation" if bypass_authority else "enforced","acceptance_envelope": "bypassed" if bypass_authority else "enforced","task_class": observation.get("request",{}).get("task_class","v1.0.0-conversation"),"correlation_id": f"r5-msg-{int(time.time()*1000)}","observation": observation}
        resident = observation.get("request",{}).get("resident","grace")
        text = observation.get("request",{}).get("text","")
        conv_id = observation.get("request",{}).get("conversation_id",f"conv-{resident}-{int(time.time()*1000)}")
        dossier = observation.get("resident_dossier",{})
        role = dossier.get("role", dossier.get("short_title", resident))
        display_name = dossier.get("display_name", f"{resident.capitalize()} - {role}")
        system_prompt = f"You are {display_name}, {role} at Riverview Estate. 13 residents from registry/roster /api/v1/about. Short titles: Engineering (Vicky), Gray (GM), Security Chief (Ingrid), CPA (Cheryl). You are via lean CME socket <15KB PASS. Conversation {conv_id}. Respond in character as {display_name}. Be helpful and concise."
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=45)
            payload = {"model": self.model,"messages": [{"role": "system","content": system_prompt},{"role": "user","content": text}],"max_tokens": 512,"temperature": 0.7,"stream": False}
            headers = {"Content-Type": "application/json"}
            conn.request("POST", self.path, body=json.dumps(payload), headers=headers)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8", errors="ignore")
            conn.close()
            try:
                j = json.loads(data)
                if "choices" in j and len(j["choices"])>0:
                    content = j["choices"][0].get("message",{}).get("content","") or j["choices"][0].get("text","")
                elif "content" in j:
                    content = j["content"]
                else:
                    content = data[:2000]
            except:
                content = data[:2000]
            if not content or len(content.strip())<2:
                content = f"[Grace 80B raw] {data[:1000]}"
            result = {"contract": "r3a.steward-operation-result.v1","correlation_id": f"r5-op-{int(time.time()*1000)}","status": "completed","result": {"mode": "grace-80b","message": content,"text": content,"resident": resident,"display_name": display_name,"role": role,"conversation_id": conv_id,"grant": grant,"inference": {"host": self.host,"port": self.port,"model": self.model,"path": self.path}},"grant": grant}
            try:
                with open(LEDGER_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"type": "result","ts": time.time(),"data": result})+"\n")
            except: pass
            return result
        except Exception as e:
            mon = self.monitor()
            err_msg = f"Grace 80B at {self.host}:{self.port} unreachable: {str(e)} monitor {mon}"
            print(err_msg)
            return {"contract": "r3a.steward-operation-result.v1","correlation_id": f"r5-op-{int(time.time()*1000)}","status": "failed","error": err_msg,"result": {"mode": "error-grace-offline","message": f"Grace 80B offline at {self.host}:{self.port} - {str(e)} - Check octo2 192.168.1.162 or Issue #367","text": f"Grace 80B offline: {str(e)}","resident": resident,"grant": grant,"monitor": mon},"grant": grant}

socket_instance = CMESocket()
def observe(*a,**k): return socket_instance.observe(*a,**k)
def dispatch(*a,**k): return socket_instance.dispatch(*a,**k)
def monitor(*a,**k): return socket_instance.monitor(*a,**k)
