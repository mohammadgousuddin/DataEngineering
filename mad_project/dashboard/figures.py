"""
MAD dashboard — figure builders + Kali/Flipper dark theme constants.

Pure plotting helpers (no Dash, no MQTT) so they stay easy to test.
"""
import plotly.graph_objects as go

# ---- palette (Kali blue + Flipper orange + terminal green) -------------------
BG = "#0a0e14"
PANEL = "#0e141c"
GRID = "#1b2530"
INK = "#c7d3e0"
DIM = "#5d6e80"
OK = "#2bd576"      # green
WARN = "#f5c542"    # amber
ALERT = "#ff5252"   # red
CYAN = "#21d4d4"    # kali accent
BLUE = "#2f81f7"
ORANGE = "#ff8a1e"  # flipper
FONT = "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace"

# ---- thresholds (defaults; dashboard sliders override at runtime) ------------
DEFAULTS = {
    "fan_temp": 40.0, "fan_co2": 900.0, "fan_hum": 20.0,
    "pump_soil": 25.0, "pump_temp": 45.0,
}


def zone_temp(v, thr):
    if v >= thr["fan_temp"]:
        return ALERT
    if v >= thr["fan_temp"] - 2:
        return WARN
    return OK


def zone_hum(v, thr):
    if v <= thr["fan_hum"]:
        return ALERT
    if v <= thr["fan_hum"] + 5:
        return WARN
    return OK


def zone_co2(v, thr):
    if v >= thr["fan_co2"]:
        return ALERT
    if v >= thr["fan_co2"] - 100:
        return WARN
    return OK


def zone_soil(v, thr):
    if v <= thr["pump_soil"]:
        return ALERT
    if v <= thr["pump_soil"] + 5:
        return WARN
    return OK


def _gauge(fig, value, rng, color, threshold, title, unit, row, col, steps):
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": f" {unit}", "font": {"size": 26, "color": INK, "family": FONT}},
        title={"text": title, "font": {"size": 12, "color": DIM, "family": FONT}},
        gauge={
            "axis": {"range": rng, "tickcolor": DIM, "tickfont": {"size": 9, "color": DIM}},
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": "rgba(255,255,255,0.02)",
            "borderwidth": 1,
            "bordercolor": GRID,
            "steps": steps,
            "threshold": {
                "line": {"color": color, "width": 3},
                "thickness": 0.85,
                "value": threshold,
            } if threshold is not None else {},
        },
        domain={"row": row, "column": col},
    ))


