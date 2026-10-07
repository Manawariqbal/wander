"""FastAPI app: websocket for the walking client + tiny REST API for the journal."""
import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.staticfiles import StaticFiles

from server import config
from server.agent.pipeline import WalkAgent
from server.audio import stt, tts
from server.db.store import Store

store = Store(config.DB_PATH)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(stt.warmup)  # load Whisper once, up front
    yield


app = FastAPI(title="wander", lifespan=lifespan)


async def speak(ws: WebSocket, agent: WalkAgent, sentence_iter) -> None:
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
            await ws.send_json({"type": "audio", "seq": seq, "mime": mime, "text": sent})
            await ws.send_bytes(audio)
            spoken.append(sent)
            seq += 1
    finally:
        prod.cancel()
        if spoken:
            agent.s.last_spoken = spoken


async def guarded(coro) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"[ws] task failed: {exc!r}")


async def handle_audio(ws: WebSocket, agent: WalkAgent, audio: bytes) -> None:
    await ws.send_json({"type": "status", "state": "thinking"})
    text = await stt.transcribe(audio)
    await ws.send_json({"type": "transcript", "text": text})
    if not text:
        return
    await speak(ws, agent, agent.on_utterance(text))


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
    return walk


# static mounts last so they don't shadow the routes above
app.mount("/journal", StaticFiles(directory="journal", html=True), name="journal")
app.mount("/", StaticFiles(directory="client", html=True), name="client")
