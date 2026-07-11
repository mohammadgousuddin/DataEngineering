# Getting Started

Get the full stack running (with simulated data) in about 10 minutes — no hardware required.

## 1. Prerequisites (Kali Linux)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin python3-pip
sudo systemctl enable --now docker

# run docker without sudo (log out/in afterwards, or `newgrp docker`)
sudo usermod -aG docker $USER

# host-side python deps (only for sensor_bridge.py + generate_dataset.py)
pip3 install --user pyserial paho-mqtt numpy scikit-learn joblib
```

Running the Flipper through VirtualBox? Pass the device into the VM (**Devices → USB → Flipper Zero**) and add yourself to `dialout`:

```bash
sudo usermod -aG dialout $USER && newgrp dialout
```

## 2. Clone & configure

```bash
git clone https://github.com/<your-org>/MAD-greenhouse.git
cd MAD-greenhouse
cp mad_project/.env.example mad_project/.env   # defaults work out of the box
```

## 3. First run (simulator — no hardware)

```bash
python3 setup.py                      # environment checks + create data/ and model/ dirs
python3 generate_dataset.py --train   # UAE training set + Random Forest model
bash launch.sh                        # docker compose up the whole stack
xdg-open http://localhost:8050        # open the dashboard
```

Live gauges should appear within seconds — that data comes from the **simulator** container. Open the wiring page at http://localhost:8888 to see the breadboard schematic pulsing green.

> `generate_dataset.py --train` is technically optional for a first smoke-test: the `control` service auto-trains a model at startup if `model/rf_control.pkl` is missing. Training on the host keeps the saved model reproducible.

## 4. Switch to real sensors

```bash
# 1. flash sensor_flipper.py onto the Flipper SD card and run it (MicroPython app)
./diagnose_flipper.sh                          # expect /dev/ttyACM0
cd mad_project && docker compose stop simulator && cd ..
python3 sensor_bridge.py                       # host bridge: serial -> MQTT
```

The dashboard's SOURCE badge flips from SIMULATOR to FLIPPER automatically — no other change needed. Details: [[Hardware and Wiring]].

## 5. Verify

```bash
docker exec -it mosquitto mosquitto_sub -h localhost -p 1885 -t "greenhouse/#" -v   # live stream
cd mad_project && docker compose ps                                                  # all Up
docker exec csv_logger sh -c 'wc -l /data/greenhouse.csv'                            # rows growing
```

Something wrong? See [[Troubleshooting]].

## What's running after `launch.sh`

| URL | Service |
|---|---|
| http://localhost:8050 | Live dashboard (Plotly Dash) |
| http://localhost:8888 | Wiring / connection status page |
| http://localhost:8086 | InfluxDB UI (org `mad`, bucket `greenhouse`, token `my-token`) |
| localhost:1885 | MQTT broker (Mosquitto) |
| http://localhost:8000 | Random Forest inference API (`/predict`, `/health`) |
