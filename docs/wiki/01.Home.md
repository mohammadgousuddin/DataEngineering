# MAD — Monitor · Automate · Detect

**Greenhouse Digital Twin · UAE Data Engineering · Semester 2**

A containerised IoT digital twin that takes physical sensor readings all the way to machine-learning-driven actuator control:

> **DHT22 + DS18B20 → Flipper Zero (USB bridge) → MQTT → InfluxDB → Random Forest → Plotly Dash**

Every reading is logged to `greenhouse.csv`, which doubles as the training corpus for retraining the AI on real greenhouse history.

## Why it's interesting

- **Simulator-first**: the full 8-service stack boots with zero hardware — a built-in UAE-climate simulator publishes to the same MQTT topic with the same schema, so the pipeline can be verified end-to-end before a single wire is connected.
- **Honest by design**: dashboards show *"Waiting for live data"* rather than fabricating readings; every degraded mode (fallback sensor, fallback model) is tagged in the data.
- **Closed ML loop**: sensor → Random Forest inference → actuator command → logged label → retraining.

## Wiki contents

| Page | What's in it |
|---|---|
| [[Getting Started]] | Prerequisites, installation, first run in under 10 minutes |
| [[System Architecture]] | The 8 services, how they connect, design decisions |
| [[Hardware and Wiring]] | Sensors, Flipper Zero, breadboard pinout, serial setup |
| [[Data Flow]] | MQTT topics and the step-by-step life of one sensor reading |
| [[AI and Machine Learning]] | UAE climate model, dataset, Random Forest, inference API, retraining |
| [[Dashboard and Monitoring]] | Dashboard panels, wiring status page, InfluxDB |
| [[Deployment and Operations]] | Docker Compose details, configuration, day-to-day commands |
| [[Troubleshooting]] | Every known failure mode and its fix |

## Quick facts

| | |
|---|---|
| Services | 8 Docker containers + 1 host-side bridge |
| Messaging | Eclipse Mosquitto 2, QoS 1, three topics |
| Storage | InfluxDB 2.7 (time series) + append-only CSV (17 columns) |
| ML | 2 × RandomForestClassifier (fan, pump), 200 trees, depth 12 |
| UI | Plotly Dash (:8050) + animated wiring page (:8888) |
| Sensor cadence | one reading every 5 seconds |
