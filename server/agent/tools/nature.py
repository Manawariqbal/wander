"""Likely species near a point, from iNaturalist (open data, no key needed)."""
from datetime import date

import httpx

API = "https://api.inaturalist.org/v1/observations/species_counts"


async def likely_species(lat: float, lon: float, radius_km: float = 3, limit: int = 12) -> dict:
    """Return {'birds': [...], 'plants': [...]} of commonly observed species this month."""
    out: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for key, taxa in (("birds", "Aves"), ("plants", "Plantae")):
            r = await client.get(
                API,
                params={
                    "lat": lat,
                    "lng": lon,
                    "radius": radius_km,
                    "month": date.today().month,
                    "iconic_taxa": taxa,
                    "per_page": limit,
                    "quality_grade": "research",
                    "locale": "en",
                },
            )
            r.raise_for_status()
            names = []
            for item in r.json().get("results", []):
                t = item["taxon"]
                names.append(t.get("preferred_common_name") or t["name"])
            out[key] = names
    return out
