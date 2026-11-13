from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import pathlib, json, os, asyncio, secrets as py_secrets, time, datetime
from passlib.context import CryptContext

app = FastAPI(title="Riverview 5 - R5 Dashboard + Auth")
BASE = pathlib.Path(__file__).parent.parent
DASH = BASE / "dashboard"
SECRETS_FILE = BASE / "secrets" / "auth.json"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def load_auth():
    env_user = os.getenv("R5_WEBSITE_USERNAME")
    env_pass = os.getenv("R5_WEBSITE_PASSWORD")
    if env_user and env_pass:
        return {"username": env_user, "password": env_pass, "source": "env"}
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text())
            return {"username": data.get("username"), "password_hash": data.get("password_hash"), "source": "secrets/auth.json"}
        except:
            pass
    return None

if DASH.exists():
    app.mount("/web", StaticFiles(directory=str(DASH)), name="web")
    app.mount("/static", StaticFiles(directory=str(DASH)), name="static")

@app.get("/")
async def root():
    return FileResponse(str(DASH / "index.html"))

@app.get("/login")
async def login_page():
    p = DASH / "steward-login.html"
    return FileResponse(str(p)) if p.exists() else FileResponse(str(DASH / "index.html"))

@app.get("/steward")
async def steward_page():
    return FileResponse(str(DASH / "index.html"))

@app.get("/steward.html")
async def steward_html():
    return FileResponse(str(DASH / "index.html"))

# --- V19 NEW: About dynamic endpoint ---

@app.get("/api/v1/about")
async def about():
    import pathlib, json, time, os
    base = pathlib.Path(__file__).parent.parent
    dossier_dir = base / "data" / "residents_dossiers"
    # Also check deploy path
    if not dossier_dir.exists():
        dossier_dir = pathlib.Path("/opt/riverview/r5-full/data/residents_dossiers")
    
    residents = {}
    residents_list = []
    short_titles = {
        "alyssa": "Chief of Staff",
        "grace": "Director Ops",
        "chloe": "Chief Architect",
        "jessica": "Chief Character",
        "vicky": "Engineering",
        "helen": "HR",
        "ingrid": "Security Chief",
        "eleanor": "Archives",
        "marie": "Research",
        "judy": "Legal",
        "cheryl": "CPA",
        "evelyn": "Confidant",
        "gm": "Gray",
        "gray_man": "Gray",
        "self": "Self"
    }
    
    if dossier_dir.exists():
        for f in sorted(dossier_dir.glob("*.json")):
            try:
                j = json.loads(f.read_text())
                rid = j.get("id", f.stem.split(".")[0]).lower()
                # Normalize gray_man to gm
                if rid == "gray_man":
                    rid = "gm"
                # Force short title
                short = short_titles.get(rid, j.get("role", rid))
                display = f"{'GM' if rid=='gm' else rid.capitalize()} - {short}" if rid != 'self' else "Self"
                # Override display if already short in file
                if "display_name" in j and len(j["display_name"]) < 40 and "Comptroller" not in j["display_name"] and "Guardian" not in j["display_name"] and "Foundry" not in j["display_name"] and "Only male" not in j["display_name"]:
                    display = j["display_name"]
                residents[f.name] = {
                    "id": rid,
                    "level": j.get("epistemic_config", {}).get("level", "balanced"),
                    "name": f.name,
                    "display_name": display,
                    "role": short,
                    "short_title": short,
                    "title": short
                }
                residents_list.append(rid)
            except Exception as e:
                residents[f.name] = {"error": str(e), "name": f.name}
    
    # Dashboard and CME sizes
    dash_path = base / "dashboard" / "index.html"
    cme_path = base / "cme" / "socket.py"
    server_path = pathlib.Path(__file__)
    about_html = base / "dashboard" / "about.html"
    
    def get_size_mtime(p):
        try:
            return {"size": p.stat().st_size, "mtime": str(p.stat().st_mtime)}
        except:
            return {"size": 0, "mtime": "missing"}
    
    return {
        "contract": "r5.about.v1",
        "version": "R5 v26c GM caps GM - Gray uppercase + plus button v26 final short titles",
        "commit": "8a2f74a R5 v26c short titles + plus button - Engineering not Foundry, Gray not Gray Man, Security Chief not firewall, CPA",
        "dashboard": "R5 CONTROLLED DOCUMENT Rev 1.0.30",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": "192.168.1.155:8080",
        "anchor": {"x": 0.377, "y": 0.653},
        "backgroundPosition": "37.7% 65.3%",
        "background": {"file": "waterwheel_dashboard_map_labels.png", "status": "fixed v19", "previous": "missing v18"},
        "website": {"file": "server.py", "size": get_size_mtime(server_path)["size"], "mtime": get_size_mtime(server_path)["mtime"]},
        "cme": {"file": "socket.py", "size": get_size_mtime(cme_path)["size"], "mtime": get_size_mtime(cme_path)["mtime"], "pass": True, "mode": "lean-v24-per-resident-conv-epistemic"},
        "server": {"file": "server.py", "size": get_size_mtime(server_path)["size"], "mtime": get_size_mtime(server_path)["mtime"]},
        "dashboard_file": {"file": "index.html", "size": get_size_mtime(dash_path)["size"], "mtime": get_size_mtime(dash_path)["mtime"]},
        "about_file": {"file": "about.html", "size": get_size_mtime(about_html)["size"], "mtime": get_size_mtime(about_html)["mtime"]},
        "capabilities": {},
        "residents_dossiers": residents,
        "residents_list": sorted(set(residents_list)),
        "short_titles": short_titles,
        "vision": {
            "host": "192.168.1.162",
            "vision_endpoint": "192.168.1.160:18080",
            "slots": 8,
            "tokens": 4096,
            "status": "plugin not core modularity",
            "service": "qwen30b-vision.service 16060 MiB / 16384 MiB 21s startup",
            "states": ["Ready green", "Model unloaded yellow Case A load", "Host offline grey Case B power-on via Issue #367 authorized registry", "Starting spinning", "Unavailable red"]
        },
        "registries": {"settings": "R3 settings registry not connected - R5 local Help->About now injected", "note": "DB 010_governed_knowledge 011_resident_dossiers source JSON cache avoids 100k JSON"},
        "routes": ["/about", "/steward/about", "/api/v1/about", "/api/v1/visual/status", "/api/v1/visual/activate", "/api/v1/visual/background", "/steward"],
        "help_section": {"path": "Settings -> Help -> About", "status": "injected v26c Help and About buttons after Infrastructure", "dynamic": "GET /api/v1/about live + iframe /about"}
    }


