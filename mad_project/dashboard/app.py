#!/usr/bin/env python3
"""
MAD dashboard — live Plotly Dash UI (Kali/Flipper dark theme).
 
100% live data from MQTT — zero hardcoded readings. A background MQTT subscriber
keeps a rolling history of greenhouse/sensor plus the latest greenhouse/command.
When no data has arrived, charts show "Waiting for live data" instead of fake
gauges. Threshold sliders let the operator override the actuator rules live.
"""
import glob
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
 
import paho.mqtt.client as mqtt
from dash import Dash, dcc, html, Input, Output, State
 
import figures as F
 
MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1885"))
CSV_PATH = os.environ.get("CSV_PATH", "/data/greenhouse.csv")
 
SENSOR_TOPIC = "greenhouse/sensor"
COMMAND_TOPIC = "greenhouse/command"
HISTORY = 90
 
# ---- shared live state -------------------------------------------------------
_lock = threading.Lock()
_history = deque(maxlen=HISTORY)
_latest = {"sensor": None, "command": None, "bridge": None, "bridge_rx": 0.0,
           "mqtt": False, "msgs": 0, "last_rx": 0.0}
 
BRIDGE_TOPIC = "greenhouse/bridge"
BRIDGE_STALE_S = 30.0
 
 
def _on_connect(client, userdata, flags, rc):
    _latest["mqtt"] = rc == 0
    client.subscribe([(SENSOR_TOPIC, 1), (COMMAND_TOPIC, 1), (BRIDGE_TOPIC, 1)])
    print(f"[dashboard] subscribed (rc={rc})", flush=True)
 
 
def _on_disconnect(client, userdata, rc):
    _latest["mqtt"] = False
 
 
def _on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        with _lock:
            if msg.topic == SENSOR_TOPIC:
                _history.append(data)
                _latest["sensor"] = data
                _latest["last_rx"] = time.time()
                _latest["msgs"] += 1
            elif msg.topic == COMMAND_TOPIC:
                _latest["command"] = data
            elif msg.topic == BRIDGE_TOPIC:
                _latest["bridge"] = data
                _latest["bridge_rx"] = time.time()
                print(f"[dashboard] BRIDGE status: connected={data.get('connected')} "
                      f"port={data.get('port')} reason={data.get('reason')}", flush=True)
    except Exception as e:
        print(f"[dashboard] msg error: {e}", flush=True)
 
 
def _mqtt_thread():
    client = mqtt.Client(client_id="dashboard")
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except Exception as e:
            print(f"[dashboard] waiting for broker ({e})", flush=True)
            time.sleep(2)
    client.loop_forever()
 
 
def csv_rows():
    try:
        with open(CSV_PATH) as f:
            return max(0, sum(1 for _ in f) - 1)
    except OSError:
        return 0
 
 
def flipper_connected():
    """Authoritative Flipper status from the retained greenhouse/bridge message.
 
    The dashboard runs inside Docker and cannot see the host /dev/ttyACM0, so it
    trusts the explicit status sensor_bridge.py publishes (with an MQTT Last Will
    that flips this to disconnected if the bridge dies or the cable is pulled).
    """
    with _lock:
        bridge = _latest["bridge"]
        bridge_rx = _latest["bridge_rx"]
    if not bridge or (time.time() - bridge_rx) >= BRIDGE_STALE_S:
        return False, None
    return bool(bridge.get("connected")), bridge.get("port")
 
 
# ---- app ---------------------------------------------------------------------
app = Dash(__name__, title="MAD · Greenhouse Digital Twin", update_title=None)
server = app.server
 
