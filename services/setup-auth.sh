#!/bin/bash
# services/setup-auth.sh - Initial credentials setup for R5 website
# Creates secrets/auth.json with bcrypt hash - centralized config without rewriting core
set -e
BASE="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_DIR="$BASE/secrets"
AUTH_FILE="$SECRETS_DIR/auth.json"

echo "=== Riverview 5 - Initial Steward Credentials Setup ==="
echo "This creates password protection for https://192.168.1.155/r5/"
echo "Auth method: Basic Auth via secrets/auth.json (bcrypt) or env vars"
echo ""

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

read -p "Enter steward username [steward]: " USERNAME
USERNAME=${USERNAME:-steward}

read -s -p "Enter password: " PASSWORD
echo ""
read -s -p "Confirm password: " PASSWORD2
echo ""

if [ "$PASSWORD" != "$PASSWORD2" ]; then
  echo "Passwords do not match"
  exit 1
fi

# Generate bcrypt hash via python
python3 -c "
from passlib.context import CryptContext
import json, pathlib
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
hash = pwd_context.hash('$PASSWORD')
data = {'username': '$USERNAME', 'password_hash': hash, 'note': 'Steward identity - see R3A_STEWARD_NATIVE_IDENTITY.md', 'created': '$(date -Iseconds)'}
path = pathlib.Path('$AUTH_FILE')
path.write_text(json.dumps(data, indent=2))
print(f'Created {path}')
"

chmod 600 "$AUTH_FILE"

echo ""
echo "Auth configured:"
echo "  File: $AUTH_FILE (600 permissions)"
echo "  Username: $USERNAME"
echo "  Hash: bcrypt"
echo ""
echo "Next:"
echo "  1. sudo systemctl restart r5-website"
echo "  2. Test: curl -u $USERNAME:YOUR_PASSWORD http://127.0.0.1:18304/api/status"
echo "  3. External: https://192.168.1.155/r5/ -> login prompt"
echo ""
echo "Alternative - env var method (for systemd):"
echo "  Edit services/r5-website.service add:"
echo "  Environment=R5_WEBSITE_USERNAME=$USERNAME"
echo "  Environment=R5_WEBSITE_PASSWORD=yourpassword"
echo "  Then systemctl daemon-reload && systemctl restart r5-website"
