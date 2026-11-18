"""r5-epistemic plugin — epistemic span grading, Phase 1 (v35.9 design).

Provides:
  epistemic.prompt — the tag-format instruction for the system prompt.
  epistemic.verify — parse + verify + downgrade a model reply.

The socket (frozen core) never grades. It passes the reply text, this
turn's tool results, the pre-seeded KB hits, and the resident's dossier
level, and attaches what this plugin returns. If this plugin is missing,
the socket reports spans unavailable — never verified.

Levels: fact / inference / unknown / roleplay.
  fact      — supported by evidence handed to verify() this turn.
  inference — follows from a verified fact in this turn.
  unknown   — not verified, or the model said it does not know.
  roleplay  — creative / personality writing. Never green, never a fact.
Rules (design v1, Pat 2026-11-17):
  - A fact with no supporting evidence is downgraded to unknown.
  - An inference resting on nothing verified is downgraded to unknown.
  - Untagged text is unknown. Coverage is measured, not assumed.
  - strict level (Grace/Cheryl/Ingrid dossiers, or an engineering /
    work-order task): roleplay in a factual answer is downgraded to
    unknown and flagged. D2 decision, Pat "go" 2026-11-18: task-level
    strict — Vicky's dossier stays balanced, engineering tasks force
    strict for any resident.
  - relaxed (Jessica) may roleplay freely; facts still need evidence.
    v35.8 rule: FACTS ARE NEVER RELAXED.
Stdlib only. Embed service (8081, BAAI/bge-m3) is used only as a
tiebreak when token overlap is inconclusive, and only when reachable.
"""
import json
import math
import re
import urllib.request

LEVELS = ("fact", "inference", "unknown", "roleplay")
_TAG_RE = re.compile(r"\[(fact|inference|unknown|roleplay)\](.*?)\[/\1\]", re.I | re.S)
# Live-found 2026-11-18: the model sometimes emits an unclosed tag
# ("[unknown] I don't have my height listed...") or a doubled tag, and
# the regex above then leaves literal "[unknown]" in the message the
# user sees. Tokenizer below handles unclosed / stray markers, and
# clean_text strips any tag-like token that survives, belt and braces.
_MARKER_RE = re.compile(r"\[(/?)(fact|inference|unknown|roleplay)\]", re.I)
_STOP = set("the a an and or of to in on for with is are was were be been it its this that these those you your we our they their he she his her i me my not no yes do does did will would can could should as at by from about into over under what who when where why how tell me please".split())
_EMBED_URL = "http://192.168.1.160:8081/embeddings"
_EMBED_MODEL = "BAAI/bge-m3"


def _tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _overlap(claim_tokens, evidence_text):
    if not claim_tokens:
        return 0.0
    ev = _tokens(evidence_text)
    if not ev:
        return 0.0
    return len(claim_tokens & ev) / len(claim_tokens)


