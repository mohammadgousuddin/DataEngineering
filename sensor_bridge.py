#!/usr/bin/env python3
"""
MAD sensor bridge (HOST side).
 
Reads the JSON telemetry stream the Flipper Zero prints over USB-CDC, validates
it, normalises it to the MAD schema, augments the fields the DHT22/DS18B20 cannot
physically measure (soil_moisture, co2, light_intensity) from the UAE climate
model, and publishes it to MQTT topic `greenhouse/sensor` (QoS 1).
 
Run on the Kali host (NOT in a container) after stopping the simulator:
    cd mad_project && docker compose stop simulator && cd ..
    python3 sensor_bridge.py
 
Requires: pyserial, paho-mqtt, numpy
"""
import glob
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
 
try:
    import serial  # pyserial
except ImportError:
    print("[!] pyserial missing -> pip3 install --user pyserial")
    sys.exit(1)
 
import paho.mqtt.client as mqtt
 
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1885"))
TOPIC = "greenhouse/sensor"
BRIDGE_TOPIC = "greenhouse/bridge"   # explicit Flipper-connection status (retained)
SERIAL_PORT = os.environ.get("SERIAL_PORT", "")  # empty = auto-detect
BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))
 
# Validation bounds (documentation §5.1)
DHT_MIN, DHT_MAX = -40.0, 80.0
HUM_MIN, HUM_MAX = 0.0, 100.0
DS_MIN, DS_MAX = -55.0, 125.0
DELTA_WARN = 5.0
 
 
def augment(now=None):
    """Synthesise soil_moisture / co2 / light_intensity from the UAE climate model."""
    now = now or datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0
    s = math.sin(2.0 * math.pi * h / 24.0)
    soil = max(0.0, min(100.0, 10.0 * s + 32.0 + random.gauss(0, 2)))
    co2 = max(0.0, 280.0 * s + 420.0 + random.gauss(0, 12))
    light = max(0.0, 5500.0 * s + 5500.0 + random.gauss(0, 180))
    return round(soil, 2), round(co2, 1), round(light, 1)
 
 
def find_port():
    if SERIAL_PORT:
        return SERIAL_PORT
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/flipper*"):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None
 
 
def validate(raw):
    """Range-check the Flipper payload; return (ok, reason)."""
    try:
        t = float(raw["temp_dht"])
        h = float(raw["humidity"])
    except (KeyError, TypeError, ValueError):
        return False, "missing temp_dht/humidity"
    if not (DHT_MIN <= t <= DHT_MAX):
        return False, f"temp_dht {t} out of range"
    if not (HUM_MIN <= h <= HUM_MAX):
        return False, f"humidity {h} out of range"
    ds = raw.get("temp_ds18")
    if ds is not None:
        ds = float(ds)
        if not (DS_MIN <= ds <= DS_MAX):
            return False, f"temp_ds18 {ds} out of range"
    return True, ""
 
 
def build_payload(raw):
    temp_dht = round(float(raw["temp_dht"]), 2)
    humidity = round(float(raw["humidity"]), 2)
    ds_status = raw.get("ds_status", "ok")
    if raw.get("temp_ds18") is None:
        temp_ds18 = temp_dht  # DS18B20 fallback to DHT22 temperature
        ds_status = "fallback"
    else:
        temp_ds18 = round(float(raw["temp_ds18"]), 2)
 
    delta = abs(temp_dht - temp_ds18)
    if delta > DELTA_WARN:
        print(f"  [warn] cross-sensor delta {delta:.1f}C > {DELTA_WARN}C", file=sys.stderr)
 
    soil, co2, light = augment()
    return {
        "ts": time.time(),
        "temp_dht": temp_dht,
        "temp_ds18": temp_ds18,
        "humidity": humidity,
        "soil_moisture": soil,
        "co2": co2,
        "light_intensity": light,
        "source": "flipper",
        "ds_status": ds_status,
    }
 
 
def publish_bridge(client, connected, port=None, reason=""):
    """Publish the explicit Flipper-connection status (retained, QoS 1).
 
    This is the AUTHORITATIVE 'is the Flipper connected?' signal. The dashboard
    and wiring services run inside Docker and cannot see the host /dev/ttyACM0,
    so they rely on this message instead of trying to glob the device file.
    """
    payload = {
        "connected": bool(connected),
        "port": port,
        "reason": reason,
        "ts": time.time(),
    }
    client.publish(BRIDGE_TOPIC, json.dumps(payload), qos=1, retain=True)
    print(f"[bridge] Published status: connected={connected} port={port} reason={reason}",
          file=sys.stderr)
 
 
def main():
    client = mqtt.Client(client_id="sensor_bridge")
    # Last Will: if this process dies or the cable is yanked, the broker auto-
    # publishes 'disconnected' so every dashboard flips to NOT CONNECTED.
    client.will_set(
        BRIDGE_TOPIC,
        json.dumps({"connected": False, "port": None,
                    "reason": "bridge offline (last will)", "ts": time.time()}),
        qos=1, retain=True,
    )
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    print(f"[+] MQTT connected {MQTT_HOST}:{MQTT_PORT} -> {TOPIC}")
    publish_bridge(client, False, reason="starting")
 
    announced_port = None
    while True:
        port = find_port()
        if not port:
            if announced_port is not None:
                announced_port = None
            publish_bridge(client, False, port=None, reason="no serial device found")
            print("[..] waiting for Flipper on /dev/ttyACM* | /dev/ttyUSB* | /dev/flipper* ...")
            time.sleep(2)
            continue
        try:
            print(f"[+] opening serial {port} @ {BAUD}")
            with serial.Serial(port, BAUD, timeout=5) as ser:
                announced_port = port
                publish_bridge(client, True, port=port, reason="serial open")
                print(f"[+] FLIPPER CONNECTED on {port} -> greenhouse/bridge")
                while True:
                    line = ser.readline().decode("utf-8", "ignore").strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # skip boot banners / partial frames
                    ok, reason = validate(raw)
                    if not ok:
                        print(f"  [drop] {reason}", file=sys.stderr)
                        continue
                    payload = build_payload(raw)
                    client.publish(TOPIC, json.dumps(payload), qos=1)
                    print(f"  -> {payload['temp_dht']}C  {payload['humidity']}%RH  "
                          f"ds={payload['temp_ds18']}C ({payload['ds_status']})")
        except serial.SerialException as e:
            announced_port = None
            publish_bridge(client, False, port=port, reason=f"serial error: {e}")
            print(f"[!] serial error on {port}: {e} — retrying", file=sys.stderr)
            time.sleep(2)
        except KeyboardInterrupt:
            break
 
    publish_bridge(client, False, reason="bridge stopped")
    client.loop_stop()
    client.disconnect()
    print("\n[+] bridge stopped")
 
 
if __name__ == "__main__":
    main()
