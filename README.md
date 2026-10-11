# wander

A screen-free, voice-first walking companion. Put your phone in your pocket, tap once, and talk.
It narrates the places, birds and plants near you, gives you small "touch grass" challenges,
keeps a life list of what you spot, and logs the walk to a map journal.

Built for the Hacktoberfest Open-Source AI Challenge, Week 1: Touch Grass.

## What it does
- **Voice in, voice out.** Local Whisper turns your speech into text, Gemma decides what you meant, ElevenLabs speaks the answer. The page stops listening by itself when you stop talking.
- **Grounded narration.** Nearby places (OpenStreetMap, Wikipedia), species commonly recorded nearby this month (iNaturalist) and weather are fetched once, and Gemma may only talk about what was fetched.
- **Touch-grass challenges.** About every 7 minutes (or on request) it asks you to do something small, like counting the sounds you can hear. Your answer gets a reply and is saved to the journal.
- **Life list.** Log a bird, plant or animal by voice; it tells you when a species is new to you.
- **Walk stats and daylight.** Ask how far you've walked, or when sunset is. It warns you once when sunset is close.
- **Loop planning.** Ask for a loop of a given length; it plans one with OpenRouteService.
- **Journal.** `/journal` shows each walk on a map with your route, track and sightings.

## Status
| Works | Not verified yet |
|---|---|
| Voice loop in a desktop browser and on a phone through a tunnel: mic, Whisper, Gemma intent routing, ElevenLabs voice | A full real walk with live phone GPS |
| Auto stop on silence, barge-in (tap to interrupt) | Turn-by-turn prompts for a planned loop |
| Life list, stats, challenges, sunset warning (unit tests, LLM mocked) | Place narration while moving |

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
Details, the WebSocket protocol and the backlog are in `AGENTS.md`.

## Quick start
Prerequisites: Python 3.11 or 3.12, [Ollama](https://ollama.com), and `ffmpeg` (`sudo apt install ffmpeg`).

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # add ELEVENLABS_API_KEY (and ORS_API_KEY for route planning)
ollama pull gemma3:4b
python -m pytest -q             # unit tests

uvicorn server.main:app --host 127.0.0.1 --port 8000
```
Open `http://localhost:8000`, tap once, and allow the microphone and location.
If port 8000 is busy, use any free port.

Optional settings in `.env`: `WHISPER_MODEL=small.en` for better accuracy (slower), `GEMMA_MODEL`, `ELEVENLABS_VOICE_ID`.

## Try it on a phone
Phones only allow the microphone and GPS on HTTPS, so the phone needs an HTTPS address.

- **Quick test:** `cloudflared tunnel --url http://localhost:8000` prints a temporary `https://....trycloudflare.com` address. It is public while it runs, so don't share it, and stop it when you're done.
- **Private:** put the server and the phone on the same [Tailscale](https://tailscale.com) network and run `sudo tailscale serve --bg 8000`.

Use earbuds, tap once to grant permissions, and keep the page open with the screen on.

### Testing without GPS
Desktop browsers often have no location. Add a test position to the address:
`http://localhost:8000/?lat=18.5204&lon=73.8567` (add `&sim=1` to simulate walking north).

## Say things like
- "Give me a challenge."
- "What birds should I hear around here?" / "When is sunset?"
- "Log a kingfisher." (it tells you when a species is new)
- "How far have I walked?"
- "I've got 45 minutes, plan me a loop."
- "Say that again." / "Skip." / "I'm done."

## Measuring it
`python -m scripts.eval_intents` prints intent accuracy. `python -m scripts.latency_report` prints median latency from real use (the server logs every turn to `data/metrics.jsonl`).

## Project layout
```
server/   FastAPI app, agent (pipeline, prompts, tools), audio (STT, TTS), walk logic, SQLite store
client/   the phone page (plain JS, no build step)
journal/  map viewer for past walks
scripts/  intent eval, latency report, terminal voice loop
tests/    unit tests (LLM and network mocked)
```

## Built with
Gemma (via Ollama), faster-whisper, ElevenLabs, FastAPI, SQLite, Leaflet. Open data: OpenStreetMap / Overpass, Wikipedia, iNaturalist, Open-Meteo, OpenRouteService.
Challenge categories: Gemma and ElevenLabs.

## Honest limitations
- It cannot see. It narrates what is likely or nearby from open data, and logs only what you tell it.
- It needs a location. Without GPS it can't narrate places or measure distance.
- Browsers suspend the microphone when the screen locks, so the page keeps the screen awake in your pocket.
- Silence detection is energy based and was tuned indoors; wind and traffic can make it listen until the 20 second cap.
- Small models make mistakes: Whisper mishears some phrases, and Gemma 4B sometimes picks the wrong intent. Ending a walk needs an explicit word like "done" so a mishearing can't end it.
- The public Overpass servers are often overloaded, so some places may be missing at times.
- Voice replies use the ElevenLabs API, so the offline fallback (Piper) needs extra setup.

## Roadmap
Offline place cache, Silero voice detection, journal polish, multiple guide voices, Hindi support.

## License
MIT, see `LICENSE`.

## Commit note
Built during the challenge window (Oct 5-11, 2026). Any commits after the deadline are listed here.