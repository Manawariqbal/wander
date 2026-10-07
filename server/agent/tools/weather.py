"""Current weather from Open-Meteo (open, no key)."""
import httpx


async def current_weather(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,precipitation,wind_speed_10m,weather_code",
        })
        r.raise_for_status()
    return r.json()["current"]
