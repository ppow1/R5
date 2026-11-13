# R5 Configuration Guide - Centralized Theme: Config Without Rewriting Core

## Core Principle You Told 150 Times
> Configuration without rewriting core was centralized theme
> Never hardcode bounded/demo/governance/safe_mode BLOCKED
> Make it configurable with autonomy:true default

## 1. Databases - What Exists and Where

### PostgreSQL is authoritative - R2 CORE_CONTRACT 1.0.1
Location: Configured via env var, not hardcoded

**Env vars (from config.example.json pattern you already use):**
```
R3A_TELEMETRY_DATABASE_DSN=postgresql://user:pass@localhost:5432/riverview
R3A_OCTOMINER_SSH_HOST=192.168.1.155
R3A_OCTOMINER_SSH_USER=riverview
R3A_OCTOMINER_IDENTITY_FILE=~/.ssh/id_rsa
R3A_OCTOMINER_KNOWN_HOSTS=~/.ssh/known_hosts
R3A_GRACE_REASONING_ENDPOINT=http://octominer1:8000/v1
R3A_GRACE_VISION_ENDPOINT=http://octominer2:8000/v1
R3A_GRACE_AUTONOMIC_ENDPOINT=http://camarillo:8000/v1
```

**Schemas (from your 18 migrations):**
- `001_ap0.sql` - Base, AP0 provisioning
- `002_event_ledger_append_only.sql` - Durable event bus: event_id, assignment_id, actor, schema_version, timestamp, correlation/causation, idempotency key, transactional state changes - **NEVER mutated, only appended**
- `003_reusable_leases_and_grants.sql` - Reusable leases for assignments, fair scheduling
- `004_grace_objectives.sql` - Grace Director Ops objectives, delegation
- `005-006` - Indexes: event_history_persisted_at_idx, activity_created_at_idx
- `007_capability_invocations.sql` - Capability calls ledger
- `008_activity_scoped_capability_grants.sql` - Per-activity grants
- `009_steward_sessions.sql` - Steward auth sessions
- `010_governed_knowledge.sql` - Knowledge assets 146 from dashboard
- `011_resident_dossiers.sql` - 13 residents (alyssa, grace, chloe, jessica, vicky, helen, ingrid, eleanor, marie, judy, cheryl, evelyn, gm)
- `012_character_context_pins.sql` - Context pins
- `013_context_pin_identity_provenance.sql` - Who pinned
- `014_context_pin_execution_profile.sql` - Execution profile
- `015_context_pin_authorization_scope.sql` - Auth scope
- `016_character_revision_retirement.sql` - Retirement
- `017_steward_conversations.sql` - Conversations lightweight ["respond helpfully"]
- `018_steward_identity.sql` - Identity

**R5 Usage - DB is dumb ledger, not business logic:**
- `cme/socket.py` does NOT import db.py directly - it calls protocol layer
- `system_d/ring0.py` writes health to event_ledger only, no logic
- `system_b/d_delta.py` reads from event_ledger via NOTIFY, dispatches via binding
- Business logic lives in `r5/registries/*.json` and `r5/hr/security_levels.json`, not in SQL

### Why R3 Broke:
- `db.py` 113,512 bytes 23 BLOCKED - became god object importing grace_module, cme, everything
- Should be: `r5/data/ledger.py` <5KB - only append and read, no imports from cme/grace

## 2. Centralized Configuration - All Config in One Place

### Pattern You Already Established: `config.example.json` + env vars + manifest

**Every plugin (from R4 Lean Draft):**
```
r3a_plugins/vicky/
  __init__.py 55 bytes
  manifest.json 3.62KB - declares r3a.module-manifest.v1@1.0.0, version major.minor.patch, deps range ~ ^ >= <=, execution_contract r3a.resident.module-binding 1.0.0
  plugin.py 181 bytes - activity handler only, imports r3a.resident.execution.v1, NOT cme.py, db.py, grace_module.py
  config.example.json 95 bytes - {"autonomy": true, "provider": "configurable", "retry_count": 3}
```