app.index_string = """<!DOCTYPE html>
<html>
<head>
  {%metas%}<title>{%title%}</title>{%favicon%}{%css%}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root{ --bg:#0a0e14; --panel:#0e141c; --grid:#1b2530; --ink:#c7d3e0;
           --dim:#5d6e80; --ok:#2bd576; --warn:#f5c542; --alert:#ff5252;
           --cyan:#21d4d4; --blue:#2f81f7; --orange:#ff8a1e; }
    *{ box-sizing:border-box; }
    body{ margin:0; background:var(--bg); color:var(--ink);
          font-family:'JetBrains Mono',ui-monospace,Menlo,monospace;
          background-image:radial-gradient(circle at 18% -10%, rgba(47,129,247,0.08), transparent 42%),
                           radial-gradient(circle at 100% 0%, rgba(255,138,30,0.06), transparent 38%);
          background-attachment:fixed; }
    .wrap{ max-width:1480px; margin:0 auto; padding:16px 20px 40px; }
    .topbar{ display:flex; align-items:center; gap:18px; flex-wrap:wrap;
             border:1px solid var(--grid); background:linear-gradient(180deg,#0e141c,#0a0e14);
             border-radius:10px; padding:12px 18px; margin-bottom:14px; }
    .brand{ display:flex; align-items:baseline; gap:10px; }
    .brand .mark{ color:var(--orange); font-weight:700; letter-spacing:1px; }
    .brand .mad{ font-size:20px; font-weight:700; letter-spacing:3px; }
    .brand .sub{ color:var(--dim); font-size:11px; letter-spacing:2px; text-transform:uppercase; }
    .badges{ display:flex; gap:10px; flex-wrap:wrap; margin-left:auto; }
    .badge{ display:flex; align-items:center; gap:7px; border:1px solid var(--grid);
            border-radius:6px; padding:6px 11px; font-size:11px; letter-spacing:.5px;
            background:rgba(255,255,255,0.015); white-space:nowrap; }
    .badge .k{ color:var(--dim); text-transform:uppercase; }
    .dot{ width:8px; height:8px; border-radius:50%; box-shadow:0 0 8px currentColor; }
    .dot.on{ color:var(--ok); background:var(--ok); animation:pulse 2s infinite; }
    .dot.off{ color:var(--alert); background:var(--alert); }
    .dot.idle{ color:var(--dim); background:var(--dim); }
    @keyframes pulse{ 0%,100%{opacity:1} 50%{opacity:.35} }
    .grid{ display:grid; grid-template-columns:minmax(0,2.1fr) minmax(300px,1fr); gap:14px; }
    @media(max-width:1040px){ .grid{ grid-template-columns:1fr; } }
    .col{ display:flex; flex-direction:column; gap:14px; }
    .panel{ border:1px solid var(--grid); border-radius:10px; background:var(--panel);
            position:relative; overflow:hidden; }
    .panel::before,.panel::after{ content:""; position:absolute; width:10px; height:10px; }
    .panel::before{ top:6px; left:6px; border-top:1px solid var(--blue); border-left:1px solid var(--blue); }
    .panel::after{ bottom:6px; right:6px; border-bottom:1px solid var(--blue); border-right:1px solid var(--blue); }
    .phead{ display:flex; align-items:center; gap:8px; padding:9px 14px;
            border-bottom:1px solid var(--grid); color:var(--dim);
            font-size:11px; letter-spacing:2px; text-transform:uppercase; }
    .phead .tag{ margin-left:auto; color:var(--blue); }
    .pbody{ padding:6px 8px; }
    .act-row{ display:flex; align-items:center; justify-content:space-between;
              padding:14px 16px; border-bottom:1px solid var(--grid); }
    .act-row:last-child{ border-bottom:none; }
    .act-name{ font-size:13px; letter-spacing:1px; }
    .act-cause{ color:var(--dim); font-size:10px; margin-top:3px; letter-spacing:.5px; }
    .pill{ font-weight:700; letter-spacing:2px; font-size:14px; padding:6px 16px;
           border-radius:6px; border:1px solid; }
    .pill.on{ color:#06140b; background:var(--ok); border-color:var(--ok);
              box-shadow:0 0 16px rgba(43,213,118,0.4); }
    .pill.off{ color:var(--dim); background:transparent; border-color:var(--grid); }
    .metric-row{ display:flex; justify-content:space-between; align-items:baseline;
                 padding:11px 16px; border-bottom:1px solid var(--grid); }
    .metric-row:last-child{ border-bottom:none; }
    .metric-row .lab{ color:var(--dim); font-size:11px; letter-spacing:1px; }
    .metric-row .val{ font-size:16px; font-weight:500; }
    .slabel{ display:flex; justify-content:space-between; color:var(--dim);
             font-size:10px; letter-spacing:1px; margin:14px 16px 2px; text-transform:uppercase; }
    .slabel b{ color:var(--ink); font-weight:500; }
    .reco{ padding:12px 16px; border-top:1px solid var(--grid); display:flex;
           align-items:center; gap:10px; }
    .reco .code{ color:var(--orange); font-size:13px; letter-spacing:1px; }
    .rc-slider .rc-slider-track{ background:var(--blue); }
    .rc-slider .rc-slider-handle{ border-color:var(--blue); background:#0a0e14; }
    .rc-slider .rc-slider-rail{ background:var(--grid); }
    .footer{ color:var(--dim); font-size:10px; letter-spacing:1px; text-align:center;
             margin-top:18px; }
    .js-plotly-plot .plotly text{ font-family:'JetBrains Mono',monospace !important; }
  </style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>"""
 
 
