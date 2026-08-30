"""
REAL, LIVE data sources. Every function here hits a genuine public API
(no key required) and returns actual current data for the requested
coordinates. No simulation happens in this file.
"""

import httpx
from datetime import datetime, timezone

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OPEN_ELEVATION = "https://api.open-elevation.com/api/v1/lookup"
RAINVIEWER_MAPS = "https://api.rainviewer.com/public/weather-maps.json"

_client_timeout = httpx.Timeout(10.0, connect=5.0)


async def get_current_weather(lat: float, lon: float) -> dict:
    """
    Live current + last-48h hourly weather from Open-Meteo.
    Returns precipitation rate, cumulative rainfall, soil moisture,
    humidity, pressure and wind -- all real measurements/model output,
    not simulated.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,precipitation,rain,relative_humidity_2m,"
            "pressure_msl,wind_speed_10m,wind_gusts_10m"
        ),
        "hourly": (
            "precipitation,soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,"
            "relative_humidity_2m"
        ),
        "past_days": 3,
        "forecast_days": 2,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        r = await client.get(OPEN_METEO_FORECAST, params=params)
        r.raise_for_status()
        data = r.json()

    hourly_precip = data.get("hourly", {}).get("precipitation", []) or []
    hourly_time = data.get("hourly", {}).get("time", []) or []
    soil_1cm = data.get("hourly", {}).get("soil_moisture_0_to_1cm", []) or []

    # Real rainfall accumulation windows, computed from actual hourly series
    now_idx = _nearest_index(hourly_time)
    rain_1h = _sum_last_n(hourly_precip, now_idx, 1)
    rain_3h = _sum_last_n(hourly_precip, now_idx, 3)
    rain_24h = _sum_last_n(hourly_precip, now_idx, 24)
    rain_72h = _sum_last_n(hourly_precip, now_idx, 72)
    soil_moisture_now = soil_1cm[now_idx] if now_idx is not None and now_idx < len(soil_1cm) else None

    current = data.get("current", {})

    return {
        "source": "open-meteo (live)",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "temperature_c": current.get("temperature_2m"),
        "precipitation_now_mm": current.get("precipitation"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "pressure_msl_hpa": current.get("pressure_msl"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "wind_gusts_kmh": current.get("wind_gusts_10m"),
        "rain_1h_mm": rain_1h,
        "rain_3h_mm": rain_3h,
        "rain_24h_mm": rain_24h,
        "rain_72h_mm": rain_72h,
        "soil_moisture_0_1cm_m3m3": soil_moisture_now,
    }


def _nearest_index(times: list[str]) -> int | None:
    if not times:
        return None
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    best_i, best_diff = None, None
    for i, t in enumerate(times):
        try:
            ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        diff = abs((ts - now).total_seconds())
        if best_diff is None or diff < best_diff:
            best_i, best_diff = i, diff
    return best_i


def _sum_last_n(series: list[float], idx: int | None, n: int) -> float | None:
    if idx is None:
        return None
    start = max(0, idx - n + 1)
    window = [v for v in series[start : idx + 1] if v is not None]
    return round(sum(window), 2) if window else None


async def get_elevation_and_slope(lat: float, lon: float) -> dict:
    """
    Real elevation from Open-Elevation, plus a locally-computed slope
    estimate using a small ring of sample points (finite-difference slope --
    a genuine terrain-derived value, not simulated, though coarser than a
    proper DEM/LIDAR product).
    """
    d = 0.01  # ~1.1km at this latitude, enough for a coarse slope estimate
    points = [
        (lat, lon),
        (lat + d, lon),
        (lat - d, lon),
        (lat, lon + d),
        (lat, lon - d),
    ]
    locations = "|".join(f"{p[0]},{p[1]}" for p in points)
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        r = await client.get(OPEN_ELEVATION, params={"locations": locations})
        r.raise_for_status()
        results = r.json().get("results", [])

    if len(results) < 5:
        return {"elevation_m": None, "slope_deg": None, "source": "open-elevation (live)"}

    center, north, south, east, west = (res["elevation"] for res in results)
    # meters per degree latitude ~111,320; longitude scaled by cos(lat)
    import math

    dy = 111_320 * d
    dx = 111_320 * d * math.cos(math.radians(lat))
    dz_dy = (north - south) / (2 * dy)
    dz_dx = (east - west) / (2 * dx)
    slope_rad = math.atan(math.hypot(dz_dx, dz_dy))
    slope_deg = math.degrees(slope_rad)

    return {
        "elevation_m": center,
        "slope_deg": round(slope_deg, 1),
        "source": "open-elevation (live, finite-difference slope)",
    }


async def get_rainviewer_radar_frames() -> dict:
    """
    Live RainViewer radar/satellite frame catalogue. Returns tile URL
    templates the frontend can render directly on a map -- this is real,
    current global precipitation radar/nowcast data.
    """
    async with httpx.AsyncClient(timeout=_client_timeout) as client:
        r = await client.get(RAINVIEWER_MAPS)
        r.raise_for_status()
        data = r.json()

    host = data.get("host", "https://tilecache.rainviewer.com")
    radar = data.get("radar", {})
    past = radar.get("past", [])
    nowcast = radar.get("nowcast", [])

    def tile_template(frame: dict) -> str:
        path = frame["path"]
        return f"{host}{path}/256/{{z}}/{{x}}/{{y}}/2/1_1.png"

    return {
        "source": "rainviewer (live)",
        "latest_past_frame": tile_template(past[-1]) if past else None,
        "nowcast_frames": [tile_template(f) for f in nowcast],
        "generated_at": data.get("generated"),
    }
