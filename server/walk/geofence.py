"""Distance helpers and POI selection."""
import math

EARTH_R = 6_371_000


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def poi_key(p: dict) -> str:
    return f"{p['name']}|{round(p['lat'], 4)}|{round(p['lon'], 4)}"


def nearest_unseen(pois: list[dict], lat: float, lon: float, narrated: set[str], radius_m: float) -> dict | None:
    """Closest POI inside radius that has something to say and was not narrated yet."""
    best, best_d = None, radius_m
    for p in pois:
        if poi_key(p) in narrated or not p.get("facts"):
            continue
        d = distance_m(lat, lon, p["lat"], p["lon"])
        if d <= best_d:
            best, best_d = p, d
    return best
