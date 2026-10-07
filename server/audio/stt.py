"""Local speech-to-text with faster-whisper."""
import asyncio
import io
from functools import lru_cache

from faster_whisper import WhisperModel

from server import config


@lru_cache(maxsize=1)
def _model() -> WhisperModel:
    return WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE,
    )


def transcribe_bytes(audio: bytes) -> str:
    """Transcribe an encoded audio blob (webm/opus, wav, mp3...). Blocking."""
    segments, _info = _model().transcribe(
        io.BytesIO(audio),
        language="en",
        vad_filter=True,
        beam_size=1,
    )
    return " ".join(s.text.strip() for s in segments).strip()


async def transcribe(audio: bytes) -> str:
    return await asyncio.to_thread(transcribe_bytes, audio)


def warmup() -> None:
    _model()
