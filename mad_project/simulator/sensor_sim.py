#!/usr/bin/env python3
"""
MAD fallback simulator.

Publishes synthetic UAE-greenhouse telemetry to greenhouse/sensor (QoS 1) every
SIM_PERIOD seconds, using the documented sinusoidal climate model. Runs by default
so the dashboard has data immediately; stop it to use the real Flipper bridge:

    docker compose stop simulator
"""
import json
import math
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1885"))
PERIOD = float(os.environ.get("SIM_PERIOD", "5"))
TOPIC = "greenhouse/sensor"


def climate(now=None):
    now = now or datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0 + now.second / 3600.0
    s = math.sin(2.0 * math.pi * h / 24.0)

    temp_dht = 7.0 * s + 36.0 + random.gauss(0, 0.35)
    humidity = max(0.0, min(100.0, 12.0 * s + 28.0 + random.gauss(0, 1.5)))
    soil = max(0.0, min(100.0, 10.0 * s + 32.0 + random.gauss(0, 2)))
    co2 = max(0.0, 280.0 * s + 420.0 + random.gauss(0, 12))
    light = max(0.0, 5500.0 * s + 5500.0 + random.gauss(0, 180))
    temp_ds18 = temp_dht + random.gauss(0, 0.4)

    return {
        "ts": time.time(),
        "temp_dht": round(temp_dht, 2),
        "temp_ds18": round(temp_ds18, 2),
        "humidity": round(humidity, 2),
        "soil_moisture": round(soil, 2),
        "co2": round(co2, 1),
        "light_intensity": round(light, 1),
        "source": "simulator",
        "ds_status": "ok",
    }


def main():
    client = mqtt.Client(client_id="simulator")
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            print(f"[sim] waiting for broker {MQTT_HOST}:{MQTT_PORT} ({e})", flush=True)
            time.sleep(2)
    client.loop_start()
    print(f"[sim] publishing to {TOPIC} every {PERIOD}s", flush=True)

    while True:
        payload = climate()
        client.publish(TOPIC, json.dumps(payload), qos=1)
        print(f"[sim] {payload['temp_dht']}C {payload['humidity']}%RH "
              f"soil={payload['soil_moisture']}% co2={payload['co2']}", flush=True)
        time.sleep(PERIOD)


if __name__ == "__main__":
    main()
