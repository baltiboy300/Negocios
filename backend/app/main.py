import os
import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import firebase_admin
from firebase_admin import credentials, messaging

from . import data_sources, sensors, risk_engine
from .locations import SITES, SITES_BY_ID

# ---------------------------------------------------------------------------
# Firebase Admin SDK Initialization
# ---------------------------------------------------------------------------
if not firebase_admin._apps:
    env_creds = os.getenv("FIREBASE_CREDENTIALS")
    if env_creds:
        try:
            cred_dict = json.loads(env_creds)
            # Ensure private key newline characters are formatted properly
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print("Error initializing from FIREBASE_CREDENTIALS env:", e)
            firebase_admin.initialize_app(options={'projectId': 'negocios-8e8a4'})
    else:
        # Fallback to local file if present
        key_path = os.path.join(os.path.dirname(__file__), "firebase-key.json")
        if os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app(options={'projectId': 'negocios-8e8a4'})

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

# Wide-open CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    site = {
        "id": f"custom_{lat}_{lon}",
        "name": name,
        "lat": lat,
        "lon": lon,
        "country": "unknown",
        "state_or_province": "",
        "notes": "ad-hoc point"
    }
    return await risk_engine.assess_site(site)

@app.get("/radar")
async def get_radar():
    return await data_sources.get_rainviewer_radar_frames()

# ---------------------------------------------------------------------------
# ML Prediction Endpoint (Called by Frontend Prana Engine)
# ---------------------------------------------------------------------------

class PredictPayload(BaseModel):
    location: str
    lat: float
    lon: float
    rain_current: float = 0.0
    rain_3h: float = 0.0
    rain_72h: float = 0.0
    soil_moisture: float = 0.0
    max_quake_magnitude: float = 0.0
    temperature: float = 15.0
    humidity: float = 70.0
    pressure: float = 1013.0

@app.post("/predict")
async def predict_hazard(data: PredictPayload):
    """Evaluates multi-hazard risk using ML models / risk engine."""
    try:
        site = {
            "id": f"station_{data.lat}_{data.lon}",
            "name": data.location,
            "lat": data.lat,
            "lon": data.lon,
            "country": "India",
            "state_or_province": "",
            "notes": "realtime telemetry"
        }
        assessment = await risk_engine.assess_site(site)
        return {
            "status": "success",
            "location": data.location,
            "predictions": {
                "cloudburst": {
                    "score": assessment.get("cloudburst", {}).get("score", 15),
                    "tier": assessment.get("cloudburst", {}).get("tier", "low")
                },
                "flashflood": {
                    "score": assessment.get("flashflood", {}).get("score", 20),
                    "tier": assessment.get("flashflood", {}).get("tier", "low")
                },
                "landslide": {
                    "score": assessment.get("landslide", {}).get("score", 25),
                    "tier": assessment.get("landslide", {}).get("tier", "low")
                }
            },
            "raw_assessment": assessment
        }
    except Exception as e:
        cb_score = min(100, int((data.rain_current / 100.0) * 85 + (15 if data.rain_current > 50 else 0)))
        ff_score = min(100, int((data.rain_3h / 50.0) * 60 + (data.soil_moisture * 30)))
        ls_score = min(100, int((data.rain_72h / 120.0) * 50 + (data.max_quake_magnitude * 10)))
        
        def tier(s):
            return "extreme" if s >= 80 else "high" if s >= 55 else "watch" if s >= 30 else "low"
            
        return {
            "status": "fallback",
            "location": data.location,
            "predictions": {
                "cloudburst": {"score": cb_score, "tier": tier(cb_score)},
                "flashflood": {"score": ff_score, "tier": tier(ff_score)},
                "landslide": {"score": ls_score, "tier": tier(ls_score)}
            },
            "note": f"Fallback rule evaluation: {str(e)}"
        }

# ---------------------------------------------------------------------------
# Firebase Cloud Messaging (FCM) Push Endpoints
# ---------------------------------------------------------------------------

class SubscribePayload(BaseModel):
    token: str
    topic: str = "hazard-alerts"

class AlertPayload(BaseModel):
    type: str = "manual"
    message: Optional[str] = None
    location: Optional[str] = None
    telemetry: Optional[dict] = None

@app.post("/subscribe-topic")
async def subscribe_topic(data: SubscribePayload):
    try:
        response = messaging.subscribe_to_topic([data.token], data.topic)
        return {"success": True, "subscribedCount": response.success_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM Subscription Error: {str(e)}")

@app.post("/dispatch-push")
async def dispatch_push(data: AlertPayload):
    try:
        alert_text = data.message or "Hazard threshold breached in your monitored sector."
        location_name = data.location or "Catchment Sector"

        message = messaging.Message(
            notification=messaging.Notification(
                title=f"🚨 SENTINEL-HL ALERT · {location_name}",
                body=alert_text,
            ),
            topic="hazard-alerts"
        )

        response = messaging.send(message)
        return {"success": True, "dispatchedMessage": alert_text, "fcm_id": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM Dispatch Error: {str(e)}")

# ---------------------------------------------------------------------------
# Sensor Ingest & Citizen Reports
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
