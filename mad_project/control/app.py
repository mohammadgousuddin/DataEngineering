#!/usr/bin/env python3
"""
MAD control service — RandomForest inference API.

POST /predict with the feature vector and receive the recommended fan/pump
actuator states. If the trained model bundle is missing at startup, the service
trains one from the UAE climate model (train.py) so the stack is self-sufficient.

Falls back to the deterministic threshold rules if the model cannot be loaded.
"""
import os
from typing import List, Optional

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

import train as trainer

MODEL_PATH = os.environ.get("MODEL_PATH", "/model/rf_control.pkl")
FEATURES = ["temp_dht", "temp_ds18", "humidity", "soil_moisture", "co2", "light_intensity"]

FAN_TEMP, FAN_CO2, FAN_HUM = 40.0, 900.0, 20.0
PUMP_SOIL, PUMP_TEMP = 25.0, 45.0

app = FastAPI(title="MAD control")
_model = {"fan": None, "pump": None, "loaded": False}


class Features(BaseModel):
    temp_dht: float
    temp_ds18: float
    humidity: float
    soil_moisture: float
    co2: float
    light_intensity: float
    # optional raw feature list overrides the named fields if provided
    features: Optional[List[float]] = None

    def vector(self):
        if self.features and len(self.features) == len(FEATURES):
            return self.features
        return [self.temp_dht, self.temp_ds18, self.humidity,
                self.soil_moisture, self.co2, self.light_intensity]


def _load_model():
    import joblib
    if not os.path.exists(MODEL_PATH):
        print("[control] no model found — training a fresh one", flush=True)
        trainer.train(MODEL_PATH)
    bundle = joblib.load(MODEL_PATH)
    _model["fan"] = bundle["fan"]
    _model["pump"] = bundle["pump"]
    _model["loaded"] = True
    print(f"[control] model loaded from {MODEL_PATH}", flush=True)


def _threshold_decision(v):
    temp_dht, _ds, humidity, soil, co2, _light = v
    fan = (temp_dht >= FAN_TEMP) or (co2 >= FAN_CO2) or (humidity <= FAN_HUM)
    pump = (soil <= PUMP_SOIL) or (temp_dht >= PUMP_TEMP)
    return int(fan), int(pump)


def _action(fan, pump):
    if fan and pump:
        return "open_fan+run_pump"
    if fan:
        return "open_fan"
    if pump:
        return "run_pump"
    return "idle"


@app.on_event("startup")
def _startup():
    try:
        _load_model()
    except Exception as e:
        print(f"[control] model load failed, using threshold fallback: {e}", flush=True)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _model["loaded"], "model_path": MODEL_PATH}


@app.post("/predict")
def predict(feat: Features):
    v = feat.vector()
    used = "model"
    if _model["loaded"]:
        X = np.array([v], dtype=float)
        try:
            fan = int(_model["fan"].predict(X)[0])
            pump = int(_model["pump"].predict(X)[0])
            fan_conf = float(_model["fan"].predict_proba(X)[0].max())
            pump_conf = float(_model["pump"].predict_proba(X)[0].max())
        except Exception as e:
            print(f"[control] inference error, threshold fallback: {e}", flush=True)
            fan, pump = _threshold_decision(v)
            fan_conf = pump_conf = 1.0
            used = "threshold"
    else:
        fan, pump = _threshold_decision(v)
        fan_conf = pump_conf = 1.0
        used = "threshold"

    return {
        "actuator": {
            "fan_state": "ON" if fan else "OFF",
            "pump_state": "ON" if pump else "OFF",
        },
        "recommended_action": _action(fan, pump),
        "confidence": {"fan": round(fan_conf, 4), "pump": round(pump_conf, 4)},
        "decided_by": used,
    }
