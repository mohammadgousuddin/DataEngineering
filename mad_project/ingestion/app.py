#!/usr/bin/env python3
"""
MAD ingestion service.

FastAPI app with a background MQTT subscriber thread. Each greenhouse/sensor
message is parsed and written to InfluxDB as a `telemetry` measurement point with
millisecond precision. Synchronous writes (write_options=SYNCHRONOUS) favour
reliability over throughput.

Health: GET /health   Stats: GET /stats
"""
import json
import os
import threading
import time

import paho.mqtt.client as mqtt
from fastapi import FastAPI
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1885"))
INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "my-token")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "mad")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "greenhouse")

TOPIC = "greenhouse/sensor"
FIELDS = ["temp_dht", "temp_ds18", "humidity", "soil_moisture", "co2", "light_intensity"]

app = FastAPI(title="MAD ingestion")
_state = {"written": 0, "errors": 0, "last": None, "connected": False}

_influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
_write = _influx.write_api(write_options=SYNCHRONOUS)


def _write_point(data):
    source = str(data.get("source", "unknown"))
    point = Point("telemetry").tag("source", source)
    if data.get("ds_status"):
        point = point.tag("ds_status", str(data["ds_status"]))
    for f in FIELDS:
        if f in data and data[f] is not None:
            point = point.field(f, float(data[f]))
    point = point.time(time.time_ns(), WritePrecision.NS)
    _write.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)


def _on_connect(client, userdata, flags, rc):
    _state["connected"] = rc == 0
    client.subscribe(TOPIC, qos=1)
    print(f"[ingestion] subscribed {TOPIC} (rc={rc})", flush=True)


def _on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        _write_point(data)
        _state["written"] += 1
        _state["last"] = data
    except Exception as e:
        _state["errors"] += 1
        print(f"[ingestion] error: {e}", flush=True)


def _mqtt_loop():
    client = mqtt.Client(client_id="ingestion")
    client.on_connect = _on_connect
    client.on_message = _on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            print(f"[ingestion] waiting for broker ({e})", flush=True)
            time.sleep(2)
    client.loop_forever()


@app.on_event("startup")
def _startup():
    threading.Thread(target=_mqtt_loop, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "mqtt_connected": _state["connected"]}


@app.get("/stats")
def stats():
    return {"written": _state["written"], "errors": _state["errors"], "last": _state["last"]}
