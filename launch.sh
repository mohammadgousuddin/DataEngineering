#!/usr/bin/env bash
#
# MAD launch — bring up the full Docker Compose stack.
#
set -euo pipefail
cd "$(dirname "$0")/mad_project"

# pick the available compose command
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "[!] Docker Compose not found. Install docker-compose-plugin (README §1)."
  exit 1
fi

echo "[+] bash launch.sh"
echo "[+] Building 8 services with $DC ..."
$DC up -d --build

echo "[+] Waiting for services to settle ..."
sleep 6
$DC ps

cat <<'EOF'

[+] MAD stack is up.
    Dashboard : http://localhost:8050
    Wiring    : http://localhost:8888   (breadboard + Flipper connection status)
    InfluxDB  : http://localhost:8086   (org: mad  bucket: greenhouse  token: my-token)
    MQTT      : localhost:1885

[i] Fallback simulator is running so you see data immediately.
    To switch to real sensors:
        cd mad_project && docker compose stop simulator && cd ..
        python3 sensor_bridge.py

    Stop everything:  cd mad_project && docker compose down
EOF
