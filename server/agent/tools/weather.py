"""Weather and daylight from Open-Meteo (open, no key)."""
from datetime import datetime, timedelta, timezone

import httpx

URL = "https://api.open-meteo.com/v1/forecast"


async def current_weather(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(URL, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,precipitation,wind_speed_10m,weather_code",
        })
        r.raise_for_status()
    return r.json()["current"]


async def sun_times(lat: float, lon: float) -> dict:
    """Today's sunrise/sunset in the location's local time, plus its UTC offset."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(URL, params={
            "latitude": lat, "longitude": lon,
            "daily": "sunrise,sunset", "timezone": "auto", "forecast_days": 1,
        })
        r.raise_for_status()
    j = r.json()
    return {
        "sunrise": j["daily"]["sunrise"][0],
        "sunset": j["daily"]["sunset"][0],
        "utc_offset_seconds": j.get("utc_offset_seconds", 0),
    }


def minutes_to_sunset(sun: dict, now_utc: datetime | None = None) -> int | None:
    """Whole minutes until sunset (negative if it has passed); None if unknown."""
    try:
        sunset = datetime.fromisoformat(sun["sunset"])
    except (KeyError, ValueError, TypeError):
        return None
    now_utc = now_utc or datetime.now(timezone.utc)
    now_local = (now_utc + timedelta(seconds=sun.get("utc_offset_seconds", 0))).replace(tzinfo=None)
    return int((sunset - now_local).total_seconds() // 60)


def format_clock(iso: str) -> str:
    """'2026-10-10T18:03' -> '6:03 PM'."""
    return datetime.fromisoformat(iso).strftime("%I:%M %p").lstrip("0")