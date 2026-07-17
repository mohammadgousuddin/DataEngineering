#!/usr/bin/env python3
"""
MAD CSV logger.

Subscribes to greenhouse/sensor and greenhouse/command, merges the latest
actuator state with each sensor reading, computes the derived metrics (heat
index, VPD, cross-sensor temp delta), and appends a complete snapshot row to
greenhouse.csv in real time. The file is append-only — never re-read.

CSV schema (documentation §7.1):
  row_num, timestamp, date, time_utc,
  temp_dht, temp_ds18, temp_delta,
  humidity, soil_moisture, co2, light_intensity,
  heat_index, vpd_kpa,
  fan_state, pump_state,
  sensor_source, ds_status
"""
import csv
import json
import math
import os
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1885"))
CSV_PATH = os.environ.get("CSV_PATH", "/data/greenhouse.csv")

SENSOR_TOPIC = "greenhouse/sensor"
COMMAND_TOPIC = "greenhouse/command"

HEADER = [
    "row_num", "timestamp", "date", "time_utc",
    "temp_dht", "temp_ds18", "temp_delta",
    "humidity", "soil_moisture", "co2", "light_intensity",
    "heat_index", "vpd_kpa",
    "fan_state", "pump_state",
    "sensor_source", "ds_status",
]

_lock = threading.Lock()
_latest_command = {"fan_state": "OFF", "pump_state": "OFF"}
_row_num = 0


def heat_index_c(temp_c, rh):
    """Steadman / NWS Rothfusz regression, returned in degrees Celsius."""
    t_f = temp_c * 9.0 / 5.0 + 32.0
    # simple form for cooler conditions
    hi_f = 0.5 * (t_f + 61.0 + (t_f - 68.0) * 1.2 + rh * 0.094)
    if (hi_f + t_f) / 2.0 >= 80.0:
        hi_f = (-42.379 + 2.04901523 * t_f + 10.14333127 * rh
                - 0.22475541 * t_f * rh - 0.00683783 * t_f * t_f
                - 0.05481717 * rh * rh + 0.00122874 * t_f * t_f * rh
                + 0.00085282 * t_f * rh * rh - 0.00000199 * t_f * t_f * rh * rh)
    return round((hi_f - 32.0) * 5.0 / 9.0, 2)


def vpd_kpa(temp_c, rh):
    """Vapour Pressure Deficit (kPa) = es - ea."""
    es = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))
    ea = es * (rh / 100.0)
    return round(es - ea, 3)


def ensure_header():
    new = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if new:
        with open(CSV_PATH, "w", newline="") as f:
            csv.writer(f).writerow(HEADER)
    else:
        # resume row numbering from existing file
        global _row_num
        with open(CSV_PATH) as f:
            _row_num = max(0, sum(1 for _ in f) - 1)


def write_row(sensor):
    global _row_num
    now = datetime.now(timezone.utc)
    temp_dht = float(sensor.get("temp_dht", 0.0))
    temp_ds18 = float(sensor.get("temp_ds18", temp_dht))
    humidity = float(sensor.get("humidity", 0.0))

    with _lock:
        cmd = dict(_latest_command)
        _row_num += 1
        row = [
            _row_num,
            f"{now.timestamp():.3f}",
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            round(temp_dht, 2),
            round(temp_ds18, 2),
            round(abs(temp_dht - temp_ds18), 2),
            round(humidity, 2),
            round(float(sensor.get("soil_moisture", 0.0)), 2),
            round(float(sensor.get("co2", 0.0)), 1),
            round(float(sensor.get("light_intensity", 0.0)), 1),
            heat_index_c(temp_dht, humidity),
            vpd_kpa(temp_dht, humidity),
            cmd.get("fan_state", "OFF"),
            cmd.get("pump_state", "OFF"),
            sensor.get("source", "unknown"),
            sensor.get("ds_status", "ok"),
        ]
        with open(CSV_PATH, "a", newline="") as f:
            csv.writer(f).writerow(row)
    return _row_num


def _on_connect(client, userdata, flags, rc):
    client.subscribe([(SENSOR_TOPIC, 1), (COMMAND_TOPIC, 1)])
    print(f"[csv_logger] subscribed sensor+command (rc={rc}) -> {CSV_PATH}", flush=True)


def _on_message(client, userdata, msg):
    global _latest_command
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        if msg.topic == COMMAND_TOPIC:
            with _lock:
                _latest_command = {
                    "fan_state": data.get("fan_state", "OFF"),
                    "pump_state": data.get("pump_state", "OFF"),
                }
        elif msg.topic == SENSOR_TOPIC:
            n = write_row(data)
            if n % 10 == 0:
                print(f"[csv_logger] {n} rows", flush=True)
    except Exception as e:
        print(f"[csv_logger] error: {e}", flush=True)


def main():
    ensure_header()
    client = mqtt.Client(client_id="csv_logger")
    client.on_connect = _on_connect
    client.on_message = _on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            print(f"[csv_logger] waiting for broker ({e})", flush=True)
            time.sleep(2)
    client.loop_forever()


if __name__ == "__main__":
    main()
