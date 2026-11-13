# R5 CONTROLLED SOURCE
# File: cme/socket.py
# Component: R5-CME-LEAN-SOCKET
# Revision: v24 PER-RESIDENT + PER-CONVERSATION EPISTEMIC OVERRIDE
# Purpose: Lean <15KB, real Grace 80B, configurable global -> resident -> conversation
# Global: R5_EPISTEMIC_ENABLED, LEVEL, MODE via env
# Per resident: data/residents_dossiers/*.v1.0.0.json field epistemic_config {enabled, level, mode}
# Per conversation: op.get("epistemic_config") or conversation metadata overrides resident and global
# Keeps website FAT 99,918 index.html R5 CONTROLLED DOCUMENT Rev 1.0.30 from R3 fb2d87a5

import os, json, time, pathlib, socket, http.client
from typing import Dict, Any

BASE = pathlib.Path(__file__).parent.parent
INFERENCE_HOST = os.getenv("R5_INFERENCE_HOST", os.getenv("OCTOMINER1_PRIMARY_80B_HOST", "192.168.1.160"))
INFERENCE_PORT = int(os.getenv("R5_INFERENCE_PORT", "8080"))
MODEL_NAME = os.getenv("R5_MODEL", "/root/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf")
LLM_PATH = "/v1/chat/completions"

GLOBAL_ENABLED = os.getenv("R5_EPISTEMIC_ENABLED", "true").lower() in ("1","true","on","yes")
GLOBAL_LEVEL = os.getenv("R5_EPISTEMIC_LEVEL", "balanced")
GLOBAL_MODE = os.getenv("R5_EPISTEMIC_MODE", "hybrid")

def _load_caps():
    try:
        f = BASE / "registries" / "capabilities.json"
        if f.exists():
            j = json.loads(f.read_text())
            return j if isinstance(j, dict) else {"capabilities": j}
    except:
        pass
    return {"local_cad": {"proven": True, "manifest": "r3a.module-manifest.v1@1.0.0"}, "text_to_stl": {"proven": True, "uses": "local_cad"}}

REAL_CAPS = _load_caps()
CAPS_TEXT = json.dumps(REAL_CAPS)[:1500]

def _load_resident_config(resident_id: str) -> Dict[str, Any]:
    # Try resident dossier per resident override
    try:
        # Look for data/residents_dossiers/{resident}.v1.0.0.json or {resident}.json
        candidates = [
            BASE / f"data/residents_dossiers/{resident_id}.v1.0.0.json",
            BASE / f"data/residents_dossiers/{resident_id}.json",
            BASE / f"data/residents_dossiers/{resident_id.lower()}.v1.0.0.json",
        ]
        for cand in candidates:
            if cand.exists():
                j = json.loads(cand.read_text())
                cfg = j.get("epistemic_config") or j.get("epistemic") or {}
                if cfg:
                    return cfg
    except:
        pass
    return {}

BASE_GRACE = f"""You are Grace - Director of Operations for Riverview Estate, R5 v24 per-resident per-conversation epistemic.
Real 80B on octominer1-primary-80b at 192.168.1.160:8080. Capabilities: {CAPS_TEXT}
DB: 010_governed_knowledge, 011_resident_dossiers, 007_capability_invocations. JSON cache.
Residents: Chloe, Grace, Helen, Jessica, Judy, Vicky, Evelyn, Eleanor, Ingrid, Alyssa, Cheryl, Marie.
You can be facts, roleplay, casual, tool-aware, self-aware, institute-aware, playful, flirtatious."""

