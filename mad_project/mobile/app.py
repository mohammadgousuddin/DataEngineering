#!/usr/bin/env python3
"""
MAD mobile — PWA backend (port 8899).

Serves the installable mobile web app and a small API:

  GET  /api/status                    -> proxies wiring:8888/status (no CORS pain)
  GET  /api/services                  -> state of every MAD container
  POST /api/services/{name}/{action}  -> start | stop | restart one service
  POST /api/system/on                 -> start every MAD container
  POST /api/system/off                -> stop everything except this app + broker
  POST /api/mode/live                 -> stop simulator (use Flipper bridge)
  POST /api/mode/sim                  -> start simulator

Controls other containers through the mounted /var/run/docker.sock.
LAN-only by design — do NOT port-forward this to the internet.
"""
import os
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

try:
    import docker
    _docker = docker.from_env()
except Exception as e:  # docker SDK missing or socket not mounted
    _docker = None
    print(f"[mobile] docker control unavailable: {e}", flush=True)

STATUS_URL = os.environ.get("STATUS_URL", "http://wiring:8888/status")
STATIC = Path(__file__).resolve().parent / "static"

# All MAD containers, in sensible start order.
SERVICES = ["mosquitto", "influxdb", "ingestion", "control", "controller",
            "csv_logger", "dashboard", "wiring", "simulator"]
# Never stopped by "system off" (this app must stay reachable; broker keeps LWT sane).
PROTECTED = {"mobile", "mosquitto"}

app = FastAPI(title="MAD mobile")


# ---------- static / PWA ----------
@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


@app.get("/manifest.json")
def manifest():
    return FileResponse(str(STATIC / "manifest.json"))


@app.get("/sw.js")
def sw():
    return FileResponse(str(STATIC / "sw.js"), media_type="application/javascript")


@app.get("/icon-192.png")
def icon192():
    return FileResponse(str(STATIC / "icon-192.png"))


@app.get("/icon-512.png")
def icon512():
    return FileResponse(str(STATIC / "icon-512.png"))


# ---------- pipeline status ----------
@app.get("/api/status")
def status():
    try:
        r = requests.get(STATUS_URL, timeout=4)
        return JSONResponse(r.json())
    except Exception as e:
        return JSONResponse({"backend": False, "live": False, "error": str(e)})


# ---------- docker control ----------
def _container(name):
    if _docker is None:
        raise HTTPException(503, "docker control unavailable (socket not mounted?)")
    try:
        return _docker.containers.get(name)
    except Exception:
        raise HTTPException(404, f"container '{name}' not found")


@app.get("/api/services")
def services():
    if _docker is None:
        return {"available": False, "services": []}
    out = []
    for name in SERVICES:
        try:
            c = _docker.containers.get(name)
            out.append({"name": name, "status": c.status})
        except Exception:
            out.append({"name": name, "status": "missing"})
    return {"available": True, "services": out}


@app.post("/api/services/{name}/{action}")
def service_action(name: str, action: str):
    if name not in SERVICES:
        raise HTTPException(400, f"unknown service '{name}'")
    if action not in ("start", "stop", "restart"):
        raise HTTPException(400, f"unknown action '{action}'")
    if action == "stop" and name in PROTECTED:
        raise HTTPException(400, f"'{name}' is protected")
    c = _container(name)
    getattr(c, action)()
    return {"ok": True, "name": name, "action": action}


@app.post("/api/system/on")
def system_on():
    done = []
    for name in SERVICES:
        try:
            c = _container(name)
            if c.status != "running":
                c.start()
                done.append(name)
        except HTTPException:
            continue
    return {"ok": True, "started": done}


@app.post("/api/system/off")
def system_off():
    done = []
    for name in reversed(SERVICES):
        if name in PROTECTED:
            continue
        try:
            c = _container(name)
            if c.status == "running":
                c.stop(timeout=8)
                done.append(name)
        except HTTPException:
            continue
    return {"ok": True, "stopped": done}


@app.post("/api/mode/live")
def mode_live():
    c = _container("simulator")
    if c.status == "running":
        c.stop(timeout=8)
    return {"ok": True, "mode": "live",
            "note": "now run `python3 sensor_bridge.py` on the host"}


@app.post("/api/mode/sim")
def mode_sim():
    c = _container("simulator")
    if c.status != "running":
        c.start()
    return {"ok": True, "mode": "simulator"}
