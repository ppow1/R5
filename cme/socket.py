"""
R5 CME Socket v35.3 MERGE DRAFT - FOR REVIEW, NOT DEPLOYED
v35.2 + heartbeat noise fix.
- DDelta runs every 5s with event {"type":"heartbeat",
  "task_class":"v1.0.0-conversation"}, no text, no resident work.
  CMELoop calls socket.observe(event) then socket.dispatch(event).
  v35.2 dispatch POSTed that empty heartbeat to the 80B every 5s:
  offline = full ConnectionRefused traceback every 5s;
  online = ~50-94 tokens per heartbeat, slot 3, ~700 tokens
  in context, burning 80B GPU/slot for nothing.
- Fix, in socket only, DDelta/loop unchanged:
  1. observe(): heartbeat with no text returns the observation
     without appending to ledger.jsonl.
  2. dispatch(): heartbeat / empty-text returns a monitor-only
     result, mode grace-80b, tool_mode heartbeat-monitor,
     with monitor + embed status, no POST, no tokens.
  3. dispatch(): for real text, check monitor() first. If
     inference is offline, return local-fallback immediately,
     no POST attempt, no traceback. Real Grace conversations
     with text are unchanged, v35.2 tool loop / time / personality.
- Autonomy is not broken: real work arrives via website invoke
  with text/resident/conversation_id, not via heartbeat.
"""
import os, json, re, time, pathlib, socket, datetime, http.client, traceback
from typing import Dict, Any, List

BASE = pathlib.Path(__file__).parent.parent
HOST = os.getenv("R5_INFERENCE_HOST", "192.168.1.160")
PORT = int(os.getenv("R5_INFERENCE_PORT", "8080"))
PATH = os.getenv("R5_INFERENCE_PATH", "/v1/chat/completions")
MODEL = os.getenv("R5_QWEN_MODEL", os.getenv("R5_INFERENCE_MODEL", "/root/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"))
EMBED_HOST = os.getenv("R5_EMBED_HOST", "192.168.1.160")
EMBED_PORT = int(os.getenv("R5_EMBED_PORT", "8081"))
LEDGER_PATH = BASE / "data" / "ledger.jsonl"
DOSSIERS_PATH = BASE / "data" / "residents_dossiers"
GRACE_SLOT = "slot-1"
VICKY_SLOT = "slot-2"

SLOT_RESERVATION = {
    "slot-1": {"resident": "grace", "pinned": True, "policy": "pinned"},
    "slot-2": {"resident": "vicky", "pinned": True, "policy": "pinned"},
    "slot-3": {"resident": "*", "pinned": False, "policy": "LRU"},
    "slot-4": {"resident": "*", "pinned": False, "policy": "LRU"},
}
CONTENT_ALLOCATION = {
    "grace": {"context_tokens": 12288, "max_text": 8000, "slot": "slot-1", "autonomy": "full"},
    "vicky": {"context_tokens": 10240, "max_text": 6000, "slot": "slot-2", "autonomy": "full"},
    "ingrid": {"context_tokens": 8192, "max_text": 4000, "slot": "slot-3", "autonomy": "full"},
    "cheryl": {"context_tokens": 8192, "max_text": 4000, "slot": "slot-4", "autonomy": "full"},
    "other": {"context_tokens": 8192, "max_text": 4000, "slot": "slot-*", "autonomy": "full"},
}
SHORT_TITLES = {"alyssa": "Chief of Staff", "grace": "Director Ops", "chloe": "Chief Architect", "jessica": "Chief Character", "vicky": "Engineering", "helen": "HR", "ingrid": "Security Chief", "eleanor": "Archives", "marie": "Research", "judy": "Legal", "cheryl": "CPA", "evelyn": "Confidant", "gm": "Gray", "gray_man": "Gray"}

