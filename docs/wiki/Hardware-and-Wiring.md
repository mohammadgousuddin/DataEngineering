# Hardware and Wiring

## Components

| Component | Measures | Interface |
|---|---|---|
| **DHT22 (AM2302)** | Air temperature + relative humidity | single-wire digital, Flipper GPIO **A7** |
| **DS18B20** (waterproof) | Probe/soil temperature | 1-Wire, Flipper GPIO **B3**, 12-bit conversion (~800 ms) |
| **Flipper Zero** | — | runs the MicroPython firmware; enumerates as USB-CDC serial (`/dev/ttyACM0`) |
| 2 × **4.7 kΩ resistors** | — | mandatory pull-ups, one per data line, to 3.3 V |

## Breadboard pinout

| Sensor pin | Connects to |
|---|---|
| DHT22 VCC (1) | red rail ← Flipper **3V3** |
| DHT22 DATA (2) | Flipper GPIO **A7**, plus 4.7 kΩ → red rail |
| DHT22 GND (4) | blue rail ← Flipper **GND** |
| DS18B20 VDD | red rail ← Flipper **3V3** |
| DS18B20 DQ | Flipper GPIO **B3**, plus 4.7 kΩ → red rail |
| DS18B20 GND | blue rail ← Flipper **GND** |
| Flipper USB-C | host machine (`/dev/ttyACM0`) |

> The **wiring page at :8888** renders this exact schematic live — wires pulse green while telemetry flows, red "waiting" when it doesn't. Use it as your visual sanity check after any rewiring.

## Firmware — `sensor_flipper.py`

MicroPython, loaded onto the Flipper SD card and run from the MicroPython app.

- Reads both sensors every **5 seconds**; DS18B20 gets its full 800 ms conversion time.
- Prints **one JSON line per cycle** to USB-CDC stdout:

```json
{"temp_dht": 38.42, "humidity": 24.7, "temp_ds18": 38.15, "ds_status": "ok", "ts": 1720510800}
```

- If the 1-Wire scan finds no probe (or a read fails), the frame still goes out with `ds_status: "fallback"` — the pipeline keeps flowing on one temperature source.
- An import guard (`HAVE_HW`) lets the same file run as a stub stream on a laptop for testing.

## Host bridge — `sensor_bridge.py`

Runs **on the host** (not in Docker — containers can't see USB serial). Start it after stopping the simulator:

```bash
cd mad_project && docker compose stop simulator && cd ..
python3 sensor_bridge.py
```

What it does, in order:

1. **Auto-detects** the serial port (`/dev/ttyACM*`, `/dev/ttyUSB*`, `/dev/flipper*`; override with `SERIAL_PORT`), opens at 115,200 baud, retries every 2 s forever.
2. **Validates** each frame against datasheet ranges — DHT −40…80 °C, RH 0…100 %, DS18 −55…125 °C. Bad frames are dropped, not corrected. A cross-sensor delta > 5 °C logs a warning.
3. **Augments** the three fields the hardware can't measure (`soil_moisture`, `co2`, `light_intensity`) from the UAE climate model so the 6-feature schema stays complete. Swap in real sensors by editing the `augment()` function.
4. **Publishes** to `greenhouse/sensor` (QoS 1, `source: "flipper"`), and maintains the retained `greenhouse/bridge` connection-status message with an MQTT Last Will (see [[Data Flow]]).

## Serial setup & diagnostics

```bash
./diagnose_flipper.sh        # checks port presence + permissions; expect /dev/ttyACM0
```

- **VirtualBox**: Devices → USB → Flipper Zero to pass the device into the VM.
- **Permissions**: `sudo usermod -aG dialout $USER && newgrp dialout`.
- Plugging the Flipper in is *not* enough for the dashboard to show "connected" — the **bridge** is what detects it and tells everyone over MQTT. See [[Troubleshooting]].