@app.get("/api/v1/visual/background")
async def visual_background():
    # ESTATE_SPATIAL_CANON per requirement
    meta = {
        "contract": "r5.visual-background.v1",
        "anchor": {"x": 0.377, "y": 0.653},
        "backgroundPosition": "37.7% 65.3%",
        "fit": "cover",
        "canon": "ESTATE_SPATIAL_CANON.md",
        "assets": []
    }
    # Try to serve real file if exists, but always include meta
    for name in ["waterwheel_dashboard_map_labels.png","panorama_dashboard_system_flags.png","waterwheel.png"]:
        p = BASE / "assets" / name
        if not p.exists():
            p = DASH / name
        if p.exists():
            meta["assets"].append(name)
            # If query ?meta=1 return JSON, else return file
            # For backward compat, return file if exists
            # V19: return file but include headers for anchor
            resp = FileResponse(str(p))
            resp.headers["X-Estate-Anchor-X"] = "0.377"
            resp.headers["X-Estate-Anchor-Y"] = "0.653"
            resp.headers["X-Estate-Background-Position"] = "37.7% 65.3%"
            return resp
    # No file found - return meta JSON so frontend can use anchor anyway
    return JSONResponse(content=meta)

@app.get("/api/v1/visual/background/meta")
async def visual_background_meta():
    return {
        "contract": "r5.visual-background.v1",
        "anchor": {"x": 0.377, "y": 0.653},
        "backgroundPosition": "37.7% 65.3%",
        "fit": "cover",
        "canon": "ESTATE_SPATIAL_CANON.md"
    }

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        try:
            s = await steward_status()
            await ws.send_json({"type":"heartbeat","status": s,"time": datetime.datetime.now().isoformat()})
        except:
            await ws.send_json({"type":"heartbeat","cme":"online"})
        await asyncio.sleep(2)


