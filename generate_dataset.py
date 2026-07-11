#!/usr/bin/env python3
"""
MAD dataset generator + Random Forest trainer.

Produces synthetic UAE-greenhouse training data using the sinusoidal climate
models from the documentation, derives deterministic threshold labels for the
fan and pump actuators, trains two RandomForestClassifiers, and saves them as a
single joblib bundle at mad_project/model/rf_control.pkl.

Usage:
  python3 generate_dataset.py                 # write training_data.csv only
  python3 generate_dataset.py --train         # write csv + train + save model
  python3 generate_dataset.py --train --rows 40000 --seed 7
  python3 generate_dataset.py --train --from-csv mad_project/data/greenhouse.csv
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
MODEL_PATH = BASE / "mad_project" / "model" / "rf_control.pkl"
DATA_PATH = BASE / "mad_project" / "data" / "training_data.csv"

# Feature order is fixed across the whole stack (control service depends on it).
FEATURES = ["temp_dht", "temp_ds18", "humidity", "soil_moisture", "co2", "light_intensity"]

# UAE desert-greenhouse actuator thresholds.
FAN_TEMP, FAN_CO2, FAN_HUM = 40.0, 900.0, 20.0
PUMP_SOIL, PUMP_TEMP = 25.0, 45.0


def climate_samples(n, seed=42):
    """UAE sinusoidal climate model with Gaussian noise (see documentation §6.1)."""
    rng = np.random.default_rng(seed)
    h = rng.uniform(0.0, 24.0, n)
    s = np.sin(2.0 * np.pi * h / 24.0)

    temp_dht = 7.0 * s + 36.0 + rng.normal(0.0, 0.35, n)
    humidity = np.clip(12.0 * s + 28.0 + rng.normal(0.0, 1.5, n), 0.0, 100.0)
    soil = np.clip(10.0 * s + 32.0 + rng.normal(0.0, 2.0, n), 0.0, 100.0)
    co2 = np.clip(280.0 * s + 420.0 + rng.normal(0.0, 12.0, n), 0.0, None)
    light = np.clip(5500.0 * s + 5500.0 + rng.normal(0.0, 180.0, n), 0.0, None)
    temp_ds18 = temp_dht + rng.normal(0.0, 0.4, n)

    X = np.column_stack([temp_dht, temp_ds18, humidity, soil, co2, light])
    return X


def threshold_labels(X):
    """Deterministic ON/OFF labels from the documented threshold rules."""
    temp_dht = X[:, 0]
    humidity = X[:, 2]
    soil = X[:, 3]
    co2 = X[:, 4]
    fan = ((temp_dht >= FAN_TEMP) | (co2 >= FAN_CO2) | (humidity <= FAN_HUM)).astype(int)
    pump = ((soil <= PUMP_SOIL) | (temp_dht >= PUMP_TEMP)).astype(int)
    return fan, pump


def write_csv(X, fan, pump, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FEATURES + ["fan_state", "pump_state"])
        for row, fa, pu in zip(X, fan, pump):
            w.writerow([f"{v:.4f}" for v in row] + [int(fa), int(pu)])
    print(f"  wrote {len(X):,} rows -> {path}")


def load_from_csv(path):
    """Load features + labels from a live greenhouse.csv export."""
    import pandas as pd  # optional dependency, only needed for --from-csv

    df = pd.read_csv(path)
    X = df[FEATURES].to_numpy(dtype=float)
    fan = (df["fan_state"].astype(str).str.upper() == "ON").astype(int).to_numpy()
    pump = (df["pump_state"].astype(str).str.upper() == "ON").astype(int).to_numpy()
    return X, fan, pump


def train(X, fan, pump, out_path):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    import joblib

    print("\nTraining Random Forest classifiers...")
    Xtr, Xte, ftr, fte, ptr, pte = train_test_split(
        X, fan, pump, test_size=0.20, random_state=42
    )

    clf_fan = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
    clf_pump = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
    clf_fan.fit(Xtr, ftr)
    clf_pump.fit(Xtr, ptr)

    fan_acc = accuracy_score(fte, clf_fan.predict(Xte))
    pump_acc = accuracy_score(pte, clf_pump.predict(Xte))
    print(f"  fan  test accuracy: {fan_acc*100:.2f}%")
    print(f"  pump test accuracy: {pump_acc*100:.2f}%")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"fan": clf_fan, "pump": clf_pump, "features": FEATURES}, out_path)
    print(f"  saved model bundle -> {out_path}")


def main():
    ap = argparse.ArgumentParser(description="MAD dataset + Random Forest trainer")
    ap.add_argument("--rows", type=int, default=20000, help="synthetic rows (default 20000)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train", action="store_true", help="train + save model after generating")
    ap.add_argument("--from-csv", type=str, default=None, help="train from a live greenhouse.csv")
    ap.add_argument("--out", type=str, default=str(MODEL_PATH), help="model output path")
    ap.add_argument("--csv-out", type=str, default=str(DATA_PATH), help="dataset csv output path")
    args = ap.parse_args()

    print(f"\nMAD dataset generator  (rows={args.rows}, seed={args.seed})")

    if args.from_csv:
        print(f"Loading training data from {args.from_csv} ...")
        X, fan, pump = load_from_csv(args.from_csv)
    else:
        X = climate_samples(args.rows, seed=args.seed)
        fan, pump = threshold_labels(X)
        write_csv(X, fan, pump, Path(args.csv_out))

    print(f"  fan ON: {fan.mean()*100:.1f}%   pump ON: {pump.mean()*100:.1f}%")

    if args.train:
        try:
            train(X, fan, pump, Path(args.out))
        except ImportError as e:
            print(f"\n[!] scikit-learn / joblib not installed on host: {e}")
            print("    pip3 install --user scikit-learn joblib")
            print("    (or let the control service auto-train inside the stack)")
            sys.exit(1)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