def _embed(text):
    try:
        req = urllib.request.Request(
            _EMBED_URL,
            data=json.dumps({"model": _EMBED_MODEL, "input": text}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.loads(r.read())
        return [float(x) for x in j["data"][0]["embedding"]]
    except Exception:
        return None


def _cosine(a, b):
    try:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0
    except Exception:
        return 0.0


def _supported(claim, evidence_texts, min_overlap=0.6):
    """Return (supported_bool, source, method). Token overlap first,
    embed cosine as tiebreak when overlap is inconclusive (0.3-0.6).
    Facts need min_overlap 0.6; inferences need only 0.3, because an
    inference follows from evidence rather than restating it."""
    toks = _tokens(claim)
    if not toks:
        return False, None, "empty-claim"
    best, best_src = 0.0, None
    for ev in evidence_texts:
        ov = _overlap(toks, ev)
        if ov > best:
            best, best_src = ov, ev
    if best >= min_overlap:
        return True, best_src, "token-overlap"
    if best >= 0.3:
        cvec = _embed(claim)
        if cvec:
            for ev in evidence_texts:
                evec = _embed(ev)
                if evec and _cosine(cvec, evec) >= 0.75:
                    return True, ev, "embed-cosine"
    return False, best_src, "token-overlap"


def _parse(text):
    """Split reply into segments. Tokenizer, not regex pairs: an
    unclosed [level] runs to the next marker or end of text, a stray
    close marker is dropped, and untagged gaps become unknown segments.
    A literal tag can never survive into a segment's text."""
    text = text or ""
    segs, tagged_chars = [], 0
    cur, cur_tagged, buf = "unknown", False, []

    def flush():
        nonlocal buf
        chunk = "".join(buf)
        if chunk.strip():
            segs.append({"text": chunk, "claimed": cur, "tagged": cur_tagged})
        buf = []

    pos = 0
    for m in _MARKER_RE.finditer(text):
        if m.start() > pos:
            buf.append(text[pos:m.start()])
        closing, level = bool(m.group(1)), m.group(2).lower()
        if not closing:
            if cur_tagged:
                tagged_chars += len("".join(buf))
            flush()
            cur, cur_tagged = level, True
        else:
            if cur_tagged and cur == level:
                tagged_chars += len("".join(buf))
                flush()
                cur, cur_tagged = "unknown", False
            # stray close marker: dropped, its text never enters a segment
        pos = m.end()
    if pos < len(text):
        buf.append(text[pos:])
    if cur_tagged:
        tagged_chars += len("".join(buf))
    flush()
    if not segs:
        segs = [{"text": text, "claimed": "unknown", "tagged": False}]
    coverage = (tagged_chars / len(text)) if text.strip() else 0.0
    return segs, coverage


def _strip_tags(text):
    return _MARKER_RE.sub("", text or "")


PROMPT_FRAGMENT = (
    "EPISTEMIC SPANS — tag every claim in your reply with one of four levels, "
    "using bracket tags: [fact]...[/fact] [inference]...[/inference] "
    "[unknown]...[/unknown] [roleplay]...[/roleplay]. "
    "fact = verified against a tool result in this turn (a device, IP, resident name or role, "
    "dossier field, number, date). inference = follows by reasoning from a verified fact. "
    "unknown = not verified, or you do not know. roleplay = creative / personality writing "
    "(stories, jokes, flirting, mood). Tag facts only when a tool result supports them; "
    "if no tool result supports a claim, tag it [unknown] and say you do not know. "
    "Never tag creative writing as fact. Example: [fact]OctoMiner1's IP address is "
    "192.168.1.160.[/fact] [roleplay]Well, well, Pat~[/roleplay]"
)


def _effective_level(resident_level, task_class):
    tc = (task_class or "").lower()
    if any(k in tc for k in ("engineering", "work-order", "work_order", "objective")):
        return "strict"
    return (resident_level or "balanced").lower()


def create_plugin(config):
    def prompt():
        return {"prompt": PROMPT_FRAGMENT, "levels": list(LEVELS),
                "format": "[level]text[/level]", "plugin": "r5-epistemic"}

    def verify(text="", tool_results=None, kb_hits=None, resident_level="balanced",
               task_class="v1.0.0-conversation"):
        evidence = []
        for tr in (tool_results or []):
            try:
                evidence.append(json.dumps(tr) if not isinstance(tr, str) else tr)
            except Exception:
                evidence.append(str(tr))
        for h in (kb_hits or []):
            evidence.append(str(h))
        level = _effective_level(resident_level, task_class)
        segs, coverage = _parse(text)
        out, verified_facts, downgraded = [], [], 0
        for s in segs:
            claimed = s["claimed"]
            span = {"text": s["text"], "claimed_level": claimed, "level": claimed,
                    "verified": False, "source": None, "downgraded_from": None,
                    "flagged": False}
            if claimed == "fact":
                ok, src, method = _supported(s["text"], evidence)
                if ok:
                    span["verified"] = True
                    span["source"] = (src or "")[:300]
                    span["method"] = method
                    verified_facts.append(s["text"])
                else:
                    span["level"] = "unknown"
                    span["downgraded_from"] = "fact"
                    span["method"] = method
                    downgraded += 1
            elif claimed == "inference":
                # An inference is verified when it follows from the
                # verified facts of this turn or from the evidence itself.
                # With no evidence at all (13.6 bar case) it downgrades.
                ok, src, method = _supported(
                    s["text"], verified_facts + evidence, min_overlap=0.3)
                if ok and (verified_facts or evidence):
                    span["verified"] = True
                    span["source"] = (src or "")[:300]
                    span["method"] = method
                else:
                    span["level"] = "unknown"
                    span["downgraded_from"] = "inference"
                    downgraded += 1
            elif claimed == "roleplay":
                if level == "strict":
                    span["level"] = "unknown"
                    span["downgraded_from"] = "roleplay"
                    span["flagged"] = True
                    downgraded += 1
            out.append(span)
        # Join segments with a space where the stripped tag was the
        # only thing between two sentences ("dossier.But" otherwise).
        _parts = []
        for s in out:
            if (_parts and _parts[-1] and not _parts[-1][-1].isspace()
                    and s["text"] and not s["text"][0].isspace()):
                _parts.append(" ")
            _parts.append(s["text"])
        clean = _strip_tags("".join(_parts))
        counts = {lv: sum(1 for s in out if s["level"] == lv) for lv in LEVELS}
        counts["downgraded"] = downgraded
        counts["coverage"] = round(coverage, 3)
        return {"plugin": "r5-epistemic", "status": "graded",
                "resident_level": level, "clean_text": clean,
                "spans": out, "summary": counts}

    class _Plugin:
        capabilities = {"epistemic.verify": verify, "epistemic.prompt": prompt}

    return _Plugin()
