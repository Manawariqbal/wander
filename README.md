# wander

A screen-free, voice-first walking companion. Put your phone in your pocket, tap once, and talk.
It plans a loop, tells you when to turn, narrates the plants, birds and history near you, and logs what you saw.

Built for the Hacktoberfest Open-Source AI Challenge, Week 1: Touch Grass.

**Open pieces:** faster-whisper (local STT), Gemma via Ollama (local reasoning), OpenStreetMap / Overpass,
OpenRouteService, iNaturalist, Wikipedia, Open-Meteo. **Voice:** ElevenLabs, with Piper as a local fallback.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # add ELEVENLABS_API_KEY and ORS_API_KEY
ollama pull gemma3:4b
python -m pytest -q                                     # unit tests

# 1) terminal smoke test (no phone): talk to it with your laptop mic
python -m scripts.voice_loop_cli --lat <your-lat> --lon <your-lon>

# 2) full server + phone client
uvicorn server.main:app --host 0.0.0.0 --port 8000
tailscale serve --https=443 localhost:8000              # gives the phone an HTTPS URL (needed for mic + GPS)
```

Open the Tailscale HTTPS URL on your phone, tap once to grant mic + location, then tap to talk / tap to stop.
Journal of past walks: `/journal`.

## Say things like
- "I've got 45 minutes, somewhere shady."
- "What birds should I hear around here?"
- "Log a kingfisher."
- "Say that again." / "Skip." / "I'm done."

## How it works
See `AGENTS.md` for architecture, the WebSocket protocol, and the build checklist.

## Honest limitations
- It cannot see. It narrates what is likely or nearby from open data, and logs only what you tell it.
- Browsers suspend the mic when the screen locks, so the page keeps the screen awake (pure black) in your pocket.
- Gemma 4B can still be wrong; narration is prompted to use only retrieved facts.

## Commit note
Built during the challenge window (Oct 5-11, 2026). Any commits after the deadline are listed here.