def gauges_figure(reading, thr):
    """6 sensor gauges; reading=None -> waiting state."""
    fig = go.Figure()
    fig.update_layout(
        grid={"rows": 2, "columns": 3, "pattern": "independent"},
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=14, r=14, t=18, b=8),
        height=360,
        font={"family": FONT, "color": INK},
    )
    if reading is None:
        fig.add_annotation(text="◴  WAITING FOR LIVE DATA",
                           showarrow=False, font={"size": 20, "color": DIM, "family": FONT},
                           x=0.5, y=0.5, xref="paper", yref="paper")
        return fig

    t = reading

    def steps(rng, bands):
        return [{"range": b[0], "color": b[1]} for b in bands]

    soft = {"ok": "rgba(43,213,118,0.10)", "warn": "rgba(245,197,66,0.12)",
            "alert": "rgba(255,82,82,0.14)", "cyan": "rgba(33,212,212,0.10)"}

    _gauge(fig, t["temp_dht"], [25, 48], zone_temp(t["temp_dht"], thr), thr["fan_temp"],
           "AIR TEMP · DHT22 (°C)", "", 0, 0,
           steps(None, [([25, thr["fan_temp"] - 2], soft["ok"]),
                        ([thr["fan_temp"] - 2, thr["fan_temp"]], soft["warn"]),
                        ([thr["fan_temp"], 48], soft["alert"])]))

    _gauge(fig, t["temp_ds18"], [25, 48], zone_temp(t["temp_ds18"], thr), thr["pump_temp"],
           "PROBE TEMP · DS18B20 (°C)", "", 0, 1,
           steps(None, [([25, thr["fan_temp"]], soft["ok"]),
                        ([thr["fan_temp"], thr["pump_temp"]], soft["warn"]),
                        ([thr["pump_temp"], 48], soft["alert"])]))

    _gauge(fig, t["humidity"], [10, 45], zone_hum(t["humidity"], thr), thr["fan_hum"],
           "HUMIDITY · RH (%)", "", 0, 2,
           steps(None, [([10, thr["fan_hum"]], soft["alert"]),
                        ([thr["fan_hum"], thr["fan_hum"] + 5], soft["warn"]),
                        ([thr["fan_hum"] + 5, 45], soft["ok"])]))

    _gauge(fig, t["soil_moisture"], [10, 45], zone_soil(t["soil_moisture"], thr), thr["pump_soil"],
           "SOIL MOISTURE (%)", "", 1, 0,
           steps(None, [([10, thr["pump_soil"]], soft["alert"]),
                        ([thr["pump_soil"], thr["pump_soil"] + 5], soft["warn"]),
                        ([thr["pump_soil"] + 5, 45], soft["ok"])]))

    _gauge(fig, t["co2"], [100, 1000], zone_co2(t["co2"], thr), thr["fan_co2"],
           "CO₂ (ppm)", "", 1, 1,
           steps(None, [([100, thr["fan_co2"] - 100], soft["ok"]),
                        ([thr["fan_co2"] - 100, thr["fan_co2"]], soft["warn"]),
                        ([thr["fan_co2"], 1000], soft["alert"])]))

    _gauge(fig, t["light_intensity"], [0, 11000], CYAN, None,
           "LIGHT (lux)", "", 1, 2,
           steps(None, [([0, 11000], soft["cyan"])]))

    return fig


def _spark(fig, xs, ys, viol_x, viol_y, color, name, row):
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"color": color, "width": 1.6},
                             name=name, showlegend=False), row=row, col=1)
    if viol_x:
        fig.add_trace(go.Scatter(x=viol_x, y=viol_y, mode="markers",
                                 marker={"color": ALERT, "size": 6, "symbol": "circle",
                                         "line": {"color": "#1a0c0c", "width": 1}},
                                 name=name + " viol", showlegend=False), row=row, col=1)


def trends_figure(history, thr):
    """Sparklines for temp / humidity / co2 / soil with violation markers."""
    from plotly.subplots import make_subplots
    titles = ("AIR TEMP °C", "HUMIDITY %RH", "CO₂ ppm", "SOIL %")
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=titles)

    if not history:
        fig.add_annotation(text="◴  WAITING FOR LIVE DATA", showarrow=False,
                           font={"size": 16, "color": DIM, "family": FONT},
                           x=0.5, y=0.5, xref="paper", yref="paper")
    else:
        xs = list(range(len(history)))
        series = [
            ("temp_dht", BLUE, lambda v: zone_temp(v, thr) == ALERT),
            ("humidity", CYAN, lambda v: zone_hum(v, thr) == ALERT),
            ("co2", ORANGE, lambda v: zone_co2(v, thr) == ALERT),
            ("soil_moisture", OK, lambda v: zone_soil(v, thr) == ALERT),
        ]
        for i, (key, color, is_viol) in enumerate(series, start=1):
            ys = [h[key] for h in history]
            vx = [x for x, y in zip(xs, ys) if is_viol(y)]
            vy = [y for y in ys if is_viol(y)]
            _spark(fig, xs, ys, vx, vy, color, key, i)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=44, r=14, t=24, b=8), height=360,
        font={"family": FONT, "color": DIM, "size": 10},
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showticklabels=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False,
                     tickfont={"size": 9, "color": DIM})
    for ann in fig.layout.annotations:
        if ann.text in titles:
            ann.font = dict(size=10, color=DIM, family=FONT)
            ann.x = 0
            ann.xanchor = "left"
    return fig
