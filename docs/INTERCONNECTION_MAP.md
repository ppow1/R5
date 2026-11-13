# Interconnection Map - Where BLOCKED Lived

R3A files:
cme.py 197,818 bytes 18 BLOCKED IMPORTS grace_module, db, notifications, capability_contracts, module_contracts
grace_module.py 85,340 36 BLOCKED IMPORTS cme, db, workflow
db.py 113,512 23 BLOCKED IMPORTS everything - god object
module_contracts.py 5,427 0 BLOCKED CLEAN - target

Circle: cme -> grace -> db -> cme = deadlock causing Vicky stall yellow dot

R5 fix:
- db = dumb append-only ledger
- cme/socket.py = 1.9KB router 3 methods
- grace = reads registries
- Helen Waite hr/security_levels.json holds whitelist/blacklist/budget
- Ingrid firewall reads hr file
- task_class branching fixes conversation vs engineering

Parking lots: hints/ + docs/ punch lists pushing context window -> move to r5/docs/PARKING_LOT.md single file

Process graphs: every capability had flow chart in R2 - keep as capabilities.json process_graph field text->validate->slice->stl
