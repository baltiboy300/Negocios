# Himalaya Multi-Hazard Early Warning API

Landslide / cloudburst / flash-flood / heavy-rain risk scoring for the
Indian Himalayas, Nepal, and Bhutan — a working FastAPI backend you can run
locally and call from any web app.

## What's real vs. simulated (be upfront about this with judges)

| Data source | Status | Detail |
|---|---|---|
| Weather (rain, humidity, wind, soil moisture) | **Real, live** | [Open-Meteo](https://open-meteo.com) forecast API, no key needed |
| Terrain (elevation, slope) | **Real, live** | [Open-Elevation](https://open-elevation.com) + a finite-difference slope calc |
| Radar/satellite precipitation imagery | **Real, live** | [RainViewer](https://www.rainviewer.com/api.html) public API tile frames |
| Citizen reports | **Real, working** | Anyone can submit via `/citizen-report`; feeds directly into the risk score |
| X-band radar reflectivity | **Simulated** | Derived from real rain rate via the actual Marshall-Palmer Z-R relationship — not random noise |
| Infrasound array anomaly | **Simulated** | Scored from real slope + soil saturation + rainfall (these genuinely drive infrasound precursors in the literature) |
| Ultrasonic weather station | **Simulated** | Micro-turbulence layered on real hourly wind data |
| LIDAR ground deformation | **Simulated** | Creep model driven by real slope + rainfall loading |
| Drone survey | **Simulated** | Flood-extent/canopy-stress modelled from real 24h rainfall |

Every simulated sensor has a matching `POST /ingest/{sensor_type}` endpoint.
Point real hardware at it and the risk engine automatically prefers the real
reading over the simulator — no code changes needed elsewhere.

## ML models

Four `GradientBoostingClassifier` models (landslide, cloudburst, flash_flood,
heavy_rain), trained on a 20,000-row synthetic dataset generated from
published rainfall-threshold research, not arbitrary randomness:

- Landslide triggering intensity-duration threshold for Himalayan terrain
  (Dahal & Hasegawa, 2008: I ≈ 73.9·D^-0.79), weighted by antecedent soil
  saturation and slope angle.
- IMD (India Meteorological Department) rainfall category thresholds:
  heavy rain ≥ 64.5 mm/24h, very heavy ≥ 115.6 mm/24h, extremely heavy ≥
  204.5 mm/24h.
- Cloudburst working definition (WMO/IMD): ≥ 100 mm/hr over a small area.
- Flash flood weighting toward short (1-3h) intense rainfall + saturation +
  slope, matching how Himalayan catchments actually respond.

Final score blends: `0.65 × ML probability + 0.25 × transparent rule score +
0.10 × citizen-report signal`, so the system stays explainable rather than a
pure black box — useful for a hazard-warning context where you need to say
*why* a score is high.

## Running it

```bash
cd backend
pip install -r requirements.txt
python -m app.model_train        # trains and saves the 4 models (~10s)
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for interactive Swagger UI.

## API reference

| Method | Path | What it does |
|---|---|---|
| GET | `/sites` | List all 12 preset monitoring sites (India/Nepal/Bhutan) |
| GET | `/risk/{site_id}` | Full hazard assessment for a preset site |
| GET | `/risk?lat=&lon=&name=` | Assessment for any arbitrary coordinate |
| GET | `/radar` | Live RainViewer tile URL templates for map overlay |
| POST | `/ingest/{sensor_type}` | Push a real sensor reading (overrides simulator) |
| POST | `/citizen-report` | Submit a real geotagged citizen hazard report |
| GET | `/citizen-report/{site_id}` | Recent reports for a site |

### Integrating with your own web app

The API is CORS-open for the hackathon demo. From any frontend:

```js
const res = await fetch("http://localhost:8000/risk/kedarnath");
const data = await res.json();
// data.hazards.landslide.score_pct, .level, .top_drivers ...
```

## Known limitations (say this out loud in your pitch — it builds trust)

- No multi-year real landslide/flood incident database was used for
  training (none is freely available at the needed granularity) — the
  model is trained on physically-derived synthetic data instead. This is a
  reasonable hackathon substitute, not a production-grade validated model.
- Slope is estimated from 5 elevation samples ~1km apart — a real system
  needs a proper DEM (e.g. ALOS PALSAR 12.5m or Bhoonidhi/ISRO Cartosat
  DEM) for accurate micro-terrain slope.
- Hardware sensor values are simulated; the ingest endpoints are real and
  ready, but no physical array/radar/LIDAR/drone is connected.
