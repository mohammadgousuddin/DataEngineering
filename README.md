# MAD — Monitor · Automate · Detect
### Greenhouse Digital Twin · UAE Data Engineering

A containerised IoT digital-twin: **DHT22 + DS18B20 → Flipper Zero (USB bridge) → MQTT → InfluxDB →
Random Forest control → Plotly Dash**, with every reading logged to `greenhouse.csv` for AI training.

> This tree was reconstructed from `mad_research_book.md`. Review each file before running it against
> real hardware. It is designed to come up cleanly **with the built-in simulator even if no Flipper is
> attached**, so you can verify the whole pipeline first, then switch to live sensors.

---

## 0. Folder layout

```
MAD-greenhouse/
├── README.md
├── CONTRIBUTING.md         # team branch/PR workflow — read before pushing
├── .gitignore
├── setup.py                # env checks + create runtime dirs (run first)
├── generate_dataset.py     # UAE climate dataset + Random Forest training
├── sensor_bridge.py        # HOST: Flipper serial JSON  -> MQTT greenhouse/sensor
├── sensor_flipper.py       # MicroPython firmware for the Flipper Zero
├── launch.sh               # docker compose up the whole stack
├── fix_dashboard.sh        # patch old Dash app.run_server -> app.run
├── diagnose_flipper.sh     # serial-port / permission diagnostics
├── docs/
│   └── MAD_Project_Presentation.pptx   # technical deep-dive slide deck
├── greenhouseai/           # Greenhouse Neural Core web component + live server
└── mad_project/
    ├── docker-compose.yml
    ├── .env.example        # copy to .env for local config (defaults work)
    ├── mosquitto/config/mosquitto.conf
    ├── simulator/          # fallback data generator
    ├── ingestion/          # MQTT -> InfluxDB
    ├── control/            # RandomForest inference API (:8000)
    ├── controller/         # sensor -> model -> command loop
    ├── csv_logger/         # MQTT -> greenhouse.csv (+ heat index, VPD)
    ├── dashboard/          # Plotly Dash live UI (:8050)
    ├── wiring/             # breadboard + Flipper wiring status page (:8888)
    ├── model/              # rf_control.pkl (generated — gitignored)
    └── data/               # greenhouse.csv (generated — gitignored)
```

> **Cloning for the first time?** Run `cp mad_project/.env.example mad_project/.env`,
> then follow the Quickstart below. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
> team branch/PR workflow.

---

## 1. Prerequisites (Kali Linux)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin python3-pip
sudo systemctl enable --now docker

# run docker without sudo (log out / back in afterwards, or `newgrp docker`)
sudo usermod -aG docker $USER

# host-side python deps (only needed for sensor_bridge.py + generate_dataset.py)
pip3 install --user pyserial paho-mqtt numpy scikit-learn joblib
```

If you run the Flipper through VirtualBox: **Devices → USB → Flipper Zero** to pass the device into the VM,
then add yourself to `dialout` for serial access:

```bash
sudo usermod -aG dialout $USER && newgrp dialout
```

---

## 2. Quickstart (simulator first — no hardware needed)

```bash
cd MAD

# 1. environment checks + create data/ and model/ dirs
python3 setup.py

# 2. generate the UAE training set and train the Random Forest
python3 generate_dataset.py --train

# 3. bring the stack up (mosquitto, influxdb, ingestion, control, controller,
#    csv_logger, dashboard, and the fallback simulator)
bash launch.sh

# 4. open the dashboard
xdg-open http://localhost:8050
```

You should see live gauges within a few seconds — that data is coming from the **simulator** container.

Open the **wiring / connection page** at <http://localhost:8888> for a graphical breadboard + Flipper
Zero schematic that animates green while telemetry is flowing and turns red "waiting" when it is not —
a quick visual check of whether the whole project is working end to end.

> Note: the `control` service will also auto-train a model on first boot if `model/rf_control.pkl`
> is missing, so step 2 is optional for a first smoke-test. Training on the host keeps the saved model
> reproducible and lets you re-train from the live CSV later.

---

## 3. Switch to real sensors (Flipper Zero)

```bash
# 1. flash sensor_flipper.py onto the Flipper SD card and start it (it prints JSON over USB-CDC)
# 2. confirm the host sees the device
./diagnose_flipper.sh           # expect /dev/ttyACM0

# 3. stop the simulator so it stops publishing fake data
cd mad_project && docker compose stop simulator && cd ..

# 4. start the host bridge: serial JSON -> MQTT greenhouse/sensor
python3 sensor_bridge.py
```

The dashboard, ingestion, csv_logger and controller are all subscribed to `greenhouse/sensor`, so they
switch to live data automatically. When the bridge is not running and the simulator is stopped, the
dashboard shows **"Waiting for live data"** — it never fabricates readings.

---

## 4. Verify / operate

```bash
# live MQTT stream
docker exec -it mosquitto mosquitto_sub -h localhost -p 1885 -t "greenhouse/#" -v

# container status
cd mad_project && docker compose ps

# watch the CSV grow
docker exec csv_logger sh -c 'wc -l /data/greenhouse.csv'

# export the CSV
docker cp csv_logger:/data/greenhouse.csv ./greenhouse.csv

# logs
docker compose logs -f dashboard
docker compose logs -f csv_logger

# stop everything
docker compose down
```

---

## 5. Key parameters (from the documentation)

**MQTT topics** — `greenhouse/sensor` (telemetry), `greenhouse/command` (actuator state), QoS 1.

**Actuator thresholds** (UAE desert calibration):

| Actuator | ON when |
|---|---|
| Fan  | `temp_dht ≥ 40°C` OR `co2 ≥ 900 ppm` OR `humidity ≤ 20%` |
| Pump | `soil_moisture ≤ 25%` OR `temp_dht ≥ 45°C` |

**Feature vector** — `[temp_dht, temp_ds18, humidity, soil_moisture, co2, light_intensity]`.

Because the DHT22/DS18B20 only physically measure air temp, probe temp and humidity, the bridge
**augments** `soil_moisture`, `co2` and `light_intensity` from the UAE climate model so the feature
vector and CSV schema stay complete. Swap those for real sensors by editing `sensor_bridge.py`.

**Environment variables** are in `mad_project/.env`.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| **Flipper shows "not connected" even though it's plugged in** | Plugging in the Flipper is not enough — the **host bridge** is what detects it. Run `python3 sensor_bridge.py` (after `docker compose stop simulator`). The bridge publishes a retained `greenhouse/bridge` status the moment it opens the serial port, which is what the dashboard/wiring page read. The containers run inside Docker and **cannot** see `/dev/ttyACM0` directly. |
| `/dev/ttyACM0` not found | VirtualBox → Devices → USB → Flipper Zero; then `./diagnose_flipper.sh` |
| Permission denied on serial | `sudo usermod -aG dialout $USER && newgrp dialout` |
| Dashboard blank | Simulator stopped **and** bridge not running → start one of them |
| `app.run_server` error | `bash fix_dashboard.sh` (already uses `app.run`, this is a safety net) |
| Docker permission denied | `sudo usermod -aG docker $USER && newgrp docker` |
| Model file missing | `python3 generate_dataset.py --train` (or let `control` auto-train) |
| `joblib` unpickle / sklearn version error | train inside the stack: `docker compose exec control python /app/train.py` |

---

*MAD — Monitor · Automate · Detect | UAE Data Engineering Semester 2*
