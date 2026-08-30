"""
Trains 4 gradient-boosted classifiers (landslide, cloudburst, flash_flood,
heavy_rain) on a synthetic dataset. The dataset is NOT random -- it's
generated from published rainfall-threshold relationships for landslides
and flash floods in the Himalayan region, plus standard meteorological
definitions for cloudburst / heavy rain, so the model learns the right
shape of the problem even without a multi-year real incident archive.

Key literature-informed rules baked into the label generator:
  - Landslide triggering rainfall intensity-duration threshold in Nepal
    Himalaya (Dahal & Hasegawa, 2008; further supported by regional studies
    in Uttarakhand/Darjeeling): roughly I = 73.9 * D^-0.79 (mm/hr vs hours),
    strongly amplified by antecedent soil saturation and slope angle.
  - IMD (India Meteorological Department) definitions:
      heavy rain      >= 64.5 mm / 24h
      very heavy rain >= 115.6 mm / 24h
      extremely heavy >= 204.5 mm / 24h
      cloudburst      >= 100 mm / hour over a small area (WMO/IMD working def.)
  - Flash floods in steep Himalayan catchments respond to short (1-3h)
    intense rainfall + already-saturated soil + steep terrain much more
    than to 24h totals.

Run standalone: `python -m app.model_train` writes joblib models to
backend/app/models/*.joblib
"""

import math
import os
import random

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

FEATURE_NAMES = [
    "rain_1h_mm",
    "rain_3h_mm",
    "rain_24h_mm",
    "rain_72h_mm",
    "soil_moisture",
    "slope_deg",
    "elevation_m",
    "xband_dbz",
    "infrasound_anomaly",
    "lidar_creep_mm_day",
    "wind_gust_kmh",
    "citizen_signal",
]


def _dahal_hasegawa_threshold_mmhr(duration_hr: float) -> float:
    duration_hr = max(duration_hr, 0.5)
    return 73.9 * duration_hr ** -0.79


def _sample_row(rng: random.Random) -> dict:
    slope_deg = rng.uniform(2, 55)
    elevation_m = rng.uniform(300, 5200)
    soil_moisture = rng.uniform(0.05, 0.5)

    # rain profile: sample a "storm intensity" and derive consistent windows
    storm_intensity = rng.choice(
        ["none", "light", "moderate", "heavy", "extreme", "cloudburst"]
    )
    intensity_mmhr = {
        "none": rng.uniform(0, 1),
        "light": rng.uniform(1, 5),
        "moderate": rng.uniform(5, 15),
        "heavy": rng.uniform(15, 35),
        "extreme": rng.uniform(35, 80),
        "cloudburst": rng.uniform(80, 180),
    }[storm_intensity]

    rain_1h = intensity_mmhr * rng.uniform(0.8, 1.0)
    rain_3h = rain_1h * rng.uniform(1.6, 2.6)
    rain_24h = rain_3h * rng.uniform(2.0, 6.0) + rng.uniform(0, 20)
    rain_72h = rain_24h * rng.uniform(1.3, 2.8) + rng.uniform(0, 40)

    xband_dbz = 10 * math.log10(max(200 * (intensity_mmhr ** 1.6), 0.1)) + rng.uniform(-3, 3)
    infrasound_anomaly = min(
        1.0,
        max(
            0.0,
            0.5 * (soil_moisture / 0.45) + 0.3 * (rain_72h / 200) + 0.2 * (slope_deg / 45)
            + rng.uniform(-0.1, 0.1),
        ),
    )
    lidar_creep = max(0.0, 0.02 * slope_deg * (1 + rain_72h / 150) + rng.uniform(-0.4, 0.4))
    wind_gust_kmh = rng.uniform(5, 90)
    citizen_signal = rng.choice([0, 0, 0, 0, rng.uniform(0.2, 1.0)])  # mostly silent

    return dict(
        rain_1h_mm=rain_1h,
        rain_3h_mm=rain_3h,
        rain_24h_mm=rain_24h,
        rain_72h_mm=rain_72h,
        soil_moisture=soil_moisture,
        slope_deg=slope_deg,
        elevation_m=elevation_m,
        xband_dbz=xband_dbz,
        infrasound_anomaly=infrasound_anomaly,
        lidar_creep_mm_day=lidar_creep,
        wind_gust_kmh=wind_gust_kmh,
        citizen_signal=citizen_signal,
    )


def _label_row(row: dict, rng: random.Random) -> dict:
    threshold_3h = _dahal_hasegawa_threshold_mmhr(3)
    saturation_boost = row["soil_moisture"] / 0.45
    slope_boost = row["slope_deg"] / 30.0

    landslide_score = (
        0.5 * (row["rain_3h_mm"] / (threshold_3h * 3)) * saturation_boost
        + 0.25 * (row["rain_72h_mm"] / 250)
        + 0.15 * slope_boost
        + 0.10 * row["infrasound_anomaly"]
        + 0.15 * min(1.0, row["lidar_creep_mm_day"] / 5.0)
    )
    landslide = 1 if landslide_score + rng.uniform(-0.1, 0.1) > 0.55 else 0

    cloudburst = 1 if row["rain_1h_mm"] >= 100 or row["rain_3h_mm"] >= 150 else 0

    flash_flood_score = (
        0.5 * min(1.0, row["rain_3h_mm"] / 90)
        + 0.3 * saturation_boost
        + 0.2 * min(1.0, row["slope_deg"] / 40)
    )
    flash_flood = 1 if flash_flood_score + rng.uniform(-0.1, 0.1) > 0.55 else 0

    heavy_rain = 1 if row["rain_24h_mm"] >= 64.5 else 0

    return dict(
        landslide=landslide,
        cloudburst=cloudburst,
        flash_flood=flash_flood,
        heavy_rain=heavy_rain,
    )


def build_dataset(n: int = 20000, seed: int = 42):
    rng = random.Random(seed)
    X, Y = [], {k: [] for k in ("landslide", "cloudburst", "flash_flood", "heavy_rain")}
    for _ in range(n):
        row = _sample_row(rng)
        labels = _label_row(row, rng)
        X.append([row[f] for f in FEATURE_NAMES])
        for k in Y:
            Y[k].append(labels[k])
    return np.array(X), {k: np.array(v) for k, v in Y.items()}


def train_all(n_samples: int = 20000):
    X, Y = build_dataset(n_samples)
    reports = {}
    for hazard, y in Y.items():
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=0, stratify=y
        )
        clf = GradientBoostingClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.08, random_state=0
        )
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        reports[hazard] = classification_report(y_test, y_pred, output_dict=False)
        joblib.dump(
            {"model": clf, "feature_names": FEATURE_NAMES},
            os.path.join(MODELS_DIR, f"{hazard}.joblib"),
        )
    return reports


if __name__ == "__main__":
    reports = train_all()
    for hazard, report in reports.items():
        print(f"\n=== {hazard} ===")
        print(report)
    print(f"\nModels saved to {MODELS_DIR}")
