# Deployment and Operations

## Docker Compose stack

`bash launch.sh` builds and starts all 8 services (`docker compose up -d --build`). Notable compose design:

- **Shared MQTT config** via a YAML anchor (`x-mqtt-env`) injected into every service.
- **Health-checked broker**: mosquitto's healthcheck runs `mosquitto_sub` against `$SYS/#`; every service `depends_on` it. The controller additionally waits for the control API.
- **Persistence**: named volumes `mosquitto-data` and `influx-data`; bind mounts `./model` and `./data` shared between containers and host (so host-side training and in-container inference use the same `rf_control.pkl`, and the CSV is directly readable on the host).
- **`restart: unless-stopped`** on every service.

## Configuration — `mad_project/.env`

Copy from the committed example: `cp mad_project/.env.example mad_project/.env`.

| Variable | Default | Used by |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `mosquitto` / `1885` | all MQTT services |
| `INFLUX_URL` | `http://influxdb:8086` | ingestion |
| `INFLUX_TOKEN` / `INFLUX_ORG` / `INFLUX_BUCKET` | `my-token` / `mad` / `greenhouse` | ingestion, InfluxDB init |
| `MODEL_PATH` | `/model/rf_control.pkl` | control |
| `CSV_PATH` | `/data/greenhouse.csv` | csv_logger, dashboard |
| `CONTROL_URL` | `http://control:8000` | controller |
| `SERIAL_PORT` | `/dev/ttyACM0` | host-side `sensor_bridge.py` only (empty = auto-detect) |

Compose uses `${VAR:-default}` everywhere, so the stack even runs with no `.env` at all. Dev-only credentials — rotate them for anything beyond coursework.

## Operating modes

**Simulator (default)** — running immediately after `launch.sh`; the `simulator` container publishes every 5 s.

**Live hardware** — two commands, zero code changes:

```bash
cd mad_project && docker compose stop simulator && cd ..
python3 sensor_bridge.py
```

Back to simulator: stop the bridge (Ctrl-C), then `docker compose start simulator`.

## Day-to-day commands

```bash
cd mad_project
docker compose ps                        # status of all services
docker compose logs -f <service>         # follow logs (dashboard, control, ...)
docker compose restart <service>         # bounce one service
docker compose down                      # stop everything (state persists in volumes)
docker compose down -v                   # stop AND wipe broker/Influx state
docker cp csv_logger:/data/greenhouse.csv ./greenhouse_export.csv   # export corpus
docker compose exec control python /app/train.py                    # retrain inside the stack
```

## Model lifecycle

```bash
python3 generate_dataset.py --train                       # fresh synthetic model (host)
python3 generate_dataset.py --train --from-csv mad_project/data/greenhouse.csv  # retrain on live data
docker compose restart control                            # reload the new bundle
```

If host-side sklearn versions clash with the container (joblib unpickle error), train inside the stack instead: `docker compose exec control python /app/train.py`.

## Team workflow

Branch-per-task, PRs into protected `main`, at least one review — full conventions in [CONTRIBUTING.md](../blob/main/CONTRIBUTING.md). Generated artifacts (`data/*.csv`, `model/*.pkl`, local `.env`) are gitignored — never force-add them.