**R5 Equivalent:**
```
r5/
  registries/
    resources.json - hardware OctoMiner1 4xP100->8x 16GB 80B MoE, OctoMiner2 30B vision 7.5s, Camarillo N95 15W 0.6B, 3060Ti, 4090, 13.6TB SAS, 4x55" quad
    capabilities.json - capabilities with process_graph text->validate->slice->stl for Local CAD proven
    environments.json - castle 8 realms + Undercurrent veil + AA USB mode
  hr/security_levels.json - whitelist/blacklist/budget - Helen Waite owns, Ingrid firewall reads
  cme/socket.py - 3 methods, no hardcoded governance, reads registries
  system_d/ring0.py - reads registries/resources.json for hardware
  system_b/d_delta.py - reads capabilities.json for process_graph
  website/server.py - reads registries for ports 443/8303/8311/18303/18311/18304

Config changes: Edit JSON, restart service. No code rewrite.
```

### Config Files List - README for Tomorrow AM Install

1. `registries/resources.json` - Hardware, no code change needed to add GPU
2. `registries/capabilities.json` - Capabilities, add Local CAD or new model by adding JSON entry with manifest + execution_contract + process_graph
3. `registries/environments.json` - Spatial realms, add new portal by adding to castle array
4. `hr/security_levels.json` - Security: whitelist/blacklist/budget - Helen Waite holds, Ingrid reads - change here, not in code
5. `config.example.json` (root) - Env var templates: host_id, ssh_host, ssh_port, ssh_user, identity_file, known_hosts_file, timeout_seconds, model_servers grace-reasoning-80b, grace-vision-30b, grace-autonomic-0.6b, comfyui
6. `residents/*.v1.0.0.json` - 13 dossiers - each has manifest, execution_contract, v1.0.0-conversation ["respond helpfully"], role, spatial_realm, execution_profile hybrid/native, affinity variable/standard
7. `services/*.service` - systemd: r5-ring0.service (Ring Zero watcher), r5-cme.service (CME watcher + waterwheel), r5-website.service (127.0.0.1:18304 -> 443 proxy), r5-nginx.conf
8. `dashboard/index.html` - Panorama map from your 4 images: Architecture College Chloe, Operations Keep Grace #1, Research Grove Marie, Character Architecture Jessica, Engineering Foundry Vicky uses CAD, Records & Memory Hall Eleanor, Archives & Library Judy/Cheryl, Security Gatehouse Ingrid+Helen, Great Courtyard Alyssa gate, CME waterwheel
9. `tools/modularity-gate.py` - <5KB CI gate: fails if socket >15KB, manifest >5KB, hardcoded BLOCKED/bounded/demo/safe_mode

### How to Change Without Rewriting Core - Examples

- Add new hardware: Edit `registries/resources.json` hardware.octominer3 = {...}, restart r5-ring0 - no code
- Add new capability: Edit `registries/capabilities.json` new_cap = {manifest, execution_contract, process_graph}, restart r5-cme - no code
- Change security: Edit `hr/security_levels.json` whitelist add user - Ingrid firewall reads instantly - no code
- Change port: Edit `website/server.py` host/port + `services/r5-website.service` ExecStart + `services/r5-nginx.conf` upstream - restart services - no core rewrite
- Change resident: Edit `residents/grace.v1.0.0.json` role - restart - no code
- Change provider: Edit `config.example.json` model_servers base_url_env - restart - no code

### Database Read/Write in R5 Code

**R5 does NOT use db.py god object.** New pattern:

- `r5/data/ledger.py` (<5KB target, not yet built in v4, will be in v5):
```python
# Only two methods, no business logic
def append_event(event: dict): # INSERT INTO event_ledger
def read_events(since: timestamp): # SELECT * FROM event_ledger WHERE persisted_at > since
```

- `cme/socket.py` observe() calls ledger.append_event, not direct SQL
- `system_d/ring0.py` observe() writes health via ledger.append_event
- `system_b/d_delta.py` reads via ledger.read_events + PostgreSQL NOTIFY

**Schemas traced:** All 18 migrations located via your uploads - we have 001_ap0.sql in /mnt/data, rest referenced in R5_Best_Path_Synthesis.md and index.json. Need to restore full 18 from your Drive zips 56MB+9.9MB+28MB+54.9MB for complete DB.

## 3. Installation Tomorrow AM - Camrui 192.168.1.155:18304

Port status you gave:
- 443 HTTPS listener reverse proxy - KEEP
- 8303 In use
- 8311 In use
- 18303 Python website backend existing - KEEP
- 18311 Python backend existing - KEEP
- 18304 No listener -> NEW R5 lean dashboard

Config:
- Host: 192.168.1.155 Camrui
- Backend: 127.0.0.1:18304 bind localhost
- External: https://192.168.1.155/r5/ via 443 proxy - avoids exposing backend directly

Install steps in services/install.sh
