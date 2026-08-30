"""
Monitoring locations across the Indian Himalayas, Nepal, and Bhutan.

Each site has real terrain metadata (approx elevation, region) used to weight
the physical risk model. Add more sites freely -- lat/lon is all that's
strictly required, elevation/slope are auto-fetched from Open-Elevation if
not supplied.
"""

from typing import TypedDict


class Site(TypedDict):
    id: str
    name: str
    country: str
    state_or_province: str
    lat: float
    lon: float
    notes: str


SITES: list[Site] = [
    # --- Indian Himalayas ---
    {
        "id": "joshimath",
        "name": "Joshimath",
        "country": "India",
        "state_or_province": "Uttarakhand",
        "lat": 30.5551,
        "lon": 79.5644,
        "notes": "Active land subsidence & landslide zone, Alaknanda valley.",
    },
    {
        "id": "kedarnath",
        "name": "Kedarnath",
        "country": "India",
        "state_or_province": "Uttarakhand",
        "lat": 30.7346,
        "lon": 79.0669,
        "notes": "Site of 2013 Kedarnath cloudburst/flash flood disaster.",
    },
    {
        "id": "chamoli",
        "name": "Chamoli",
        "country": "India",
        "state_or_province": "Uttarakhand",
        "lat": 30.4000,
        "lon": 79.3200,
        "notes": "2021 Chamoli glacial-lake outburst flash flood.",
    },
    {
        "id": "darjeeling",
        "name": "Darjeeling",
        "country": "India",
        "state_or_province": "West Bengal",
        "lat": 27.0410,
        "lon": 88.2663,
        "notes": "Steep tea-garden slopes, chronic monsoon landslides.",
    },
    {
        "id": "gangtok",
        "name": "Gangtok",
        "country": "India",
        "state_or_province": "Sikkim",
        "lat": 27.3389,
        "lon": 88.6065,
        "notes": "Urbanised ridge terrain, cloudburst-triggered debris flow risk.",
    },
    # --- Nepal ---
    {
        "id": "kathmandu",
        "name": "Kathmandu Valley",
        "country": "Nepal",
        "state_or_province": "Bagmati",
        "lat": 27.7172,
        "lon": 85.3240,
        "notes": "Dense urban flash-flood risk along Bagmati/Bishnumati rivers.",
    },
    {
        "id": "sindhupalchok",
        "name": "Sindhupalchok",
        "country": "Nepal",
        "state_or_province": "Bagmati",
        "lat": 27.9513,
        "lon": 85.6836,
        "notes": "One of Nepal's most landslide-prone districts.",
    },
    {
        "id": "melamchi",
        "name": "Melamchi",
        "country": "Nepal",
        "state_or_province": "Bagmati",
        "lat": 27.9270,
        "lon": 85.5510,
        "notes": "2021 Melamchi flash flood/debris flow disaster.",
    },
    {
        "id": "pokhara",
        "name": "Pokhara",
        "country": "Nepal",
        "state_or_province": "Gandaki",
        "lat": 28.2096,
        "lon": 83.9856,
        "notes": "Seti river gorge, glacial lake outburst flood exposure.",
    },
    # --- Bhutan ---
    {
        "id": "thimphu",
        "name": "Thimphu",
        "country": "Bhutan",
        "state_or_province": "Thimphu",
        "lat": 27.4712,
        "lon": 89.6339,
        "notes": "Valley urban flood risk from Wang Chhu river.",
    },
    {
        "id": "punakha",
        "name": "Punakha",
        "country": "Bhutan",
        "state_or_province": "Punakha",
        "lat": 27.5921,
        "lon": 89.8797,
        "notes": "Confluence town, historic GLOF flood exposure.",
    },
    {
        "id": "paro",
        "name": "Paro",
        "country": "Bhutan",
        "state_or_province": "Paro",
        "lat": 27.4287,
        "lon": 89.4164,
        "notes": "Steep valley walls, monsoon landslide risk.",
    },
]

SITES_BY_ID = {s["id"]: s for s in SITES}
