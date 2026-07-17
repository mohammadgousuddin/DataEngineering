#!/usr/bin/env python3
"""
MAD model training (in-container).

Trains the fan + pump RandomForestClassifiers from the UAE climate model and
saves the joblib bundle to MODEL_PATH. Training inside the control container
guarantees the scikit-learn version matches at inference time (no host/container
unpickle mismatch).

Run automatically on control startup if the model is missing, or manually:
    docker compose exec control python /app/train.py
"""
import os

import numpy as np

MODEL_PATH = os.environ.get("MODEL_PATH", "/model/rf_control.pkl")
FEATURES = ["temp_dht", "temp_ds18", "humidity", "soil_moisture", "co2", "light_intensity"]

FAN_TEMP, FAN_CO2, FAN_HUM = 40.0, 900.0, 20.0
PUMP_SOIL, PUMP_TEMP = 25.0, 45.0


def _samples(n=20000, seed=42):
    rng = np.random.default_rng(seed)
    h = rng.uniform(0, 24, n)
    s = np.sin(2 * np.pi * h / 24)
    temp_dht = 7 * s + 36 + rng.normal(0, 0.35, n)
    humidity = np.clip(12 * s + 28 + rng.normal(0, 1.5, n), 0, 100)
    soil = np.clip(10 * s + 32 + rng.normal(0, 2, n), 0, 100)
    co2 = np.clip(280 * s + 420 + rng.normal(0, 12, n), 0, None)
    light = np.clip(5500 * s + 5500 + rng.normal(0, 180, n), 0, None)
    temp_ds18 = temp_dht + rng.normal(0, 0.4, n)
    X = np.column_stack([temp_dht, temp_ds18, humidity, soil, co2, light])
    fan = ((temp_dht >= FAN_TEMP) | (co2 >= FAN_CO2) | (humidity <= FAN_HUM)).astype(int)
    pump = ((soil <= PUMP_SOIL) | (temp_dht >= PUMP_TEMP)).astype(int)
    return X, fan, pump


def train(out_path=MODEL_PATH):
    from sklearn.ensemble import RandomForestClassifier
    import joblib

    X, fan, pump = _samples()
    clf_fan = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
    clf_pump = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
    clf_fan.fit(X, fan)
    clf_pump.fit(X, pump)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    joblib.dump({"fan": clf_fan, "pump": clf_pump, "features": FEATURES}, out_path)
    print(f"[control] trained + saved model -> {out_path}", flush=True)
    return out_path


if __name__ == "__main__":
    train()
