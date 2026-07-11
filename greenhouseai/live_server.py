#!/usr/bin/env python3
"""
Greenhouse Neural Core — local live WebSocket bridge
====================================================
The website ("CONNECT LIVE" button) connects to  ws://localhost:8765
and expects ONE JSON object per reading, e.g.:

    {
      "timestamp": 1781471734.15,   # optional, unix seconds (UTC)
      "temp_dht": 31.9,
      "temp_delta": 0.27,
      "humidity": 18.8,
      "soil_moisture": 24.7,
      "co2": 235.0,
      "light_intensity": 1486.5,
      "heat_index": 29.8,
      "vpd_kpa": 3.83,
      "fan_state": "ON",            # or "OFF" / 1 / 0  (optional)
      "pump_state": "OFF"           # optional
    }

Any missing field keeps its previous value, so you can send partial updates.

------------------------------------------------------------------
TWO WAYS TO USE
------------------------------------------------------------------
1) DEMO MODE (default): replays greenhouse.csv as if it were live,
   one row every few seconds — great for testing the website's live path.

2) REAL MODE: replace `read_real_sensor()` with your Flipper Zero /
   serial / MQTT read and it will stream your actual greenhouse.

------------------------------------------------------------------
SETUP
------------------------------------------------------------------
    pip install websockets
    python live_server.py
then open the website and click  "CONNECT LIVE".
"""

import asyncio, csv, json, time, itertools, pathlib

try:
    import websockets
    from websockets.http11 import Response
    from websockets.datastructures import Headers
except ImportError:
    raise SystemExit("Run:  pip install websockets")

HOST, PORT = "127.0.0.1", 8765
INTERVAL_S = 2.0                      # seconds between pushes (real rig = 5s)
CSV_PATH = pathlib.Path(__file__).with_name("greenhouse.csv")

FIELDS = ["temp_dht", "temp_delta", "humidity", "soil_moisture",
          "co2", "light_intensity", "heat_index", "vpd_kpa"]


def csv_rows():
    """Yield readings from greenhouse.csv forever (DEMO MODE)."""
    while True:
        with open(CSV_PATH, newline="") as f:
            for row in csv.DictReader(f):
                yield {
                    "timestamp": float(row["timestamp"]),
                    **{k: float(row[k]) for k in FIELDS},
                    "fan_state": row["fan_state"],
                    "pump_state": row["pump_state"],
                }


# --- REAL MODE: implement this for your own hardware ---------------
def read_real_sensor():
    """Return a dict like the schema above from your Flipper/serial feed."""
    raise NotImplementedError


def reject_plain_http(connection, request):
    if "upgrade" not in request.headers.get("Connection", "").lower():
        return Response(200, "OK", Headers())


async def stream(websocket):
    print("client connected")
    feed = csv_rows()                 # swap for your real generator
    try:
        for reading in feed:
            reading["timestamp"] = time.time()   # stamp as 'now' for live clock
            await websocket.send(json.dumps(reading))
            await asyncio.sleep(INTERVAL_S)
    except websockets.ConnectionClosed:
        print("client disconnected")


async def main():
    print(f"Greenhouse live bridge on ws://{HOST}:{PORT}  (Ctrl+C to stop)")
    async with websockets.serve(stream, HOST, PORT, process_request=reject_plain_http):
        await asyncio.Future()        # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped")