def badge(label, dot_class, value):
    return html.Div(className="badge", children=[
        html.Span(className=f"dot {dot_class}"),
        html.Span(className="k", children=label),
        html.Span(value),
    ])
 
 
def slider_block(sid, label, unit, mn, mx, step, val):
    return html.Div([
        html.Div(className="slabel", children=[html.Span(label), html.B(id=f"{sid}-val")]),
        dcc.Slider(id=sid, min=mn, max=mx, step=step, value=val,
                   marks=None, tooltip={"placement": "bottom", "always_visible": False},
                   updatemode="drag"),
    ])
 
 
app.layout = html.Div(className="wrap", children=[
    dcc.Interval(id="tick", interval=2000, n_intervals=0),
 
    html.Div(className="topbar", children=[
        html.Div(className="brand", children=[
            html.Span(className="mark", children="◆"),
            html.Span(className="mad", children="MAD"),
            html.Span(className="sub", children="monitor · automate · detect"),
        ]),
        html.Div(id="badges", className="badges"),
    ]),
 
    html.Div(className="grid", children=[
        html.Div(className="col", children=[
            html.Div(className="panel", children=[
                html.Div(className="phead", children=["sensor telemetry",
                         html.Span(className="tag", children="greenhouse/sensor · qos1")]),
                html.Div(className="pbody", children=[
                    dcc.Graph(id="gauges", config={"displayModeBar": False})]),
            ]),
            html.Div(className="panel", children=[
                html.Div(className="phead", children=["trends · threshold violations",
                         html.Span(className="tag", children="last 90 samples")]),
                html.Div(className="pbody", children=[
                    dcc.Graph(id="trends", config={"displayModeBar": False})]),
            ]),
        ]),
 
        html.Div(className="col", children=[
            html.Div(className="panel", children=[
                html.Div(className="phead", children=["actuators · random forest",
                         html.Span(className="tag", children="POST /predict")]),
                html.Div(id="actuators"),
            ]),
            html.Div(className="panel", children=[
                html.Div(className="phead", children=["derived metrics"]),
                html.Div(id="derived"),
            ]),
            html.Div(className="panel", children=[
                html.Div(className="phead", children=["threshold override",
                         html.Span(className="tag", children="operator")]),
                html.Div(className="pbody", children=[
                    slider_block("fan_temp", "fan · air temp ≥", "°C", 35, 48, 0.5, 40),
                    slider_block("fan_co2", "fan · co₂ ≥", "ppm", 600, 1200, 10, 900),
                    slider_block("fan_hum", "fan · humidity ≤", "%", 10, 35, 1, 20),
                    slider_block("pump_soil", "pump · soil ≤", "%", 15, 40, 1, 25),
                    slider_block("pump_temp", "pump · air temp ≥", "°C", 40, 50, 0.5, 45),
                    html.Div(style={"height": "8px"}),
                ]),
            ]),
        ]),
    ]),
 
    html.Div(className="footer", id="footer"),
])
 
 
def _cause(reading, thr):
    causes_fan, causes_pump = [], []
    if reading["temp_dht"] >= thr["fan_temp"]:
        causes_fan.append(f"AIR ≥ {thr['fan_temp']:.0f}°C")
    if reading["co2"] >= thr["fan_co2"]:
        causes_fan.append(f"CO₂ ≥ {thr['fan_co2']:.0f}")
    if reading["humidity"] <= thr["fan_hum"]:
        causes_fan.append(f"RH ≤ {thr['fan_hum']:.0f}%")
    if reading["soil_moisture"] <= thr["pump_soil"]:
        causes_pump.append(f"SOIL ≤ {thr['pump_soil']:.0f}%")
    if reading["temp_dht"] >= thr["pump_temp"]:
        causes_pump.append(f"AIR ≥ {thr['pump_temp']:.0f}°C")
    return causes_fan, causes_pump
 
 
