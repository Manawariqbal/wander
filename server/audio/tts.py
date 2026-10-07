"""Text-to-speech: ElevenLabs primary, Piper (local) fallback.

synthesize() returns (audio_bytes, mime_type).
"""
import asyncio
import os
import subprocess
import tempfile

import httpx

from server import config

ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


async def _elevenlabs(text: str, output_format: str) -> tuple[bytes, str]:
    url = ELEVEN_URL.format(voice_id=config.ELEVENLABS_VOICE_ID)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            url,
            params={"output_format": output_format},
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            json={"text": text, "model_id": config.ELEVENLABS_MODEL},
        )
        r.raise_for_status()
    mime = "audio/mpeg" if output_format.startswith("mp3") else "application/octet-stream"
    return r.content, mime


def _piper_blocking(text: str) -> tuple[bytes, str]:
    if not config.PIPER_MODEL:
        raise RuntimeError("PIPER_MODEL not set; no offline TTS fallback available")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    try:
        subprocess.run(
            [config.PIPER_BIN, "--model", config.PIPER_MODEL, "--output_file", out],
            input=text.encode(),
            check=True,
            capture_output=True,
        )
        with open(out, "rb") as fh:
            return fh.read(), "audio/wav"
    finally:
        os.unlink(out)


async def synthesize(text: str, output_format: str = "mp3_44100_128") -> tuple[bytes, str]:
    """Speak `text`. Falls back to Piper if ElevenLabs is unavailable."""
    if config.ELEVENLABS_API_KEY:
        try:
            return await _elevenlabs(text, output_format)
        except Exception as exc:  # network down, quota, etc.
            print(f"[tts] ElevenLabs failed ({exc!r}); trying Piper")
    return await asyncio.to_thread(_piper_blocking, text)
