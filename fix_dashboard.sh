#!/usr/bin/env bash
#
# fix_dashboard.sh — patch legacy Dash entrypoints.
#
# Newer Dash (>= 2.16) removed app.run_server in favour of app.run. This stack
# already uses app.run, so this script is a safety net if you swap in an older
# dashboard/app.py that still calls run_server.
#
set -euo pipefail
cd "$(dirname "$0")/mad_project"

APP="dashboard/app.py"
if [ ! -f "$APP" ]; then
  echo "[!] $APP not found"
  exit 1
fi

if grep -q "app.run_server" "$APP"; then
  sed -i 's/app\.run_server/app.run/g' "$APP"
  echo "[+] patched app.run_server -> app.run in $APP"
else
  echo "[=] $APP already uses app.run — nothing to do"
fi

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

echo "[+] rebuilding dashboard container ..."
$DC up -d --build dashboard
echo "[+] done — http://localhost:8050"
