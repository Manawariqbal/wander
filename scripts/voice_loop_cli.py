"""Day-1 smoke test: talk to the agent from the terminal, no phone needed.

    python -m scripts.voice_loop_cli --lat 18.5204 --lon 73.8567

Press Enter to start recording, Enter again to stop. Ctrl+C to quit.
"""
import argparse
import asyncio
import io

import numpy as np
import sounddevice as sd
import soundfile as sf

from server import config
from server.agent.pipeline import WalkAgent
from server.audio import stt, tts
from server.db.store import Store

SR = 16000


def record() -> bytes:
    input("Enter to start recording...")
    frames = []

    def cb(indata, _frames, _time, _status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb):
        input("Recording... Enter to stop.")
    audio = np.concatenate(frames) if frames else np.zeros((0, 1), dtype="float32")
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV")
    return buf.getvalue()


def play(audio: bytes, mime: str) -> None:
    if mime == "audio/wav":
        data, sr = sf.read(io.BytesIO(audio), dtype="float32")
    else:  # raw 16-bit PCM @ 22.05 kHz from ElevenLabs
        data, sr = np.frombuffer(audio, dtype="<i2").astype("float32") / 32768, 22050
    sd.play(data, sr)
    sd.wait()


async def main(lat: float, lon: float) -> None:
    agent = WalkAgent(Store(config.DB_PATH))
    agent.update_position(lat, lon)
    print("Loading models and prefetching the area...")
    stt.warmup()
    async for sent in agent.ambient():  # greeting
        print("AI:", sent)
        play(*await tts.synthesize(sent, "pcm_22050"))

    while True:
        wav = await asyncio.to_thread(record)
        text = await stt.transcribe(wav)
        print("You:", text)
        if not text:
            continue
        async for sent in agent.on_utterance(text):
            print("AI:", sent)
            play(*await tts.synthesize(sent, "pcm_22050"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    a = ap.parse_args()
    asyncio.run(main(a.lat, a.lon))