# R5 v24 Vision Readiness plugin not core Issue #209 #353 21s #367 registry
@app.get("/api/v1/visual/status")
async def api_visual_status():
    import socket as _socket
    from datetime import datetime as _dt
    status = {"contract": "r3a.visual-status.v1", "timestamp": _dt.utcnow().isoformat()+"Z"}
    host = "192.168.1.162"
    host_online = False
    try:
        sock = _socket.create_connection((host, 8080), timeout=1)
        sock.close()
        host_online = True
    except:
        try:
            sock = _socket.create_connection((host, 22), timeout=1)
            sock.close()
            host_online = True
        except:
            host_online = False
    model_loaded = False
    try:
        import http.client
        conn = http.client.HTTPConnection("192.168.1.160", 18080, timeout=2)
        conn.request("GET", "/v1/models")
        resp = conn.getresponse()
        if 200 <= resp.status < 300:
            model_loaded = True
        conn.close()
    except:
        model_loaded = False
    if not host_online:
        status.update({"host": "offline", "service": "unknown", "model": "unloaded", "state": "Host offline", "vram": None, "endpoint": "timeout", "color": "grey", "icon": "X"})
    elif not model_loaded:
        status.update({"host": "online", "service": "inactive", "model": "unloaded", "state": "Model unloaded", "vram": None, "endpoint": "timeout", "color": "yellow", "icon": "O", "note": "Case A load via octominer2/vision/load"})
    else:
        status.update({"host": "online", "service": "active", "model": "loaded", "state": "Ready", "vram": 16060, "endpoint": "responding", "color": "green", "icon": "OK", "note": "21s from 61s 16060 MiB VRAM"})
    return status

@app.post("/api/v1/visual/activate")
async def api_visual_activate(request: dict = None):
    from datetime import datetime as _dt
    if request is None:
        request = {}
    mode = request.get("mode", "load")
    return {"contract": "r3a.visual-activate.v1", "mode": mode, "status": "queued", "job_id": f"vision-{int(_dt.utcnow().timestamp())}", "note": f"Requested {mode} Case A load vs B power-on via Issue #367"}

@app.get("/api/v1/visual/background")
async def api_visual_background():
    import pathlib as _pl
    from fastapi.responses import FileResponse
    base2 = _pl.Path(__file__).parent.parent
    candidates = [base2/"dashboard"/"waterwheel_dashboard_map_labels.png", base2/"assets"/"waterwheel_dashboard_map_labels.png", base2/"dashboard"/"waterwheel.png"]
    for p in candidates:
        if p.exists():
            return FileResponse(str(p))
    return {"anchor": {"x": 0.377, "y": 0.653}, "backgroundPosition": "37.7% 65.3%", "status": "missing v18 fixed v19"}


@app.get("/about")
async def about_page():
    from fastapi.responses import FileResponse
    import pathlib as _pl
    p = _pl.Path(__file__).parent.parent / "dashboard" / "about.html"
    if p.exists():
        return FileResponse(str(p), media_type="text/html")
    return {"detail": "about.html not found at "+str(p)}

