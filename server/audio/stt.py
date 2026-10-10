"""Local speech-to-text with faster-whisper (decodes via ffmpeg)."""
import asyncio
import re
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from server import config

SR = 16000
BEEP_TRIM_S = 0.25  # drop the start beep the browser records; lower to 0.15 if first words get clipped

# Phrases Whisper tends to invent when there is no real speech in the audio.
_HALLUCINATIONS = (
    "see you in the next video", "thanks for watching", "thank you for watching",
    "make a video", "please subscribe", "subtitles by", "amara.org",
)

# Biases Whisper toward the vocabulary it will actually hear.
_PROMPT = (
    "Voice commands for a walking companion: plan a 30 minute loop, "
    "what birds should I hear, what's around me, log a kingfisher, say that again, I'm done."
)


@lru_cache(maxsize=1)
def _model() -> WhisperModel:
    return WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE,
    )


def _decode_ffmpeg(audio: bytes) -> np.ndarray:
    """Decode browser audio (webm/mp4) to 16 kHz mono float32."""
    try:
        p = subprocess.run(
            ["ffmpeg", "-nostdin", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(SR), "pipe:1"],
            input=audio, capture_output=True, check=True,
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not installed: run `sudo apt install ffmpeg`")
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _save_debug(samples: np.ndarray) -> None:
    Path("data").mkdir(exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open("data/last_utterance.wav", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _norm(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower()).strip()


def _is_hallucination(text: str) -> bool:
    t = _norm(text)
    if t in ("thank you", "you", "bye") or any(p in t for p in _HALLUCINATIONS):
        return True
    # Whisper sometimes echoes the initial prompt when the audio is unclear
    return len(t) > 25 and t in _norm(_PROMPT)


def _run(samples: np.ndarray) -> str:
    segments, _info = _model().transcribe(
        samples,
        language="en",
        vad_filter=True,
        vad_parameters=dict(threshold=0.3, min_silence_duration_ms=500),
        beam_size=1,
        condition_on_previous_text=False,
        initial_prompt=_PROMPT,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def transcribe_bytes(audio: bytes) -> str:
    samples = _decode_ffmpeg(audio)
    samples = samples[int(BEEP_TRIM_S * SR):]  # remove the start beep
    if len(samples) == 0:
        print("[stt] ffmpeg produced no audio")
        return ""
    peak = float(np.abs(samples).max())
    rms = float(np.sqrt(np.mean(samples ** 2)))
    print(f"[stt] v3 decoded {len(samples) / SR:.1f}s, peak={peak:.3f}, rms={rms:.4f}")
    _save_debug(samples)

    if peak < 0.01:
        print("[stt] audio is essentially silent: check the browser's microphone input")
        return ""
    if peak < 0.5:  # boost quiet recordings
        samples = samples * (0.8 / peak)

    text = _run(samples)
    if not text:
        print("[stt] no speech detected in this clip (listen to data/last_utterance.wav)")
        return ""
    if _is_hallucination(text):
        print(f"[stt] discarded likely hallucination: {text!r}")
        return ""
    return text


async def transcribe(audio: bytes) -> str:
    return await asyncio.to_thread(transcribe_bytes, audio)


def warmup() -> None:
    _model()