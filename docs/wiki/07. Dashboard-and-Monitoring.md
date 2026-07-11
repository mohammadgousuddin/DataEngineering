# Dashboard and Monitoring

Three live windows into the same pipeline — all honest by design: when telemetry stops, they say **"WAITING FOR LIVE DATA"** rather than showing stale or fake numbers.

## Dashboard — http://localhost:8050

Dark Kali/Flipper-themed Plotly Dash app. A background MQTT thread keeps a rolling **90-sample history** of `greenhouse/sensor` plus the latest `greenhouse/command` and `greenhouse/bridge`; the UI refreshes every **2 s**. Telemetry counts as live only if the last frame is **< 12 s** old.

| Panel | Contents | Behaviour |
|---|---|---|
| **Top badges** | SOURCE, FLIPPER, MQTT, INFLUX, CSV rows, UTC | source dot green = flipper, grey = simulator; the FLIPPER badge trusts only the retained `greenhouse/bridge` status (stale after 30 s) |
| **Sensor telemetry** | 6 gauges: air temp, probe temp, RH, soil, CO₂, light | green/amber/red band zones and threshold needles recomputed from the *current* slider values |
| **Trends** | 4 sparklines (temp, RH, CO₂, soil) over the last 90 samples | red markers on every sample that violates a threshold |
| **Actuators · Random Forest** | FAN and IRRIGATION PUMP pills + trigger causes (e.g. `AIR ≥ 40°C · CO₂ ≥ 900`) | pills follow the operator thresholds; the `RF MODEL ▸` row shows the model's recommendation, `decided_by`, and fan/pump confidence from `greenhouse/command` |
| **Derived metrics** | heat index, VPD (ideal 0.8–1.2 kPa), cross-sensor Δ | VPD flagged IDEAL/LOW/HIGH; Δ amber > 1.5 °C, red > 5 °C |
| **Threshold override** | 5 sliders: fan temp / fan CO₂ / fan RH / pump soil / pump temp | live operator retuning — gauges, violation markers, pills and causes all re-colour instantly |
| **Footer** | frames received, broker address, LIVE/WAITING | |

## Wiring page — http://localhost:8888

- `GET /` — animated breadboard + Flipper Zero schematic mirroring the physical wiring ([[Hardware and Wiring]]). Polls status every ~1.3 s: wires pulse green while data flows; red "waiting" when it stops.
- `GET /status` — machine-readable pipeline health:

```json
{"backend": true, "live": true, "mqtt": true, "source": "flipper",
 "age": 2.1, "msgs": 1284, "uptime": 5321,
 "flipper": {"connected": true, "port": "/dev/ttyACM0", "reason": "serial open"},
 "sensor": {"temp_dht": 38.4, "delta": 0.27},
 "command": {"fan_state": "ON", "pump_state": "OFF", "recommended_action": "open_fan"}}
```

Flipper `connected` is primarily the retained bridge status (< 30 s old); live frames tagged `source: "flipper"` also count as proof of life.

## InfluxDB UI — http://localhost:8086

Login `mad` / `madpassword` (token `my-token`). Flux explorer over the `greenhouse` bucket, measurement `telemetry`, tags `source` and `ds_status`. Useful for ad-hoc time-series analysis beyond the dashboard's 90-sample window.

## Command-line monitoring

```bash
docker exec -it mosquitto mosquitto_sub -h localhost -p 1885 -t "greenhouse/#" -v  # raw stream
cd mad_project && docker compose ps                    # container status
docker compose logs -f dashboard                       # any service's logs
docker exec csv_logger sh -c 'wc -l /data/greenhouse.csv'   # corpus growth
curl -s localhost:8000/health                          # model loaded?
curl -s localhost:8888/status | python3 -m json.tool   # full pipeline health
```
