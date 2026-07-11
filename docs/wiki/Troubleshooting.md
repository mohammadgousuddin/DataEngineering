# Troubleshooting

## Hardware / Flipper

| Problem | Fix |
|---|---|
| **Dashboard shows "not connected" although the Flipper is plugged in** | Plugging in is not enough — the **host bridge** is what detects it. Run `python3 sensor_bridge.py` (after `docker compose stop simulator`). The bridge publishes the retained `greenhouse/bridge` status the moment it opens the serial port; that message is what the dashboard/wiring page read. Containers **cannot** see `/dev/ttyACM0`. |
| `/dev/ttyACM0` not found | VirtualBox: Devices → USB → Flipper Zero, then `./diagnose_flipper.sh` |
| Permission denied on serial | `sudo usermod -aG dialout $USER && newgrp dialout` |
| DS18B20 reads missing | Check the 4.7 kΩ pull-up on B3 and the 3V3/GND rails. The pipeline keeps running meanwhile — frames carry `ds_status: "fallback"` with the DHT22 temperature substituted. |
| Wild/impossible readings | The bridge drops out-of-range frames by design (`[drop] ...` in its output) — check wiring; a flaky data line without its pull-up is the usual culprit. |
| DHT22 vs DS18B20 disagree | Deltas > 5 °C log a bridge warning and show red in the dashboard's CROSS-SENSOR Δ metric. One sensor is misplaced (direct sun / touching soil) or failing. |

## Stack / Docker

| Problem | Fix |
|---|---|
| Docker permission denied | `sudo usermod -aG docker $USER && newgrp docker` |
| Dashboard blank / "WAITING FOR LIVE DATA" | No publisher: the simulator is stopped **and** the bridge isn't running — start one of them. Confirm with `mosquitto_sub -t "greenhouse/#" -v`. |
| `app.run_server` error in older Dash code | `bash fix_dashboard.sh` (current code already uses `app.run`; the script is a safety net) |
| Model file missing | `python3 generate_dataset.py --train`, or just restart `control` — it auto-trains at startup |
| `joblib` unpickle / sklearn version error | Host and container sklearn versions differ — train inside the stack: `docker compose exec control python /app/train.py` |
| Service keeps restarting | `docker compose logs <service>`; most services block-retry until the broker is up, so check mosquitto's health first (`docker compose ps`) |
| Port already in use (8050/8086/8888/1885/8000) | Another process owns it — `sudo lsof -i :8050`, stop it or remap the port in `docker-compose.yml` |

## Data / AI

| Problem | Fix |
|---|---|
| CSV not growing | `docker compose logs csv_logger`; verify sensor messages flow (`mosquitto_sub`), and that `./data` is writable |
| No rows in InfluxDB | `curl localhost:8086/health`; check `docker compose logs ingestion` and `/stats` for its error counter |
| RF decisions look wrong | Check `decided_by` in `greenhouse/command` — `"threshold"` means the model failed to load and rules are active; see `docker compose logs control` |
| Confidence always 1.0 | You're in threshold-fallback mode (see above) — thresholds are deterministic |
| Dashboard pills disagree with RF row | Expected: pills follow the **operator's slider thresholds**, the RF row shows the **model's** recommendation. They diverge when you move sliders away from the trained thresholds. |

## Diagnostic one-liners

```bash
mosquitto_sub -h localhost -p 1885 -t "greenhouse/#" -v     # is anything publishing?
curl -s localhost:8888/status | python3 -m json.tool         # full pipeline health JSON
curl -s localhost:8000/health                                # model loaded?
docker compose ps                                            # who's up?
./diagnose_flipper.sh                                        # serial port + permissions
```
