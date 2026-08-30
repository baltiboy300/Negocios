"""
Fuses all inputs into 4 hazard risk scores (0-100) + risk level + drivers.

For each site:
  1. Pull REAL live weather (Open-Meteo) and REAL terrain (Open-Elevation).
  2. Pull sensor readings -- real ingested reading if hardware has ever
     reported for this site, else the physically-grounded simulator.
  3. Pull the REAL citizen-report signal.
  4. Run the trained GradientBoosting model per hazard -> probability.
  5. Blend model probability with a transparent rule-based score (so the
     system is explainable, not just a black box) and the citizen signal.
  6. Return a score, level, and the top contributing factors.
"""

import os
import joblib

from . import data_sources, sensors
from .model_train import FEATURE_NAMES

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
_MODEL_CACHE: dict[str, dict] = {}

HAZARDS = ["landslide", "cloudburst", "flash_flood", "heavy_rain"]


def _load_model(hazard: str) -> dict:
    if hazard not in _MODEL_CACHE:
        path = os.path.join(_MODELS_DIR, f"{hazard}.joblib")
        _MODEL_CACHE[hazard] = joblib.load(path)
    return _MODEL_CACHE[hazard]


def _level(score: float) -> str:
    if score >= 75:
        return "SEVERE"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MODERATE"
    return "LOW"


async def assess_site(site: dict) -> dict:
    lat, lon, site_id = site["lat"], site["lon"], site["id"]

    weather = await data_sources.get_current_weather(lat, lon)
    terrain = await data_sources.get_elevation_and_slope(lat, lon)

    slope_deg = terrain.get("slope_deg") or 15.0
    elevation_m = terrain.get("elevation_m") or 1500.0
    soil_moisture = weather.get("soil_moisture_0_1cm_m3m3") or 0.2
    rain_1h = weather.get("rain_1h_mm") or 0.0
    rain_3h = weather.get("rain_3h_mm") or 0.0
    rain_24h = weather.get("rain_24h_mm") or 0.0
    rain_72h = weather.get("rain_72h_mm") or 0.0
    wind_gusts = weather.get("wind_gusts_kmh") or 0.0
    rain_rate_now = max(rain_1h, weather.get("precipitation_now_mm") or 0.0)

    # sensors: real ingested reading wins if present, else simulate
    xband = sensors.latest_real_reading("xband_radar", site_id) or sensors.simulate_xband_radar(
        rain_rate_now, site_id
    )
    infrasound = sensors.latest_real_reading(
        "infrasound_array", site_id
    ) or sensors.simulate_infrasound_array(slope_deg, rain_72h, soil_moisture, site_id)
    ultrasonic = sensors.latest_real_reading(
        "ultrasonic_station", site_id
    ) or sensors.simulate_ultrasonic_station(weather.get("wind_speed_kmh") or 0.0, wind_gusts, site_id)
    lidar = sensors.latest_real_reading("lidar_deformation", site_id) or sensors.simulate_lidar_deformation(
        slope_deg, rain_72h, site_id
    )
    drone = sensors.latest_real_reading("drone_survey", site_id) or sensors.simulate_drone_survey(
        rain_24h, site_id
    )

    citizen_score = sensors.citizen_signal_score(site_id)

    feature_row = {
        "rain_1h_mm": rain_1h,
        "rain_3h_mm": rain_3h,
        "rain_24h_mm": rain_24h,
        "rain_72h_mm": rain_72h,
        "soil_moisture": soil_moisture,
        "slope_deg": slope_deg,
        "elevation_m": elevation_m,
        "xband_dbz": xband.get("reflectivity_dbz", 0.0),
        "infrasound_anomaly": infrasound.get("anomaly_score_0_1", 0.0),
        "lidar_creep_mm_day": lidar.get("ground_displacement_mm_day", 0.0),
        "wind_gust_kmh": wind_gusts,
        "citizen_signal": citizen_score,
    }
    x = [[feature_row[f] for f in FEATURE_NAMES]]

    hazard_results = {}
    for hazard in HAZARDS:
        bundle = _load_model(hazard)
        model = bundle["model"]
        prob = float(model.predict_proba(x)[0][1])

        # transparent rule-based cross-check score (0-1), then blend
        rule_score = _rule_score(hazard, feature_row)
        blended = 0.65 * prob + 0.25 * rule_score + 0.10 * citizen_score
        score_pct = round(min(1.0, blended) * 100, 1)

        hazard_results[hazard] = {
            "score_pct": score_pct,
            "level": _level(score_pct),
            "model_probability": round(prob, 3),
            "rule_based_score": round(rule_score, 3),
            "citizen_signal_contribution": citizen_score,
            "top_drivers": _top_drivers(hazard, feature_row),
        }

    return {
        "site": site,
        "weather": weather,
        "terrain": terrain,
        "sensors": {
            "x_band_radar": xband,
            "infrasound_array": infrasound,
            "ultrasonic_station": ultrasonic,
            "lidar_deformation": lidar,
            "drone_survey": drone,
        },
        "citizen_reports": sensors.get_recent_citizen_reports(site_id),
        "hazards": hazard_results,
    }


