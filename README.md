# wander

A screen-free, voice-first walking companion.  
Put your phone in your pocket, tap once, and talk.

It narrates nearby places, birds and plants, gives you small “touch grass” challenges, keeps a life list of what you spot, and logs every walk to a map journal.

Built for the **Hacktoberfest Open-Source AI Challenge**, Week 1: Touch Grass.

---

## What it does

- **Voice in, voice out**  
  Local Whisper turns your speech into text → Gemma decides the intent → ElevenLabs speaks the reply. Listening stops automatically when you stop talking.

- **Grounded narration**  
  Nearby places (OpenStreetMap + Wikipedia), species recorded in the area this month (iNaturalist), and weather are fetched once. Gemma is only allowed to talk about what was actually retrieved.

- **Touch-grass challenges**  
  Roughly every 7 minutes (or on request) it asks you to do something small — count the sounds you hear, notice the light, etc. Your answer is replied to and saved in the journal.

- **Life list**  
  Say “Log a kingfisher” and it records the sighting. It tells you when a species is new to you.

- **Walk stats & daylight**  
  Ask how far you’ve walked or when sunset is. It warns you once when sunset is approaching.

- **Loop planning**  
  “I’ve got 45 minutes, plan me a loop” → OpenRouteService generates a walking loop of the requested length.

- **Journal**  
  `/journal` shows every past walk on a map with your route, GPS track, and sightings.

---

## Status

| Works | Not verified yet |
|-------|------------------|
| Voice loop (desktop browser + phone via tunnel): mic, Whisper, Gemma intent routing, ElevenLabs | Full real walk with live phone GPS |
| Auto-stop on silence + barge-in (tap to interrupt) | Turn-by-turn prompts for a planned loop |
| Life list, stats, challenges, sunset warning (unit tests, LLM mocked) | Place narration while moving |

---

## How it works

```
 PHONE / BROWSER (client/)                 SERVER (server/)
┌──────────────────────────┐   WebSocket  ┌────────────────────────────────────┐
│ tap to talk, auto-stop   │ ──audio────▶ │ ffmpeg decode → faster-whisper     │
│ GPS ping every ~8 s      │ ──gps──────▶ │            │                       │
│ plays audio replies      │ ◀──mp3────── │            ▼                       │
└──────────────────────────┘              │ WalkAgent ◀──▶ Gemma (Ollama)      │
                                          │  intents · narration · challenges  │
                                          │  tools: places, species, weather,  │
                                          │         sun times, routing         │
                                          │            ▼                       │
                                          │ sentence splitter → ElevenLabs TTS │
                                          │ SQLite: walks, sightings, track    │
                                          └────────────────────────────────────┘
```

Full WebSocket protocol, architecture notes, and backlog are in [`AGENTS.md`](AGENTS.md).

---

## Quick start

**Prerequisites**
- Python 3.11 or 3.12
- [Ollama](https://ollama.com)
- `ffmpeg` (`sudo apt install ffmpeg`)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # add ELEVENLABS_API_KEY (and ORS_API_KEY for routing)
ollama pull gemma3:4b
python -m pytest -q                                 # unit tests

uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`, tap once, and allow the microphone + location.

Optional `.env` settings:
- `WHISPER_MODEL=small.en` (better accuracy, slower)
- `GEMMA_MODEL`
- `ELEVENLABS_VOICE_ID`

---

## Try it on a phone

Phones only allow the microphone and GPS on HTTPS.

**Quick public test**
```bash
cloudflared tunnel --url http://localhost:8000
```
It prints a temporary `https://….trycloudflare.com` address. Don’t share it and stop the tunnel when finished.

**Private (recommended)**
Put the server and phone on the same [Tailscale](https://tailscale.com) network, then:
```bash
sudo tailscale serve --bg 8000
```

Use earbuds, tap once to grant permissions, and keep the page open (the page holds a wake lock so the screen doesn’t turn off).

### Testing without GPS

Desktop browsers often have no location. Append a test position:
```
http://localhost:8000/?lat=18.5204&lon=73.8567
```
Add `&sim=1` to simulate walking north.

---

## Things you can say

- “Give me a challenge.”
- “What birds should I hear around here?” / “When is sunset?”
- “Log a kingfisher.” (it tells you if it’s new)
- “How far have I walked?”
- “I’ve got 45 minutes, plan me a loop.”
- “Say that again.” / “Skip.” / “I’m done.”

---

## Measuring it

```bash
python -m scripts.eval_intents          # intent accuracy
python -m scripts.latency_report        # median latency from real use
```

The server logs every turn to `data/metrics.jsonl`.

---

## Project layout

```
server/     FastAPI app, agent (pipeline, prompts, tools), audio (STT/TTS), walk logic, SQLite
client/     Phone page (plain JS, no build step)
journal/    Map viewer for past walks
scripts/    Intent eval, latency report, terminal voice loop
tests/      Unit tests (LLM and network mocked)
```

---

## Built with

- **Models**: Gemma 3 (via Ollama), faster-whisper
- **Voice**: ElevenLabs (Piper as offline fallback)
- **Backend**: FastAPI + WebSocket, SQLite
- **Maps**: Leaflet
- **Open data**: OpenStreetMap / Overpass, Wikipedia, iNaturalist, Open-Meteo, OpenRouteService

Challenge categories: **Gemma** and **ElevenLabs**.

---

## Honest limitations

- It cannot see. It narrates what is likely or nearby from open data and only logs what you tell it.
- It needs a location. Without GPS it can’t narrate places or measure distance.
- Browsers suspend the microphone when the screen locks, so the page keeps the screen awake.
- Silence detection is energy-based and was tuned indoors; wind and traffic can keep it listening until the 20-second cap.
- Small models make mistakes: Whisper mishears some phrases, Gemma 4B sometimes picks the wrong intent. Ending a walk requires an explicit word like “done”.
- Public Overpass servers are often overloaded, so some places may be missing.
- Voice replies use the ElevenLabs API; the offline Piper fallback needs extra setup.

---

## Roadmap

- Offline place cache (`poi_cache`)
- Hands-free mode with Silero VAD
- Journal polish (narrated POIs on map + end-of-walk summary)
- Multiple guide voices
- Hindi support
- Optional: BirdNET on-device bird call ID
- Optional: deploy journal + API to Render (inference stays local)

---

## License

MIT — see [`LICENSE`](LICENSE).

---

Built during the challenge window (5–11 Oct 2026).  
Any commits after the deadline are listed here.
```