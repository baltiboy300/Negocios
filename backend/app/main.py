from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from . import data_sources, sensors, risk_engine
from .locations import SITES, SITES_BY_ID

app = FastAPI(
    title="Himalaya Multi-Hazard Early Warning API",
    description=(
        "Landslide / cloudburst / flash-flood / heavy-rain risk for the "
        "Indian Himalayas, Nepal and Bhutan. Combines live weather+terrain "
        "APIs, simulated hardware-sensor feeds, real crowd-sourced citizen "
        "reports, and trained ML risk models."
    ),
    version="0.1.0",
)

# Wide-open CORS for hackathon demo purposes -- restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "status": "ok",
        "docs": "/docs",
        "sites": "/sites",
        "risk_endpoint": "/risk/{site_id}",
    }


@app.get("/sites")
def list_sites():
    return {"sites": SITES}


@app.get("/risk/{site_id}")
async def get_risk(site_id: str):
    site = SITES_BY_ID.get(site_id)
    if not site:
        raise HTTPException(404, f"Unknown site_id '{site_id}'. See /sites for valid ids.")
    return await risk_engine.assess_site(site)


@app.get("/risk")
async def get_risk_by_coords(lat: float, lon: float, name: str = "custom_point"):
    """Assess risk for any arbitrary point, not just the preset sites."""
    site = {"id": f"custom_{lat}_{lon}", "name": name, "lat": lat, "lon": lon,
            "country": "unknown", "state_or_province": "", "notes": "ad-hoc point"}
    return await risk_engine.assess_site(site)


@app.get("/radar")
async def get_radar():
    """Live RainViewer radar tile templates for map overlay."""
    return await data_sources.get_rainviewer_radar_frames()


# ---------------------------------------------------------------------------
# Sensor ingest -- real endpoint, ready for real hardware. Any device that
# can POST JSON (an actual X-band radar controller, an ultrasonic weather
# station's data logger, etc.) can push here and the risk engine will use
# real data instead of the simulator automatically.
# ---------------------------------------------------------------------------

class SensorIngest(BaseModel):
    site_id: str
    payload: dict = Field(..., description="Arbitrary sensor-specific JSON payload")


@app.post("/ingest/{sensor_type}")
def ingest(sensor_type: str, body: SensorIngest):
    valid_types = {"xband_radar", "infrasound_array", "ultrasonic_station", "lidar_deformation", "drone_survey"}
    if sensor_type not in valid_types:
        raise HTTPException(400, f"sensor_type must be one of {sorted(valid_types)}")
    if body.site_id not in SITES_BY_ID:
        raise HTTPException(404, f"Unknown site_id '{body.site_id}'")
    reading = sensors.ingest_reading(sensor_type, body.site_id, body.payload)
    return {"stored": True, "reading": reading}


# ---------------------------------------------------------------------------
# Citizen reports -- fully real, working feature.
# ---------------------------------------------------------------------------

class CitizenReportIn(BaseModel):
    site_id: str
    lat: float
    lon: float
    hazard_type: str = Field(..., pattern="^(landslide|flood|heavy_rain|cloudburst|other)$")
    severity: int = Field(..., ge=1, le=5)
    message: str
    reporter_name: Optional[str] = None


@app.post("/citizen-report")
def post_citizen_report(report: CitizenReportIn):
    if report.site_id not in SITES_BY_ID:
        raise HTTPException(404, f"Unknown site_id '{report.site_id}'")
    stored = sensors.submit_citizen_report(sensors.CitizenReport(**report.model_dump()))
    return {"stored": True, "report": stored}


@app.get("/citizen-report/{site_id}")
def get_citizen_reports(site_id: str):
    return {"reports": sensors.get_recent_citizen_reports(site_id)}