def _rule_score(hazard: str, f: dict) -> float:
    if hazard == "heavy_rain":
        return min(1.0, f["rain_24h_mm"] / 204.5)  # IMD "extremely heavy" as ceiling
    if hazard == "cloudburst":
        return min(1.0, max(f["rain_1h_mm"] / 100.0, f["rain_3h_mm"] / 150.0))
    if hazard == "flash_flood":
        return min(
            1.0,
            0.5 * min(1.0, f["rain_3h_mm"] / 90.0)
            + 0.3 * min(1.0, f["soil_moisture"] / 0.45)
            + 0.2 * min(1.0, f["slope_deg"] / 40.0),
        )
    if hazard == "landslide":
        threshold_3h_total = 73.9 * (3 ** -0.79) * 3
        return min(
            1.0,
            0.45 * min(1.0, f["rain_3h_mm"] / threshold_3h_total) * min(1.0, f["soil_moisture"] / 0.4)
            + 0.20 * min(1.0, f["rain_72h_mm"] / 250.0)
            + 0.15 * min(1.0, f["slope_deg"] / 35.0)
            + 0.10 * f["infrasound_anomaly"]
            + 0.10 * min(1.0, f["lidar_creep_mm_day"] / 5.0),
        )
    return 0.0


def _top_drivers(hazard: str, f: dict) -> list[str]:
    drivers = []
    if hazard in ("cloudburst", "heavy_rain", "flash_flood") and f["rain_1h_mm"] > 20:
        drivers.append(f"Intense rainfall right now: {f['rain_1h_mm']:.1f} mm/hr")
    if f["rain_24h_mm"] > 64.5:
        drivers.append(f"24h rainfall {f['rain_24h_mm']:.0f} mm exceeds IMD heavy-rain threshold")
    if hazard == "landslide":
        if f["soil_moisture"] > 0.3:
            drivers.append(f"Soil already saturated ({f['soil_moisture']:.2f} m3/m3)")
        if f["slope_deg"] > 25:
            drivers.append(f"Steep terrain ({f['slope_deg']:.0f} degrees)")
        if f["infrasound_anomaly"] > 0.5:
            drivers.append("Elevated infrasound anomaly (possible slope movement)")
        if f["lidar_creep_mm_day"] > 3:
            drivers.append(f"Accelerating ground creep ({f['lidar_creep_mm_day']:.1f} mm/day)")
    if hazard == "flash_flood" and f["rain_3h_mm"] > 50:
        drivers.append(f"Sharp 3h rainfall spike: {f['rain_3h_mm']:.0f} mm")
    if not drivers:
        drivers.append("No strong individual driver -- conditions near baseline")
    return drivers