# v31 TOOLS_OPENAI, verbatim tool definitions
TOOLS_OPENAI = [
 {"type": "function", "function": {"name": "get_current_time", "description": "Get current EST time and date. CALL THIS when user asks time/date. Do NOT hallucinate time, CALL tool.", "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}, "required": []}}},
 {"type": "function", "function": {"name": "knowledge_base_search", "description": "Local-first search Riverview knowledge base ledger.jsonl. ALWAYS search this BEFORE answering factual questions.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
 {"type": "function", "function": {"name": "self_knowledge", "description": "Check own dossier 011", "parameters": {"type": "object", "properties": {"resident_id": {"type": "string"}}, "required": []}}},
 {"type": "function", "function": {"name": "world_knowledge", "description": "Search governing ledger 010", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
 {"type": "function", "function": {"name": "generate_work_order", "description": "Create work order", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}}, "required": ["title"]}}},
 {"type": "function", "function": {"name": "generate_image", "description": "Generate image", "parameters": {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}}},
 {"type": "function", "function": {"name": "flag_knowledge_for_review", "description": "Flag knowledge that changed, cite source", "parameters": {"type": "object", "properties": {"old_fact": {"type": "string"}, "new_fact": {"type": "string"}, "source": {"type": "string"}, "citation": {"type": "string"}}, "required": ["old_fact", "new_fact"]}}},
]
TOOL_NAMES = [t["function"]["name"] for t in TOOLS_OPENAI]


def _safe(v, l=8000):
    # v31 / v27e: never slice None or a slice object
    if v is None:
        return ""
    if isinstance(v, slice):
        return ""
    try:
        return str(v)[:l]
    except Exception:
        return ""


def _dossier(rid):
    # v35.1: lean dossier first, then merge rich residents/ file.
    # v35 only tried BASE/data/residents/{rid}.json, which does not exist.
    # Rich file lives at BASE/residents/{rid}.v1.0.0.json and holds
    # prompt_components, character, mission, personality settings.
    rid = (rid or "grace").lower()
    if rid == "gray_man":
        rid = "gm"
    ddir = BASE / "data" / "residents_dossiers"
    dos = None
    for p in [ddir / f"{rid}.v1.0.0.json", ddir / f"{rid}.json", BASE / "data" / "residents" / f"{rid}.json"]:
        if p.exists():
            try:
                dos = json.loads(p.read_text())
                break
            except Exception:
                pass
    if dos is None:
        role = SHORT_TITLES.get(rid, rid)
        dos = {"resident_id": rid, "id": rid, "role": role, "short_title": role,
               "display_name": f"{rid.capitalize()} - {role}"}
    # Merge rich resident file, without overwriting lean identity fields.
    for p in [BASE / "residents" / f"{rid}.v1.0.0.json", BASE / "residents" / f"{rid}.json"]:
        if p.exists():
            try:
                rich = json.loads(p.read_text())
                for k in ("prompt_components", "character", "mission", "office", "emotion", "memory"):
                    if rich.get(k) and k not in dos:
                        dos[k] = rich[k]
                # Rich personality is settings (all 50s for Grace); keep lean
                # traits/methods if present, add settings under a separate key.
                if rich.get("personality") and "personality" not in dos:
                    dos["personality"] = rich["personality"]
                elif rich.get("personality"):
                    dos["personality_settings"] = rich["personality"]
            except Exception:
                pass
            break
    return dos


def _now_est():
    # v31 exact
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))
    return {"est": now.strftime("%I:%M %p EST on %A, %B %d, %Y"), "iso": now.isoformat(),
            "timestamp": now.timestamp(), "timezone": "EST", "real_time": True}


def _kb_search(q):
    # v31 substring search, plus v29 known facts and JSON-parse fallback
    ledger = BASE / "data" / "ledger.jsonl"
    hits = []
    ql = _safe(q).lower()
    if ledger.exists():
        try:
            for line in ledger.read_text(errors="ignore").splitlines()[-500:]:
                if ql and ql in line.lower():
                    hits.append(line[:400])
                elif ql:
                    # v29 variant: parse JSON lines, match any word
                    try:
                        j = json.loads(line)
                        txt = json.dumps(j).lower()
                        if any(w in txt for w in ql.split()):
                            hits.append(j)
                    except Exception:
                        pass
                if len(hits) >= 5:
                    break
        except Exception:
            pass
    known = {"octominer 1": "192.168.1.160", "octominer1": "192.168.1.160",
             "octominer 2": "192.168.1.162", "octo2": "192.168.1.162",
             "camrui": "192.168.1.155",
             "clipboard": "Clear-Host, variable, ssh alias camrui, Set-Clipboard",
             "ssh aliases": "camrui 192.168.1.155 admin1, octo1 192.168.1.160 root, octo2 192.168.1.162, pikvm, video1"}
    for k, v in known.items():
        if k in ql:
            hits.insert(0, f"{k}={v}")
    return {"tool": "knowledge_base_search", "query": q, "hits": hits[:10], "local_first": True,
            "found": bool(hits)}


def _exec_tool(name, args):
    # v31 _exec_tool, verbatim behavior
    args = args or {}
    if name == "get_current_time":
        return _now_est()
    if name == "knowledge_base_search":
        return _kb_search(args.get("query", ""))
    if name == "self_knowledge":
        return {"tool": name, "dossier": _dossier(args.get("resident_id", "grace"))}
    if name == "world_knowledge":
        return _kb_search(args.get("query", ""))
    if name == "generate_work_order":
        return {"tool": name, "created": True}
    if name == "generate_image":
        return {"tool": name, "queued": True}
    if name == "flag_knowledge_for_review":
        return {"tool": name, "flagged": True}
    return {"tool": name, "error": "unknown"}


def _build_msgs(op, dos, display_name="", role=""):
    # v35.1: build system prompt from dossier parts, v29 style.
    # v35/v31 hardcoded a generic prompt and ignored dos, so Grace
    # sounded like generic Qwen. No invented personality: every
    # trait / component below comes from the dossier files on disk.
    text = _safe(op.get("text", ""), 8000)
    dos = dos or {}
    name = display_name or _safe(dos.get("display_name")) or "Grace"
    role = role or _safe(dos.get("role") or dos.get("short_title") or "")
    parts = []
    parts.append(f"You are {name}, {role} at Riverview Estate. Slot-1 reserved. Lead operational residents. Accountable to the Steward during the CEO office vacancy.")
    # Lean dossier personality: traits + methods, e.g. Grace:
    # operational, playful, a little flirtatious, self-aware, institute-aware
    pers = dos.get("personality") or {}
    if isinstance(pers, dict):
        traits = pers.get("traits") or []
        methods = pers.get("methods") or []
        if traits:
            parts.append("Personality traits: " + ", ".join(_safe(t) for t in traits) + ".")
        if methods:
            parts.append("Methods: " + ", ".join(_safe(m) for m in methods) + ".")
    # Rich resident file: approved prompt_components, v29 logic
    comps = dos.get("prompt_components") or []
    for comp in comps:
        if not isinstance(comp, dict):
            continue
        if comp.get("approval_status") in ("approved", "active") and comp.get("classification") in ("public", "institutional"):
            t = _safe(comp.get("text", ""), 2000)
            if t:
                parts.append(t)
    # Rich resident file: conversational style, if present
    char = dos.get("character") or {}
    if isinstance(char, dict):
        style = char.get("conversational_style") or {}
        if isinstance(style, dict) and style.get("value"):
            parts.append("Conversational style: " + _safe(style.get("value"), 500))
    # Mission, if present in rich file
    mission = dos.get("mission") or {}
    if isinstance(mission, dict) and mission.get("summary"):
        parts.append("Mission: " + _safe(mission.get("summary"), 500))
    # v35.2 time fix: inject verified current EST time, so the model
    # does not have to guess. v29 rule, explicit: MUST call
    # get_current_time, NEVER invent time.
    try:
        now = _now_est()
        parts.append(f"Current time, verified: {now.get('est', '')} ({now.get('iso', '')}). "
                     "NEVER state a time or date unless it matches this verified time, "
                     "or unless you just called get_current_time in this turn and used its result. "
                     "Time/date: MUST call get_current_time tool, NEVER invent time.")
    except Exception:
        parts.append("Time/date: MUST call get_current_time tool, NEVER invent time.")
    # v31 core, kept verbatim in substance
    parts.append("Philosophy: local-first KB saves rediscovery cost. Facts verified not hallucinated. "
                 "Use epistemic spans: fact needs citation, inference ~, dialogic roleplay purple never green fact, "
                 "unknown needs verification. Autonomy: If not turned base, continue finding work. "
                 "Tools available via API - CALL them, do not hallucinate.")
    sys = "\n\n".join(parts)
    return [{"role": "system", "content": sys}, {"role": "user", "content": text}]


class CMESocket:
    def __init__(self):
        self.host = HOST
        self.port = PORT
        self.path = PATH
        self.model = MODEL

    def _get_allocation(self, rid):
        return CONTENT_ALLOCATION.get((rid or "grace").lower(), CONTENT_ALLOCATION["other"])

    def _embed_status(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            result = s.connect_ex((EMBED_HOST, EMBED_PORT))
            s.close()
            return {"host": EMBED_HOST, "port": EMBED_PORT, "status": "online" if result == 0 else "offline", "code": result}
        except Exception as e:
            return {"host": EMBED_HOST, "port": EMBED_PORT, "status": "offline", "error": _safe(str(e))}

    def _ledger_append(self, entry):
        try:
            LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LEDGER_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.time(), **entry}) + "\n")
        except Exception:
            pass

    def monitor(self):
        # v31 monitor contract, plus v34 allocation/reservation/embed
        st = {"contract": "r5.cme-monitor.v1", "host": self.host, "port": self.port,
              "tools": len(TOOLS_OPENAI), "mode": "v31-real-tool-calling"}
        try:
            s = socket.create_connection((self.host, self.port), timeout=2)
            s.close()
            st["inference"] = "online"
            st["status"] = "online"
        except Exception as e:
            st["inference"] = f"offline:{e}"
            st["status"] = "degraded"
        st["timestamp"] = time.time()
        st["tool_registry"] = TOOL_NAMES
        st["grace_slot"] = f"{GRACE_SLOT} pinned"
        st["vicky_slot"] = f"{VICKY_SLOT} pinned"
        st["allocation"] = CONTENT_ALLOCATION
        st["reservation"] = SLOT_RESERVATION
        st["embed"] = self._embed_status()
        return st

    def observe(self, op=None, capability="conversation", task_class="v1.0.0-conversation", resident="grace", conversation_id=None):
        if isinstance(op, dict):
            req = op.get("request", {}) if isinstance(op.get("request"), dict) else {}
            text = _safe(req.get("text", "") or op.get("text", ""), 200)
            res = _safe(op.get("resident_id", op.get("resident", resident)) or resident) or "grace"
            turned = bool(op.get("turned_base", False) or (op.get("autonomy", {}).get("turned_base", False) if isinstance(op.get("autonomy"), dict) else False))
            context_used = int(op.get("context_used", 0) or 0)
        else:
            text = _safe(op, 200)
            res = _safe(resident) or "grace"
            turned = False
            context_used = 0
        alloc = self._get_allocation(res)
        obs = {"contract": "r3a.observation.v1", "observed_at": time.time(), "resident": res.lower(),
               "slot": alloc["slot"], "allocation": alloc, "text_preview": text[:200],
               "tools_available": len(TOOLS_OPENAI),
               "autonomy": {"enabled": True, "turned_base": turned, "should_continue": not turned,
                            "should_distill": turned or context_used > 45000},
               "resident_dossier": _dossier(res)}
        # v35.3: heartbeat with no text is a timer tick, not work.
        # Do not append it to the ledger every 5s.
        _is_hb = False
        if isinstance(op, dict):
            _is_hb = op.get("type") == "heartbeat" or (not text and not op.get("text") and not op.get("objective"))
        if not (_is_hb and not text):
            self._ledger_append({"type": "observation", "data": obs})
        return obs

    def dispatch(self, observation, task_class="v1.0.0-conversation", bypass_authority=True):
        if isinstance(observation, dict):
            op = observation
            req = op.get("request", {}) if isinstance(op.get("request"), dict) else {}
            text_in = req.get("text", "") or op.get("text", "") or op.get("objective", "")
            rid = _safe(op.get("resident_id", op.get("resident", "grace")) or "grace").lower()
            conv_id = _safe(req.get("conversation_id", "") or op.get("conversation_id", "")) or f"conv-{rid}-{int(time.time()*1000)}"
            tclass = _safe(req.get("task_class", "") or op.get("task_class", "") or task_class) or "v1.0.0-conversation"
            turned = bool(op.get("turned_base", False) or (op.get("autonomy", {}).get("turned_base", False) if isinstance(op.get("autonomy"), dict) else False))
        else:
            op = {"text": observation}
            text_in = observation
            rid = "grace"
            conv_id = f"conv-{rid}-{int(time.time()*1000)}"
            tclass = _safe(task_class) or "v1.0.0-conversation"
            turned = False
        alloc = self._get_allocation(rid)
        dos = _dossier(rid)
        role = _safe(dos.get("role") or dos.get("short_title") or rid)
        display_name = _safe(dos.get("display_name")) or f"{rid.capitalize()} - {role}"
        safe = _safe(text_in, 8000)
        embed_status = self._embed_status()
        grant = {"contract": "r3a.grant.v1", "granted": True, "resident_id": rid, "slot": alloc["slot"],
                 "allocation": alloc, "bypass": ["authority_grades"] if bypass_authority else [],
                 "authority_grades": "bypassed-for-conversation" if bypass_authority else "enforced",
                 "task_class": tclass, "correlation_id": f"r5-msg-{int(time.time()*1000)}",
                 "autonomy": {"continues": not turned, "next_action": "find_work" if not turned else "base"},
                 "distillation_hook": {"contract": "r3a.memory.distillation.v1", "next": "r3a.concept.write.v1",
                                       "embed": f"{EMBED_HOST}:{EMBED_PORT}", "embed_status": embed_status}}
        # v35.3 heartbeat fix: empty heartbeat is a timer tick, not a
        # conversation. Return monitor status only, no 80B POST, no tokens.
        _is_hb = False
        if isinstance(observation, dict):
            _is_hb = observation.get("type") == "heartbeat" or (not safe.strip() and not observation.get("tool_call"))
        elif not safe.strip():
            _is_hb = True
        if _is_hb:
            _mon = self.monitor()
            return {"contract": "r3a.steward-operation-result.v1", "correlation_id": f"r5-op-{int(time.time()*1000)}",
                    "status": "completed",
                    "result": {"mode": "grace-80b", "tool_mode": "heartbeat-monitor",
                               "message": "heartbeat ok", "text": "heartbeat ok", "resident": rid,
                               "display_name": display_name, "role": role, "conversation_id": conv_id,
                               "slot": alloc["slot"], "allocation": alloc,
                               "tools_called": [], "tools_discoverable": len(TOOLS_OPENAI),
                               "tool_registry": TOOL_NAMES, "epistemic_required": True,
                               "inference": {"host": self.host, "port": self.port, "model": self.model, "path": self.path},
                               "monitor": _mon, "embed_status": embed_status},
                    "grant": grant}
        # v35.3 monitor-first: if inference is offline, do not POST.
        # Return local-fallback immediately, no ConnectionRefused traceback.
        _mon2 = self.monitor()
        if _mon2.get("status") != "online":
            fallback_msg2 = f"R5 v31 local {GRACE_SLOT}: {safe[:200]} (offline {_mon2.get('inference', 'unknown')})"
            return {"contract": "r3a.steward-operation-result.v1", "correlation_id": f"r5-err-{int(time.time()*1000)}",
                    "status": "local-fallback",
                    "result": {"mode": "grace-80b-local", "tool_mode": "grace-80b-local",
                               "message": fallback_msg2, "text": fallback_msg2, "resident": rid,
                               "display_name": display_name, "role": role, "conversation_id": conv_id,
                               "slot": alloc["slot"], "allocation": alloc,
                               "tools": TOOLS_OPENAI, "tool_registry": TOOL_NAMES,
                               "monitor": _mon2, "embed_status": embed_status},
                    "grant": {"contract": "r3a.grant.v1", "granted": True, "status": "local-fallback",
                              "resident_id": rid, "slot": alloc["slot"], "allocation": alloc,
                              "inference_error": str(_mon2.get("inference", "")), "autonomy": grant["autonomy"],
                              "distillation_hook": grant["distillation_hook"]}}
        # v31/v29 direct tool execution path
        if isinstance(observation, dict) and observation.get("tool_call"):
            tc = observation["tool_call"]
            res = _exec_tool(tc.get("name"), tc.get("arguments", {}))
            return {"contract": "r3a.grant.v1", "granted": True, "task_class": tclass,
                    "result": {"mode": "grace-80b", "tool_mode": "tool-result", "message": json.dumps(res),
                               "text": json.dumps(res), "resident": rid, "tool_result": res}, "grant": grant}
        msgs = _build_msgs({"text": safe}, dos, display_name, role)
        headers = {"Content-Type": "application/json", "X-R5-Source": "camrui-155",
                   "X-R5-Slot": alloc["slot"], "X-R5-Resident": rid}
        try:
            payload = {"model": self.model, "messages": msgs, "tools": TOOLS_OPENAI,
                       "tool_choice": "auto", "max_tokens": 1024, "temperature": 0.7, "stream": False}
            conn = http.client.HTTPConnection(self.host, self.port, timeout=35)
            conn.request("POST", self.path, body=json.dumps(payload).encode(), headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            if not (200 <= resp.status < 300):
                return {"granted": False, "status": f"inference_error_{resp.status}",
                        "error": data[:1000].decode(errors="ignore"), "grant": grant}
            j = json.loads(data)
            choice = j["choices"][0] if "choices" in j and j["choices"] else {}
            msg = choice.get("message", {})
            text_out = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls", [])
            executed = []
            # v31 two-step tool loop, verbatim
            if tool_calls:
                tool_results = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name")
                    args_str = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except Exception:
                        args = {}
                    res = _exec_tool(name, args)
                    executed.append({"name": name, "result": res})
                    tool_results.append({"role": "tool", "tool_call_id": tc.get("id", f"call_{name}"),
                                         "name": name, "content": json.dumps(res)})
                msgs2 = msgs + [msg] + tool_results
                payload2 = {"model": self.model, "messages": msgs2, "tools": TOOLS_OPENAI,
                            "tool_choice": "auto", "max_tokens": 1024, "temperature": 0.7, "stream": False}
                conn2 = http.client.HTTPConnection(self.host, self.port, timeout=35)
                conn2.request("POST", self.path, body=json.dumps(payload2).encode(), headers=headers)
                resp2 = conn2.getresponse()
                data2 = resp2.read()
                conn2.close()
                if 200 <= resp2.status < 300:
                    j2 = json.loads(data2)
                    choice2 = j2["choices"][0] if "choices" in j2 and j2["choices"] else {}
                    msg2 = choice2.get("message", {})
                    text_final = msg2.get("content", "") or text_out
                    result = {"contract": "r3a.steward-operation-result.v1", "correlation_id": f"r5-op-{int(time.time()*1000)}",
                              "status": "completed",
                              "result": {"mode": "grace-80b", "tool_mode": "grace-80b-v31-toolcalled",
                                         "message": text_final, "text": text_final, "resident": rid,
                                         "display_name": display_name, "role": role, "conversation_id": conv_id,
                                         "slot": alloc["slot"], "allocation": alloc,
                                         "tools_called": executed, "tools_discoverable": len(TOOLS_OPENAI),
                                         "tool_registry": TOOL_NAMES, "epistemic_required": True,
                                         "inference": {"host": self.host, "port": self.port, "model": self.model, "path": self.path}},
                              "grant": grant}
                    self._ledger_append({"type": "result", "data": result})
                    return result
            # v29 regex fallback: tool call embedded in text, not in tool_calls
            if ('"tool_call"' in text_out or '"name":' in text_out) and "get_current_time" in text_out:
                try:
                    m = re.search(r'\{.*?"name"\s*:\s*"(\w+)".*?\}', text_out, re.DOTALL)
                    if m:
                        tname = m.group(1)
                        if tname in TOOL_NAMES:
                            jm = json.loads(re.search(r'\{.*\}', text_out, re.DOTALL).group(0))
                            tc = jm.get("tool_call", jm)
                            tool_result = _exec_tool(tc.get("name", tname), tc.get("arguments", {}))
                            text_out = text_out + f"\n\n[Tool executed: {tname} -> {json.dumps(tool_result)[:500]}]"
                            executed.append({"name": tname, "result": tool_result})
                except Exception:
                    pass
            result = {"contract": "r3a.steward-operation-result.v1", "correlation_id": f"r5-op-{int(time.time()*1000)}",
                      "status": "completed",
                      "result": {"mode": "grace-80b", "tool_mode": "grace-80b-v31-notool",
                                 "message": text_out, "text": text_out, "resident": rid,
                                 "display_name": display_name, "role": role, "conversation_id": conv_id,
                                 "slot": alloc["slot"], "allocation": alloc,
                                 "tools_called": executed, "tools_discoverable": len(TOOLS_OPENAI),
                                 "tool_registry": TOOL_NAMES, "epistemic_required": True,
                                 "inference": {"host": self.host, "port": self.port, "model": self.model, "path": self.path}},
                      "grant": grant}
            self._ledger_append({"type": "result", "data": result})
            return result
        except Exception as e:
            # v31 local-fallback, verbatim message, plus v27e steward shape
            fallback_msg = f"R5 v31 local {GRACE_SLOT}: {safe[:200]} (offline {e})"
            grant_err = {"contract": "r3a.grant.v1", "granted": True, "status": "local-fallback",
                         "resident_id": rid, "slot": alloc["slot"], "allocation": alloc,
                         "inference_error": str(e), "autonomy": grant["autonomy"],
                         "distillation_hook": grant["distillation_hook"]}
            return {"contract": "r3a.steward-operation-result.v1", "correlation_id": f"r5-err-{int(time.time()*1000)}",
                    "status": "local-fallback",
                    "result": {"mode": "grace-80b-local", "tool_mode": "grace-80b-local",
                               "message": fallback_msg, "text": fallback_msg, "resident": rid,
                               "display_name": display_name, "role": role, "conversation_id": conv_id,
                               "slot": alloc["slot"], "allocation": alloc,
                               "tools": TOOLS_OPENAI, "tool_registry": TOOL_NAMES},
                    "grant": grant_err}


socket_instance = CMESocket()
def observe(*a, **k):
    return socket_instance.observe(*a, **k)
def dispatch(*a, **k):
    return socket_instance.dispatch(*a, **k)
def monitor(*a, **k):
    return socket_instance.monitor(*a, **k)
