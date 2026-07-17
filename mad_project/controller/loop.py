#!/usr/bin/env python3
"""
MAD controller loop.

Subscribes to greenhouse/sensor, forwards each reading to the control service
(POST /predict), and republishes the recommended actuator state to
greenhouse/command (QoS 1). The dashboard and csv_logger consume the command.
"""
import json
import os
import time

import paho.mqtt.client as mqtt
import requests

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1885"))
CONTROL_URL = os.environ.get("CONTROL_URL", "http://control:8000")

SENSOR_TOPIC = "greenhouse/sensor"
COMMAND_TOPIC = "greenhouse/command"
FEATURES = ["temp_dht", "temp_ds18", "humidity", "soil_moisture", "co2", "light_intensity"]


def _predict(reading):
    payload = {f: float(reading.get(f, 0.0)) for f in FEATURES}
    r = requests.post(f"{CONTROL_URL}/predict", json=payload, timeout=5)
    r.raise_for_status()
    return r.json()


def _on_connect(client, userdata, flags, rc):
    client.subscribe(SENSOR_TOPIC, qos=1)
    print(f"[controller] subscribed {SENSOR_TOPIC} (rc={rc})", flush=True)


def _on_message(client, userdata, msg):
    try:
        reading = json.loads(msg.payload.decode("utf-8"))
        result = _predict(reading)
        act = result["actuator"]
        command = {
            "ts": time.time(),
            "fan_state": act["fan_state"],
            "pump_state": act["pump_state"],
            "recommended_action": result.get("recommended_action", "idle"),
            "confidence": result.get("confidence", {}),
            "decided_by": result.get("decided_by", "model"),
        }
        client.publish(COMMAND_TOPIC, json.dumps(command), qos=1)
        print(f"[controller] fan={command['fan_state']} pump={command['pump_state']} "
              f"action={command['recommended_action']}", flush=True)
    except requests.RequestException as e:
        print(f"[controller] control service error: {e}", flush=True)
    except Exception as e:
        print(f"[controller] error: {e}", flush=True)


def main():
    client = mqtt.Client(client_id="controller")
    client.on_connect = _on_connect
    client.on_message = _on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            print(f"[controller] waiting for broker ({e})", flush=True)
            time.sleep(2)
    client.loop_forever()


if __name__ == "__main__":
    main()