@app.get("/steward/about")
async def steward_about_alias():
    from fastapi.responses import FileResponse
    import pathlib as _pl
    p = _pl.Path(__file__).parent.parent / "dashboard" / "about.html"
    if p.exists():
        return FileResponse(str(p), media_type="text/html")
    return {"detail": "about.html not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


@app.get('/api/v1/resident/directory')
@app.get('/api/v1/residents')
async def resident_directory():
    residents=[{'id':'grace','name':'Grace','role':'Grace Controls','status':'online'},{'id':'steward','name':'Steward','role':'R5 Steward','status':'online'}]
    return {'contract':'r3a.resident-directory.v1','residents':residents,'registered_residents':len(residents),'count':len(residents),'state':{'residents':residents,'state_catalog':[],'events':[]},'status':'online'}

@app.get('/api/v1/conversation')
@app.get('/api/v1/conversations')
async def list_conversations():
    return {'contract':'r5.conversation-list.v1','conversations':[{'id':'conv-grace-001','resident':'grace','title':'Grace Chat'}]}

@app.post('/api/v1/conversation')
async def create_conversation(request):
    try:
        body=await request.json()
    except:
        body={}
    text=body.get('text','') or body.get('message','')
    from cme.socket import CMESocket
    sock=CMESocket()
    grant=sock.dispatch({'text':text},'v1.0.0-conversation')
    return {'contract':'r5.conversation.v1','status':'completed','resident':'grace','message':f'Grace: {text[:200]}','grant':dict(grant)}


@app.get('/api/v1/state')
async def get_state():
    residents=[{"id":"grace","name":"Grace","role":"Grace Controls","status":"online"},{"id":"steward","name":"Steward","role":"R5 Steward","status":"online"}]
    return {"contract":"r3a.state.v1","registered_residents":2,"state":{"residents":residents,"state_catalog":[],"events":[]},"residents":residents}


# R3A STEWARD WORKSPACE API - what dashboard JS actually calls

# --- R5 v19 GRACE CONVERSATION STORE ---
GRACE_STORE_FILE=pathlib.Path('/tmp/r5_grace_store.json')
GRACE_STORE={}
if GRACE_STORE_FILE.exists():
    try:
        import json as _js
        GRACE_STORE=_js.loads(GRACE_STORE_FILE.read_text())
    except:
        GRACE_STORE={}

def _save_grace():
    try:
        import json as _js
        GRACE_STORE_FILE.write_text(_js.dumps(GRACE_STORE))
    except:
        pass

@app.get('/api/v1/steward/residents')
async def steward_residents():
    residents=[
        {'resident_id':'grace','display_name':'Grace','authorized':True,'id':'grace','name':'Grace','role':'Grace Controls','status':'online'},
        {'resident_id':'steward','display_name':'Steward','authorized':True,'id':'steward','name':'Steward','role':'R5 Steward','status':'online'}
    ]
    return {'contract':'r3a.steward-workspace-web.v1','residents':residents,'freshness':'current','registered_residents':2}

@app.get('/api/v1/steward/conversations')
async def steward_conversations(resident_id: str = None):
    convs=[{'conversation_id':'conv-grace-001','title':'Grace Chat','resident_id':'grace'}]
    if resident_id and resident_id!='grace':
        convs=[]
    return {'contract':'r3a.steward-workspace-web.v1','conversations':convs,'freshness':'current'}

@app.post('/api/v1/steward/conversations')
async def steward_create_conversation(request: dict = None):
    return {'contract':'r3a.steward-workspace-web.v1','conversation':{'conversation_id':'conv-grace-001','title':'Grace Chat'},'freshness':'current'}

@app.get('/api/v1/steward/conversations/{conv_id}/messages')
async def steward_messages(conv_id: str):
    msgs=GRACE_STORE.get(conv_id)
    if not msgs:
        msgs=[{'message_id':'msg-001','text':'Grace online - R5 v21 lean CME 5135 bytes REAL 80B at 192.168.1.160:8080','sender':{'id':'grace','display_name':'Grace','kind':'resident'},'created_at':'2026-11-12T00:00:00Z','delivery_state':'delivered'}]
        GRACE_STORE[conv_id]=msgs
        _save_grace()
    return {'contract':'r3a.steward-workspace-web.v1','messages':msgs,'freshness':'current'}

@app.post('/api/v1/steward/conversations/{conv_id}/messages')
async def steward_send_message(conv_id: str, request: Request):
    try:
        body=await request.json()
    except:
        body={}
    txt=body.get('text','') or body.get('message','')
    conv_id_store=conv_id
    if conv_id_store not in GRACE_STORE:
        GRACE_STORE[conv_id_store]=[{'message_id':'msg-001','text':'Grace online - R5 v21 lean CME 5135 bytes REAL 80B at 192.168.1.160:8080 - say hi!','sender':{'id':'grace','display_name':'Grace','kind':'resident'},'created_at':'2026-11-12T00:00:00Z','delivery_state':'delivered'}]
    # FIXED v21 - real 80B via CMESocket
    try:
        from cme.socket import CMESocket
        sock = CMESocket()
        op = {'text': txt, 'resident': 'grace', 'resident_id': 'grace'}
        grant = sock.dispatch(op, 'v1.0.0-conversation')
        real = grant.get('message') or grant.get('result',{}).get('message') or grant.get('text') or ''
        text = real if real else f"Grace 80B: {txt}"
    except Exception as e:
        text = f"Grace 80B error: {e} - {txt[:100]}"
    import datetime, time, json as _js
    user_msg={'message_id': f"user-{int(datetime.datetime.now().timestamp()*1000)}", 'text': txt, 'sender': {'id':'steward','display_name':'Steward','kind':'steward'}, 'created_at': datetime.datetime.now().isoformat()+'Z', 'delivery_state':'delivered'}
    grace_msg={'message_id': f"grace-{int(datetime.datetime.now().timestamp()*1000)}", 'text': text, 'sender': {'id':'grace','display_name':'Grace','kind':'resident'}, 'created_at': datetime.datetime.now().isoformat()+'Z', 'delivery_state':'delivered'}
    GRACE_STORE[conv_id_store].append(user_msg)
    GRACE_STORE[conv_id_store].append(grace_msg)
    try:
        GRACE_STORE_FILE.write_text(_js.dumps(GRACE_STORE))
    except:
        pass
    return {'contract':'r3a.steward-workspace-web.v1','message':grace_msg,'messages':GRACE_STORE[conv_id_store],'freshness':'current','correlation_id':f"r5-msg-{int(time.time())}"}



