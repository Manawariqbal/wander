"""Loop walking routes via OpenRouteService (free API key)."""
import random

import httpx

from server import config

URL = "https://api.openrouteservice.org/v2/directions/foot-walking/geojson"

# average walking speed used to convert minutes -> metres
WALK_M_PER_MIN = 80


async def plan_loop(lat: float, lon: float, minutes: int | None = None, km: float | None = None) -> dict:
    """Plan a round-trip walk starting and ending at (lat, lon).

    Returns distance, duration, GeoJSON geometry, and a list of turn steps,
    each with the coordinate where the instruction applies.
    """
    if not config.ORS_API_KEY:
        raise RuntimeError("ORS_API_KEY not set")
    length_m = int((km * 1000) if km else (minutes or 30) * WALK_M_PER_MIN)
    body = {
        "coordinates": [[lon, lat]],
        "instructions": True,
        "options": {"round_trip": {"length": length_m, "points": 3, "seed": random.randint(1, 10_000)}},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(URL, json=body, headers={"Authorization": config.ORS_API_KEY})
        r.raise_for_status()
    feat = r.json()["features"][0]
    coords = feat["geometry"]["coordinates"]  # [lon, lat] pairs
    props = feat["properties"]
    steps = []
    for seg in props.get("segments", []):
        for st in seg.get("steps", []):
            idx = st["way_points"][0]
            steps.append({
                "instruction": st["instruction"],
                "distance_m": st["distance"],
                "lat": coords[idx][1],
                "lon": coords[idx][0],
            })
    return {
        "distance_m": props["summary"]["distance"],
        "duration_min": round(props["summary"]["duration"] / 60),
        "geometry": feat["geometry"],
        "steps": steps,
    }
