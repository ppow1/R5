#!/bin/bash
# R5 Install - tomorrow AM
set -e
echo "=== Riverview 5 Install ==="
echo "System D = Ring Zero (bare metal guardian)"
echo "System B = D-Delta (CME runner on top of D)"
echo "Website = Listener service on :8080"

# Copy services to systemd (Linux) or create launchd (macOS) or task scheduler (Windows)
if [ -d /etc/systemd/system ]; then
  echo "Installing systemd services..."
  sudo cp services/r5-ring0.service /etc/systemd/system/
  sudo cp services/r5-ddelta.service /etc/systemd/system/
  sudo cp services/r5-website.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable r5-ring0 r5-ddelta r5-website
  sudo systemctl start r5-ring0 r5-ddelta r5-website
  echo "Services started - check: systemctl status r5-*"
  echo "Dashboard: http://localhost:8080"
else
  echo "No systemd - running directly (Windows/dev):"
  echo "  python system_d/ring0.py &"
  echo "  python system_b/d_delta.py &"
  echo "  python3 website/server.py"
  python3 -m pip install fastapi uvicorn --quiet
  python3 website/server.py
fi

echo "Gate check:"
python3 tools/modularity-gate.py && echo "PASS - lean gate"