@app.callback(
    [Output("gauges", "figure"), Output("trends", "figure"),
     Output("badges", "children"), Output("actuators", "children"),
     Output("derived", "children"), Output("footer", "children"),
     Output("fan_temp-val", "children"), Output("fan_co2-val", "children"),
     Output("fan_hum-val", "children"), Output("pump_soil-val", "children"),
     Output("pump_temp-val", "children")],
    [Input("tick", "n_intervals"),
     Input("fan_temp", "value"), Input("fan_co2", "value"), Input("fan_hum", "value"),
     Input("pump_soil", "value"), Input("pump_temp", "value")],
)
def update(_n, fan_temp, fan_co2, fan_hum, pump_soil, pump_temp):
    thr = {"fan_temp": fan_temp, "fan_co2": fan_co2, "fan_hum": fan_hum,
           "pump_soil": pump_soil, "pump_temp": pump_temp}
 
    with _lock:
        reading = dict(_latest["sensor"]) if _latest["sensor"] else None
        command = dict(_latest["command"]) if _latest["command"] else None
        hist = list(_history)
        mqtt_ok = _latest["mqtt"]
        msgs = _latest["msgs"]
        last_rx = _latest["last_rx"]
 
    live = reading is not None and (time.time() - last_rx) < 12
    if not live:
        reading = None
 
    # ---- badges
    src = (reading or {}).get("source", "—")
    src_dot = "on" if src == "flipper" else ("idle" if src == "simulator" else "off")
    flip, flip_port = flipper_connected()
    # Note: flipper_connected() checks the authoritative greenhouse/bridge MQTT message.
    # Don't override it based on the source field, which just indicates the current
    # reading's origin, not the live connection state of the bridge.
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    badges = [
        badge("source", src_dot, (src or "—").upper()),
        badge("flipper", "on" if flip else "off",
              (flip_port or "ttyACM0") if flip else "not connected"),
        badge("mqtt", "on" if mqtt_ok else "off", f":{MQTT_PORT}"),
        badge("influx", "on" if mqtt_ok else "idle", ":8086"),
        badge("csv", "idle", f"{csv_rows():,} rows"),
        badge("utc", "on" if live else "idle", now),
    ]
 
    # ---- gauges + trends
    gfig = F.gauges_figure(reading, thr)
    tfig = F.trends_figure(hist, thr)
 
    # ---- actuators (operator-threshold override; model command shown as reco)
    if reading is None:
        fan_on = pump_on = False
        cf = cp = []
    else:
        cf, cp = _cause(reading, thr)
        fan_on = bool(cf)
        pump_on = bool(cp)
 
    def act_row(name, on, causes):
        return html.Div(className="act-row", children=[
            html.Div([
                html.Div(className="act-name", children=name),
                html.Div(className="act-cause",
                         children=(" · ".join(causes) if (on and causes) else
                                   ("within limits" if reading else "no data"))),
            ]),
            html.Span(className=f"pill {'on' if on else 'off'}", children="ON" if on else "OFF"),
        ])
 
    reco = (command or {}).get("recommended_action", "idle" if reading else "—")
    conf = (command or {}).get("confidence", {})
    decided = (command or {}).get("decided_by", "model")
    conf_txt = ""
    if conf:
        conf_txt = f"  fan {conf.get('fan', 0)*100:.1f}% · pump {conf.get('pump', 0)*100:.1f}%"
    actuators = [
        act_row("FAN", fan_on, cf),
        act_row("IRRIGATION PUMP", pump_on, cp),
        html.Div(className="reco", children=[
            html.Span(className="k", style={"color": "var(--dim)", "fontSize": "10px",
                                            "letterSpacing": "1px"}, children="RF MODEL ▸"),
            html.Span(className="code", children=reco),
            html.Span(style={"color": "var(--dim)", "fontSize": "10px", "marginLeft": "auto"},
                      children=(f"{decided}{conf_txt}" if reading else "")),
        ]),
    ]
 
    # ---- derived metrics
    if reading is None:
        derived = [html.Div(className="metric-row", children=[
            html.Span(className="lab", children="awaiting telemetry"),
            html.Span(className="val", style={"color": "var(--dim)"}, children="—")])]
    else:
        t = reading["temp_dht"]
        rh = reading["humidity"]
        es = 0.6108 * (2.718281828 ** (17.27 * t / (t + 237.3)))
        vpd = round(es * (1 - rh / 100.0), 2)
        tf = t * 9 / 5 + 32
        hi_f = 0.5 * (tf + 61 + (tf - 68) * 1.2 + rh * 0.094)
        hi = round((hi_f - 32) * 5 / 9, 1)
        delta = round(abs(reading["temp_dht"] - reading["temp_ds18"]), 2)
        vpd_state = "IDEAL" if 0.8 <= vpd <= 1.2 else ("LOW" if vpd < 0.8 else "HIGH")
        vpd_color = "var(--ok)" if vpd_state == "IDEAL" else "var(--warn)"
        d_color = "var(--alert)" if delta > 5 else ("var(--warn)" if delta > 1.5 else "var(--ok)")
        derived = [
            html.Div(className="metric-row", children=[
                html.Span(className="lab", children="HEAT INDEX"),
                html.Span(className="val", children=f"{hi} °C")]),
            html.Div(className="metric-row", children=[
                html.Span(className="lab", children="VPD · ideal 0.8–1.2"),
                html.Span(className="val", style={"color": vpd_color},
                          children=f"{vpd} kPa · {vpd_state}")]),
            html.Div(className="metric-row", children=[
                html.Span(className="lab", children="CROSS-SENSOR Δ"),
                html.Span(className="val", style={"color": d_color}, children=f"{delta} °C")]),
        ]
 
    footer = (f"MAD · {msgs:,} telemetry frames received · broker {MQTT_HOST}:{MQTT_PORT} · "
              f"{'LIVE' if live else 'WAITING'} · UAE Data Engineering")
 
    return (gfig, tfig, badges, actuators, derived, footer,
            f"{fan_temp:g}°C", f"{fan_co2:g}", f"{fan_hum:g}%", f"{pump_soil:g}%", f"{pump_temp:g}°C")
 
 
if __name__ == "__main__":
    threading.Thread(target=_mqtt_thread, daemon=True).start()
    app.run(host="0.0.0.0", port=8050, debug=False)
