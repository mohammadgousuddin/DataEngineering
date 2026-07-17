#!/usr/bin/env python3
"""
MAD wiring + connection status service  (port 8888).

Serves a graphical breadboard / Flipper Zero wiring diagram that reflects the
LIVE pipeline state. A background MQTT subscriber tracks greenhouse/sensor and
greenhouse/command; the page polls GET /status every ~1.3s and lights up the
wiring (animated, green) when data is flowing or shows a red "waiting" state
when it is not.

  GET /        -> wiring diagram page
  GET /status  -> JSON pipeline/connection status
"""
import json
import os
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1885"))
SENSOR_TOPIC = "greenhouse/sensor"
COMMAND_TOPIC = "greenhouse/command"
BRIDGE_TOPIC = "greenhouse/bridge"
STALE_S = 12.0
BRIDGE_STALE_S = 30.0

HERE = Path(__file__).resolve().parent
INDEX = HERE / "static" / "index.html"

_lock = threading.Lock()
_state = {
    "mqtt": False,
    "sensor": None,
    "command": None,
    "bridge": None,
    "bridge_rx": 0.0,
    "last_rx": 0.0,
    "msgs": 0,
    "started": time.time(),
}

app = FastAPI(title="MAD wiring status")


def _on_connect(client, userdata, flags, rc):
    _state["mqtt"] = rc == 0
    client.subscribe([(SENSOR_TOPIC, 1), (COMMAND_TOPIC, 1), (BRIDGE_TOPIC, 1)])
    print(f"[wiring] subscribed (rc={rc})", flush=True)


def _on_disconnect(client, userdata, rc):
    _state["mqtt"] = False


def _on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        with _lock:
            if msg.topic == SENSOR_TOPIC:
                _state["sensor"] = data
                _state["last_rx"] = time.time()
                _state["msgs"] += 1
            elif msg.topic == COMMAND_TOPIC:
                _state["command"] = data
            elif msg.topic == BRIDGE_TOPIC:
                _state["bridge"] = data
                _state["bridge_rx"] = time.time()
    except Exception as e:
        print(f"[wiring] msg error: {e}", flush=True)


def _mqtt_thread():
    client = mqtt.Client(client_id="wiring")
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            print(f"[wiring] waiting for broker ({e})", flush=True)
            time.sleep(2)
    client.loop_forever()


@app.on_event("startup")
def _startup():
    threading.Thread(target=_mqtt_thread, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(str(INDEX))


@app.get("/status")
def status():
    with _lock:
        sensor = dict(_state["sensor"]) if _state["sensor"] else None
        command = dict(_state["command"]) if _state["command"] else None
        bridge = dict(_state["bridge"]) if _state["bridge"] else None
        bridge_rx = _state["bridge_rx"]
        mqtt_ok = _state["mqtt"]
        last_rx = _state["last_rx"]
        msgs = _state["msgs"]
        started = _state["started"]

    now = time.time()
    age = (now - last_rx) if last_rx else None
    live = sensor is not None and age is not None and age < STALE_S
    source = (sensor or {}).get("source") if live else None

    # --- authoritative Flipper-connection status ---
    # Primary signal: the explicit retained greenhouse/bridge message published
    # by sensor_bridge.py on the host. Fallback: live frames tagged source=flipper.
    bridge_fresh = bridge is not None and (now - bridge_rx) < BRIDGE_STALE_S
    flipper_connected = bool(bridge_fresh and bridge.get("connected"))
    if live and source == "flipper":
        flipper_connected = True
    flipper_port = (bridge or {}).get("port") if bridge_fresh else None
    flipper_reason = (bridge or {}).get("reason") if bridge_fresh else "bridge not running"

    delta = None
    if live and sensor and "temp_dht" in sensor and "temp_ds18" in sensor:
        delta = round(abs(float(sensor["temp_dht"]) - float(sensor["temp_ds18"])), 2)

    return JSONResponse({
        "backend": True,
        "live": live,
        "mqtt": mqtt_ok,
        "source": source,
        "age": round(age, 1) if age is not None else None,
        "msgs": msgs,
        "uptime": round(now - started, 0),
        "flipper": {
            "connected": flipper_connected,
            "port": flipper_port,
            "reason": flipper_reason,
        },
        "sensor": {
            "temp_dht": (sensor or {}).get("temp_dht"),
            "temp_ds18": (sensor or {}).get("temp_ds18"),
            "humidity": (sensor or {}).get("humidity"),
            "soil_moisture": (sensor or {}).get("soil_moisture"),
            "co2": (sensor or {}).get("co2"),
            "light_intensity": (sensor or {}).get("light_intensity"),
            "ds_status": (sensor or {}).get("ds_status"),
            "delta": delta,
        } if live else None,
        "command": {
            "fan_state": (command or {}).get("fan_state", "OFF"),
            "pump_state": (command or {}).get("pump_state", "OFF"),
            "recommended_action": (command or {}).get("recommended_action", "idle"),
        } if (live and command) else None,
    })
