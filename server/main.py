"""FastAPI app: websocket for the walking client + tiny REST API for the journal."""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server import config, postcard
from server.agent.pipeline import WalkAgent
from server.audio import stt, tts
from server.db.store import Store

store = Store(config.DB_PATH)
METRICS = Path("data/metrics.jsonl")


def log_metrics(m: dict) -> None:
    """Append one latency record; used by scripts/latency_report.py for the write-up."""
    try:
        METRICS.parent.mkdir(exist_ok=True)
        with METRICS.open("a") as f:
            f.write(json.dumps(m) + "\n")
    except Exception as exc:
        print(f"[metrics] could not write: {exc!r}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(stt.warmup)  # load Whisper once, up front
    yield


app = FastAPI(title="wander", lifespan=lifespan)


async def speak(ws: WebSocket, agent: WalkAgent, sentence_iter, metrics: dict | None = None) -> None:
    """Pipeline: sentences (Gemma) -> audio (TTS) -> client, overlapping generation and synthesis."""
    q: asyncio.Queue = asyncio.Queue(maxsize=3)

    async def producer():
        try:
            async for sent in sentence_iter:
                await q.put(sent)
        finally:
            await q.put(None)

    prod = asyncio.create_task(producer())
    spoken: list[str] = []
    seq = 0
    try:
        while (sent := await q.get()) is not None:
            audio, mime = await tts.synthesize(sent)
            if metrics is not None and "first_audio_s" not in metrics:
                metrics["first_audio_s"] = round(time.perf_counter() - metrics["t0"], 2)
            await ws.send_json({"type": "audio", "seq": seq, "mime": mime, "text": sent})
            await ws.send_bytes(audio)
            spoken.append(sent)
            seq += 1
    finally:
        prod.cancel()
        if spoken:
            agent.s.last_spoken = spoken
        if metrics is not None and "first_audio_s" in metrics:
            metrics["total_s"] = round(time.perf_counter() - metrics["t0"], 2)
            metrics["sentences"] = len(spoken)
            log_metrics({k: v for k, v in metrics.items() if k != "t0"})


async def guarded(coro) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"[ws] task failed: {exc!r}")


async def handle_audio(ws: WebSocket, agent: WalkAgent, audio: bytes) -> None:
    await ws.send_json({"type": "status", "state": "thinking"})
    print(f"[audio] received {len(audio)} bytes")
    metrics = {"kind": "utterance", "ts": round(time.time()), "t0": time.perf_counter()}
    try:
        text = await stt.transcribe(audio)
        metrics["stt_s"] = round(time.perf_counter() - metrics["t0"], 2)
        print(f"[stt] {text!r}")
        await ws.send_json({"type": "transcript", "text": text})
        if not text:
            await ws.send_json({"type": "status", "state": "ready"})
            return
        await speak(ws, agent, agent.on_utterance(text), metrics)
        await ws.send_json({"type": "status", "state": "ready"})
    except Exception:
        await ws.send_json({"type": "status", "state": "ready"})
        raise


@app.websocket("/ws/walk")
async def walk_ws(ws: WebSocket):
    await ws.accept()
    agent = WalkAgent(store)
    task: asyncio.Task | None = None

    def busy() -> bool:
        return task is not None and not task.done()

    async def cancel_current():
        if busy():
            task.cancel()
            await ws.send_json({"type": "stop"})

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                await cancel_current()  # barge-in: the walker spoke
                task = asyncio.create_task(guarded(handle_audio(ws, agent, msg["bytes"])))
            elif msg.get("text"):
                data = json.loads(msg["text"])
                if data["type"] == "gps":
                    agent.update_position(data["lat"], data["lon"])
                    if not busy():
                        task = asyncio.create_task(guarded(speak(ws, agent, agent.ambient())))
                elif data["type"] == "interrupt":
                    await cancel_current()
    finally:
        if busy():
            task.cancel()


# ---------- journal API ----------
@app.get("/api/walks")
def list_walks():
    return store.list_walks()


@app.get("/api/walks/{walk_id}")
def get_walk(walk_id: int):
    walk = store.get_walk(walk_id)
    if not walk:
        raise HTTPException(404, "walk not found")
    walk["postcard_audio"] = postcard.audio_path(walk_id) is not None
    return walk


@app.get("/api/lifelist")
def life_list():
    return store.life_list()


@app.post("/api/walks/{walk_id}/postcard")
async def make_postcard(walk_id: int, regenerate: bool = False):
    """Write (or return the cached) spoken postcard for a walk."""
    if not store.get_walk(walk_id):
        raise HTTPException(404, "walk not found")
    try:
        return await postcard.ensure_postcard(store, walk_id, regenerate)
    except Exception as exc:
        print(f"[postcard] failed: {exc!r}")
        raise HTTPException(502, "Could not write the postcard just now. Is Ollama running?")


@app.get("/api/walks/{walk_id}/postcard.audio")
def postcard_audio(walk_id: int):
    path = postcard.audio_path(walk_id)
    if not path:
        raise HTTPException(404, "no postcard audio yet")
    return FileResponse(path, media_type="audio/mpeg" if path.suffix == ".mp3" else "audio/wav")


# static mounts last so they don't shadow the routes above
app.mount("/journal", StaticFiles(directory="journal", html=True), name="journal")
app.mount("/", StaticFiles(directory="client", html=True), name="client")