# R5 Website Auth Setup

## Question: Does website have login? What are credentials?

**Answer:** No credentials existed in previous zips - now added in v6. Not handled at nginx level, so added to website itself.

### Method - Centralized Config Without Rewriting Core

**Two methods - both work, file method preferred:**

1. **File method (recommended):** `secrets/auth.json` with bcrypt hash
   - Created via `services/setup-auth.sh`
   - Permissions 600, not in git
   - Read by website/server.py verify_auth()

2. **Env var method:** `R5_WEBSITE_USERNAME` / `R5_WEBSITE_PASSWORD` in systemd service
   - Edit `services/r5-website.service` add Environment lines
   - daemon-reload + restart

**Initial setup tomorrow AM:**
```bash
cd /opt/riverview/r5-full
pip install passlib bcrypt fastapi uvicorn --quiet
./services/setup-auth.sh
# Enter username: steward
# Enter password: ****
# Creates secrets/auth.json

sudo systemctl restart r5-website
curl -u steward:pass http://127.0.0.1:18304/api/status
# Should return auth.configured: true
```

**External access:**
- https://192.168.1.155/r5/ -> browser prompts Basic Auth realm="Riverview 5 - Steward Access"
- Enter steward + password from setup-auth.sh
- Behind 443 proxy, so HTTPS encrypted

**If you skip setup:**
- Auth returns None -> website allows open but logs warning "Setup Required"
- For initial testing behind localhost it's okay, but for LAN/Internet you must run setup-auth.sh

**Security:**
- Password never stored plaintext - only bcrypt hash in auth.json
- auth.json chmod 600
- Not committed to git (.gitignore includes secrets/)
- Steward identity per R3A_STEWARD_NATIVE_IDENTITY.md - Office persists, Occupant replaceable
