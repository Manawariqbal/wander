# AGENTS.md: spec for AI coding agents working on this repo

Project: **wander**, a voice-first walking companion (see README). Deadline: submit the DEV post
by Oct 11, 2026 (11:59 PM PDT). The repo must contain only work started inside the challenge window.

## Architecture (one paragraph)
Phone PWA (`client/`) sends GPS pings (JSON) and utterances (binary webm/mp4 blob) over `WS /ws/walk` to a
FastAPI server on a laptop. Server: faster-whisper -> `WalkAgent` (`server/agent/pipeline.py`) -> Gemma via
Ollama -> sentence splitter -> TTS (ElevenLabs, Piper fallback) -> audio frames back to the phone.
Walk data (walks, sightings, GPS track) lives in SQLite; `/journal` renders it on a Leaflet map.

## Websocket protocol
Client -> server
- text `{"type":"gps","lat":..,"lon":..,"acc":..}` every ~8 s
- text `{"type":"interrupt"}` when the user starts talking
- binary: one complete recorded utterance (webm/opus or mp4/aac)

Server -> client
- text `{"type":"status","state":"thinking"}`
- text `{"type":"transcript","text":"..."}`
- text `{"type":"audio","seq":n,"mime":"audio/mpeg","text":"..."}` immediately followed by one binary frame of audio
- text `{"type":"stop"}` (barge-in: client must clear its playback queue)

## Conventions
- Python 3.11+, async everywhere I/O happens; blocking work goes through `asyncio.to_thread`.
- Anything spoken must come from retrieved facts (see `prompts.NARRATOR_SYSTEM`). Never let the model invent species/history.
- Keep narration to 2-4 short sentences, plain text, no markdown (it is read aloud).
- Network lookups must degrade gracefully (see `prefetch.py`); a failed lookup never crashes a walk.
- Keep prompts in `server/agent/prompts.py`. Keep config in `server/config.py`.

## Status
Written but NOT yet run end to end. Compiled and unit-tested only for pure logic (geofence, sentence splitter).
First job: run the smoke test, fix whatever breaks, in this order:

1. [ ] `ollama pull gemma3:4b`; confirm `python -m scripts.eval_intents` runs and prints accuracy.
2. [ ] `python -m scripts.voice_loop_cli --lat .. --lon ..` works: mic -> Whisper -> Gemma -> ElevenLabs -> speakers.
3. [ ] Verify each tool against the live API with a real coordinate: iNaturalist, Overpass, Wikipedia GeoSearch, Open-Meteo, ORS round trip (check `steps[].way_points` handling).
4. [ ] Start the server; open it over Tailscale HTTPS on a phone; confirm mic, GPS, wake lock, audio playback (iOS needs the first tap to unlock audio).
5. [ ] Check Gemma's JSON-schema output (`format`) works for the installed Gemma version; if not, fall back to prompt-only JSON + `json.loads` with a retry.
6. [ ] Short outdoor test: walk around the block; confirm geofence narration fires once per POI and respects the cooldown.

## Backlog (in priority order)
1. SQLite `poi_cache` so a walk can run with no internet except TTS (schema has a TODO). Prefetch should write it, and `ambient` should read from it.
2. Hands-free mode: browser VAD (Silero) instead of tap-to-talk, behind a toggle.
3. Journal polish: show narrated POIs on the map, add an end-of-walk summary card.
4. Wrap `WalkAgent` in LangGraph (nodes: classify, plan, ask, log, repeat, end, narrate) if it improves clarity for the write-up.
5. Latency numbers: log STT time, time-to-first-sentence, time-to-first-audio per turn; report medians in the post.
6. Optional: BirdNET for on-device bird call ID (log a confirmed species automatically).
7. Optional: deploy `journal/` + API to Render (inference stays local; sync the SQLite export).

## Known risks
- ORS `round_trip` can return odd loops; retry with a new seed if distance is off by >30%.
- Overpass public endpoint rate-limits; prefetch once per walk, not per ping.
- ElevenLabs free tier has output-format limits; `mp3_44100_128` is the safe default.
- Gemma 4B may hallucinate when context is thin; keep the "not sure" fallback in the narrator prompt.
