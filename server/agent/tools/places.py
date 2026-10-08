"""Nearby points of interest: OpenStreetMap (Overpass) + Wikipedia."""
import httpx

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
WIKI = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "wander-ai/0.1 (hacktoberfest project)"}


async def osm_pois(lat: float, lon: float, radius_m: int = 600, limit: int = 40) -> list[dict]:
    q = f"""
    [out:json][timeout:25];
    (
      nwr(around:{radius_m},{lat},{lon})["historic"];
      nwr(around:{radius_m},{lat},{lon})["tourism"~"viewpoint|artwork|attraction"];
      nwr(around:{radius_m},{lat},{lon})["natural"="tree"]["species"];
      nwr(around:{radius_m},{lat},{lon})["leisure"~"park|garden|nature_reserve"]["name"];
    );
    out center {limit};
    """
    last_exc: Exception | None = None
    r = None
    async with httpx.AsyncClient(timeout=40, headers=UA) as client:
        for url in OVERPASS_URLS:
            try:
                r = await client.post(url, data={"data": q})
                r.raise_for_status()
                break
            except Exception as exc:
                print(f"[overpass] {url} failed: {exc!r}")
                last_exc = exc
                r = None
    if r is None:
        raise last_exc  # prefetch handles this and carries on without OSM data

    pois = []
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if c.get("lat") is None:
            continue
        name = tags.get("name") or tags.get("species") or tags.get("historic") or "unnamed"
        kind = tags.get("historic") or tags.get("tourism") or tags.get("natural") or tags.get("leisure")
        pois.append({
            "name": name,
            "kind": kind,
            "lat": c["lat"],
            "lon": c["lon"],
            "wikipedia": tags.get("wikipedia"),
            "facts": tags.get("description")
            or (f"A {tags['species']} tree." if tags.get("natural") == "tree" and tags.get("species") else ""),
        })
    return pois


async def wiki_nearby(lat: float, lon: float, radius_m: int = 1000, limit: int = 8) -> list[dict]:
    """Wikipedia articles near a point, with a short plain-text extract."""
    async with httpx.AsyncClient(timeout=20, headers=UA) as client:
        r = await client.get(WIKI, params={
            "action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}",
            "gsradius": min(radius_m, 10000), "gslimit": limit, "format": "json",
        })
        r.raise_for_status()
        hits = r.json()["query"]["geosearch"]
        if not hits:
            return []
        ids = "|".join(str(h["pageid"]) for h in hits)
        r2 = await client.get(WIKI, params={
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
            "exsentences": 3, "pageids": ids, "format": "json",
        })
        r2.raise_for_status()
        pages = r2.json()["query"]["pages"]
    out = []
    for h in hits:
        extract = pages.get(str(h["pageid"]), {}).get("extract", "")
        out.append({
            "name": h["title"], "kind": "wikipedia", "lat": h["lat"], "lon": h["lon"],
            "wikipedia": h["title"], "facts": extract,
        })
    return out