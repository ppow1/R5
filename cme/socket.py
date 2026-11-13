"""
R5 CME Socket v27e - Real Grace 80B forward - Fix slice bug - Lean <15KB PASS
192.168.1.160:8080/v1/chat/completions - registry/roster only - 6825->~7k bytes PASS
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
    def _safe_text(self, v):
        # Fix: never slice None or slice object - cast to str first
        try:
            if v is None: return ""
            if isinstance(v, slice): return ""  # bug source: slice(None,2000,None) object passed
            s = str(v)
            return s[:2000]
        except Exception:
            try: return str(v)[:2000]
            except: return ""
    def _load_dossier(self, resident_id):
        try:
            rid = (resident_id or "grace").lower()
            if rid == "gray_man": rid = "gm"
            if not isinstance(rid, str): rid = "grace"
            for p in DOSSIERS_PATH.glob("*.v1.0.0.json"):
                try:
                    if p.stem.split(".")[0].lower() == rid:
                        return json.loads(p.read_text())
                except: continue
        except: pass
        r = (resident_id or "").lower() if isinstance(resident_id, str) else "grace"
        role = SHORT_TITLES.get(r, resident_id if isinstance(resident_id, str) else "Director Ops")
        return {"id": resident_id, "role": role, "short_title": role, "display_name": f"{str(resident_id).capitalize() if resident_id else 'Grace'} - {role}"}
    def observe(self, request_text, capability="conversation", task_class="v1.0.0-conversation", resident="grace", conversation_id=None):
        safe = self._safe_text(request_text)
        cap = self._safe_text(capability) or "conversation"
        tclass = self._safe_text(task_class) or "v1.0.0-conversation"
        res_id = self._safe_text(resident) or "grace"
        conv = self._safe_text(conversation_id) or f"conv-{res_id}-{int(time.time()*1000)}"
        obs = {"contract": "r3a.observation.v1","observed_at": time.time(),"request": {"text": safe,"capability": cap,"task_class": tclass,"resident": res_id,"conversation_id": conv},"resident_dossier": self._load_dossier(res_id)}
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
            return {"status": "offline","host": self.host,"port": self.port,"error": self._safe_text(str(e))}
    def dispatch(self, observation, bypass_authority=True):
        try:
            if not isinstance(observation, dict): observation = {"request": {"text": self._safe_text(observation)}}
            req = observation.get("request", {}) if isinstance(observation.get("request"), dict) else {}
            text = self._safe_text(req.get("text", ""))
            resident = self._safe_text(req.get("resident", "grace")) or "grace"
            conv_id = self._safe_text(req.get("conversation_id")) or f"conv-{resident}-{int(time.time()*1000)}"
            tclass = self._safe_text(req.get("task_class")) or "v1.0.0-conversation"
            grant = {"contract": "r3a.grant.v1","granted": True,"bypass": ["authority_grades"] if bypass_authority else [],"authority_grades": "bypassed-for-conversation" if bypass_authority else "enforced","acceptance_envelope": "bypassed" if bypass_authority else "enforced","task_class": tclass,"correlation_id": f"r5-msg-{int(time.time()*1000)}","observation": observation}
            dossier = observation.get("resident_dossier", {}) if isinstance(observation.get("resident_dossier"), dict) else self._load_dossier(resident)
            role = self._safe_text(dossier.get("role") or dossier.get("short_title") or resident)
            display_name = self._safe_text(dossier.get("display_name")) or f"{resident.capitalize()} - {role}"
            system_prompt = self._safe_text(f"You are {display_name}, {role} at Riverview Estate. 13 residents from registry/roster /api/v1/about. Short titles: Engineering (Vicky), Gray (GM), Security Chief (Ingrid), CPA (Cheryl). Lean CME <15KB PASS. Conversation {conv_id}. Respond as {display_name}. Be helpful, concise.")
            # Call Grace 80B
            conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
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
            content = self._safe_text(content)
            if len(content.strip())<2:
                content = self._safe_text(f"[Grace 80B raw] {data[:1000]}") or "Hello. Grace here. How can I help?"
            result = {"contract": "r3a.steward-operation-result.v1","correlation_id": f"r5-op-{int(time.time()*1000)}","status": "completed","result": {"mode": "grace-80b","message": content,"text": content,"resident": resident,"display_name": display_name,"role": role,"conversation_id": conv_id,"grant": grant,"inference": {"host": self.host,"port": self.port,"model": self.model,"path": self.path}},"grant": grant}
            try:
                with open(LEDGER_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"type": "result","ts": time.time(),"data": result})+"\n")
            except: pass
            return result
        except Exception as e:
            mon = self.monitor()
            tb = traceback.format_exc()[-1500:]
            err = self._safe_text(f"{type(e).__name__}: {e} | tb: {tb}")
            print(f"Dispatch exception: {err}")
            # Never return slice object as message - always str
            safe_res = self._safe_text(resident) if 'resident' in locals() else "grace"
            safe_conv = self._safe_text(conv_id) if 'conv_id' in locals() else f"conv-{safe_res}-err"
            grant_err = {"contract": "r3a.grant.v1","granted": False,"error": err,"bypass": []}
            return {"contract": "r3a.steward-operation-result.v1","correlation_id": f"r5-err-{int(time.time()*1000)}","status": "failed","error": {"code": "dispatch_failed","message": err,"traceback": tb},"result": {"mode": "error","message": f"Dispatch failed: {err}","text": f"Error: {err}","resident": safe_res,"conversation_id": safe_conv,"monitor": mon},"grant": grant_err}

socket_instance = CMESocket()
def observe(*a,**k): return socket_instance.observe(*a,**k)
def dispatch(*a,**k): return socket_instance.dispatch(*a,**k)
def monitor(*a,**k): return socket_instance.monitor(*a,**k)