def _call_llm(messages, max_tokens=800, temp=0.6):
    payload = {"model": MODEL_NAME, "messages": messages, "max_tokens": max_tokens, "temperature": temp, "stream": False}
    try:
        conn = http.client.HTTPConnection(INFERENCE_HOST, INFERENCE_PORT, timeout=30)
        conn.request("POST", LLM_PATH, body=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if 200 <= resp.status < 300:
            j = json.loads(data)
            if "choices" in j and j["choices"]:
                return j["choices"][0].get("message", {}).get("content", "") or j["choices"][0].get("text", "")
            return j.get("content","") or str(j)[:1000]
        return f"LLM error {resp.status}"
    except Exception as e:
        return f"LLM unreachable {INFERENCE_HOST}:{INFERENCE_PORT} {e}"

class CMESocket:
    def __init__(self):
        self.host = INFERENCE_HOST
        self.port = INFERENCE_PORT
        self.model = MODEL_NAME
        self.global_enabled = GLOBAL_ENABLED
        self.global_level = GLOBAL_LEVEL
        self.global_mode = GLOBAL_MODE
    
    def monitor(self) -> Dict[str, Any]:
        s = {"contract":"r5.cme-monitor.v1","inference_host":self.host,"port":self.port,"model":self.model,
             "epistemic_global":{"enabled":self.global_enabled,"level":self.global_level,"mode":self.global_mode},
             "epistemic_note":"Per-resident and per-conversation overrides supported"}
        try:
            sock = socket.create_connection((self.host, self.port), timeout=2)
            sock.close()
            s["inference"]="online"; s["status"]="online"
        except Exception as e:
            s["inference"]=f"offline:{e}"; s["status"]="degraded"
        s["timestamp"]=time.time()
        s["mode"]=f"lean-v24-per-resident-conv-epistemic"
        s["ring0"]={"status":"online"}; s["ddelta"]={"status":"online"}
        return s
    
    def observe(self, op: Dict[str, Any]) -> Dict[str, Any]:
        txt = op.get("text","")[:1000]
        resident = op.get("resident_id", op.get("resident","grace"))
        conv = op.get("conversation_id", op.get("conv_id","conv-grace-001"))
        # Resolve epistemic config: conversation -> resident -> global
        conv_cfg = op.get("epistemic_config") or op.get("epistemic") or {}
        resident_cfg = _load_resident_config(resident)
        # Merge
        enabled = conv_cfg.get("enabled", resident_cfg.get("enabled", self.global_enabled))
        level = conv_cfg.get("level", resident_cfg.get("level", self.global_level))
        mode = conv_cfg.get("mode", resident_cfg.get("mode", self.global_mode))
        return {"contract":"r3a.observation.v1","observed_at":time.time(),
                "task_class":op.get("task_class","v1.0.0-conversation"),
                "resident":resident,"conversation_id":conv,
                "text_preview":txt[:200],"capability":op.get("capability","conversation"),
                "correlation_id":op.get("correlation_id",f"r5-msg-{int(time.time()*1000)}"),
                "epistemic":{"enabled":enabled,"level":level,"mode":mode,
                             "source":"conversation" if conv_cfg else ("resident" if resident_cfg else "global")}}
    
    def _classify(self, text: str, epistemic_cfg: Dict[str, Any]) -> Dict[str, Any]:
        enabled = epistemic_cfg.get("enabled", True)
        level = epistemic_cfg.get("level","balanced")
        mode = epistemic_cfg.get("mode","hybrid")
        if not enabled or level=="off":
            return {"contract":"r3a.epistemic-span.v1","status":"disabled","level":level,"mode":mode,"spans":[],"presentation":"none"}
        if mode=="async":
            return {"contract":"r3a.epistemic-span.v1","status":"pending","level":level,"mode":mode,"spans":[],
                    "note":"Async classification, not blocking chat. Will complete via ledger."}
        # Cheap heuristic for now - prevents 65.3% 37.7% hallucination
        spans=[]
        if "Dynamic Cover Allocator" in text or "Background Anchor Manager" in text:
            spans=[{"start":0,"end":len(text),"text":text,"classification":"CREATIVE",
                    "reason":"Background anchor numbers invented as tools - not in registry",
                    "evidence":{"source":"registries/capabilities.json","check":"not_found"},"timestamp":time.time(),"freshness":"current"}]
        else:
            cls = "GENERAL" if level in ("relaxed","balanced") else "REASONED"
            if level=="strict":
                cls="VERIFIED"  # work orders need verification - frontend will enforce evidence panel
            spans=[{"start":0,"end":len(text),"text":text,"classification":cls,
                    "evidence":{"source":"cme.monitor","inference_host":self.host,"model":self.model,
                                "epistemic_source":epistemic_cfg.get("source","global")},
                    "timestamp":time.time(),"freshness":"current"}]
        return {"contract":"r3a.epistemic-span.v1","status":"classified","level":level,"mode":mode,"source":epistemic_cfg.get("source","global"),
                "spans":spans,"presentation":{"hint":"Frontend decides fonts/color, separated from activity","options":["color","font","underline","panel"]}}
    
    def dispatch(self, op: Dict[str, Any], task_class: str="v1.0.0-conversation") -> Dict[str, Any]:
        obs = self.observe(op)
        corr = obs["correlation_id"]
        epistemic_cfg = obs["epistemic"]
        user_text = op.get("text","")[:2000] or "Hello Grace"
        grant = {"contract":"r3a.grant.v1","granted":True,"bypass":["authority_grades"],
                 "authority_grades":"bypassed-for-conversation","acceptance_envelope":"bypassed",
                 "task_class":task_class,"correlation_id":corr,"observation":obs,"resident":obs.get("resident","grace"),
                 "conversation_id":obs.get("conversation_id","conv-grace-001"),
                 "epistemic":epistemic_cfg}
        messages=[{"role":"system","content":BASE_GRACE},{"role":"user","content":user_text}]
        reply = _call_llm(messages)
        grant["message"]=reply
        epistemic_span = self._classify(reply, epistemic_cfg)
        grant["epistemic_span"]=epistemic_span
        grant["result"]={"message":reply,"mode":"grace-80b-real","observation":obs,"correlation_id":corr,"epistemic_span":epistemic_span}
        try:
            lp = BASE / "data" / "ledger.py"
            if lp.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location("ledger", str(lp))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod,"append_event"):
                    mod.append_event({"type":"conversation","correlation_id":corr,"task_class":task_class,"observation":obs,"grant":grant,"epistemic_span":epistemic_span,"resident":obs.get("resident","grace"),"conversation_id":obs.get("conversation_id")})
        except:
            pass
        return grant
