"""Fetch everything we need about the area up front, so the walk itself is mostly local."""
import asyncio

from server import config
from server.agent.tools import nature, places, weather


async def prefetch_area(lat: float, lon: float) -> dict:
    """Run all lookups concurrently; any single failure degrades gracefully."""
    results = await asyncio.gather(
        places.osm_pois(lat, lon, config.POI_SEARCH_RADIUS_M),
        places.wiki_nearby(lat, lon, config.POI_SEARCH_RADIUS_M + 400),
        nature.likely_species(lat, lon),
        weather.current_weather(lat, lon),
        return_exceptions=True,
    )
    osm, wiki, species, wx = results

    def ok(x, default):
        if isinstance(x, Exception):
            print(f"[prefetch] lookup failed: {x!r}")
            return default
        return x

    return {
        "pois": ok(osm, []) + ok(wiki, []),
        "species": ok(species, {}),
        "weather": ok(wx, {}),
    }
