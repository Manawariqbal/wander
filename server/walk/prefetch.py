"""Fetch everything we need about the area up front, so the walk itself is mostly local."""
import asyncio

from server import config
from server.agent.tools import nature, places, weather
from server.db.store import Store


async def prefetch_area(lat: float, lon: float, store: Store | None = None) -> dict:
    """Run all lookups concurrently; any single failure degrades gracefully.

    If a Store is provided, try the ~1 km grid cache first and write back on a miss.
    """
    # 1. Try cache first
    if store is not None:
        cached = store.get_poi_cache(lat, lon)
        if cached is not None:
            print(f"[prefetch] cache hit for {lat:.4f},{lon:.4f}")
            return cached

    # 2. Live lookups
    results = await asyncio.gather(
        places.osm_pois(lat, lon, config.POI_SEARCH_RADIUS_M),
        places.wiki_nearby(lat, lon, config.POI_SEARCH_RADIUS_M + 400),
        nature.likely_species(lat, lon),
        weather.current_weather(lat, lon),
        weather.sun_times(lat, lon),
        return_exceptions=True,
    )
    osm, wiki, species, wx, sun = results

    def ok(x, default):
        if isinstance(x, Exception):
            print(f"[prefetch] lookup failed: {x!r}")
            return default
        return x

    data = {
        "pois": ok(osm, []) + ok(wiki, []),
        "species": ok(species, {}),
        "weather": ok(wx, {}),
        "sun": ok(sun, {}),
    }

    # 3. Write to cache
    if store is not None:
        store.set_poi_cache(lat, lon, data)
        print(f"[prefetch] cached for {lat:.4f},{lon:.4f}")

    return data