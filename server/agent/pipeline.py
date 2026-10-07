"""The brain: turns utterances and GPS fixes into sentences to speak.

Everything here yields plain strings (sentences). Audio, websockets and
persistence glue live elsewhere. This is the file to wrap in LangGraph later
if you want an explicit graph; the seams are already node-shaped:
classify -> (plan | ask | log | repeat | end) -> narrate.
"""
import time
from typing import AsyncIterator

from server import config
from server.agent import llm, prompts
from server.agent.tools import routing
from server.db.store import Store
from server.walk import geofence, prefetch
from server.walk.session import Session

NAV_TRIGGER_M = 25


class WalkAgent:
    def __init__(self, store: Store):
        self.store = store
        self.s = Session()

    # ---------- position ----------
    def update_position(self, lat: float, lon: float) -> None:
        self.s.lat, self.s.lon = lat, lon
        if self.s.walk_id is None:
            self.s.walk_id = self.store.start_walk(lat, lon)
        self.store.add_track(self.s.walk_id, lat, lon)

    # ---------- ambient (called on GPS pings when idle) ----------
    async def ambient(self) -> AsyncIterator[str]:
        s = self.s
        if s.lat is None or s.ended:
            return

        if not s.prefetched and not s.prefetching:
            s.prefetching = True
            try:
                data = await prefetch.prefetch_area(s.lat, s.lon)
                s.pois, s.species, s.weather = data["pois"], data["species"], data["weather"]
                s.prefetched = True
            finally:
                s.prefetching = False
            temp = s.weather.get("temperature_2m")
            greeting = "Ready when you are."
            if temp is not None:
                greeting = f"Ready when you are. It's about {round(temp)} degrees out. Tap the screen and tell me what you'd like to do."
            yield greeting
            return

        # 1) turn-by-turn has priority
        if s.route and s.next_step < len(s.route["steps"]):
            step = s.route["steps"][s.next_step]
            if geofence.distance_m(s.lat, s.lon, step["lat"], step["lon"]) <= NAV_TRIGGER_M:
                s.next_step += 1
                yield step["instruction"] + "."
                return

        # 2) a nearby point of interest, rate-limited
        if time.time() - s.last_narration_ts < config.NARRATION_COOLDOWN_S:
            return
        poi = geofence.nearest_unseen(s.pois, s.lat, s.lon, s.narrated, config.GEOFENCE_RADIUS_M)
        if poi:
            s.narrated.add(geofence.poi_key(poi))
            s.last_narration_ts = time.time()
            ctx = f"{poi['name']} ({poi.get('kind')}): {poi['facts']}"
            task = "Mention this place the walker is passing right now, in 2 or 3 short sentences."
            async for sent in llm.sentences(llm.chat_stream(prompts.narration_prompt(task, ctx))):
                yield sent

    # ---------- utterances ----------
    async def on_utterance(self, text: str) -> AsyncIterator[str]:
        s = self.s
        try:
            intent = await llm.chat_json(
                [{"role": "system", "content": prompts.INTENT_SYSTEM}, {"role": "user", "content": text}],
                prompts.INTENT_SCHEMA,
            )
        except Exception as exc:
            print(f"[intent] classification failed: {exc!r}")
            intent = {"intent": "ask"}
        kind = intent.get("intent", "ask")
        print(f"[intent] {kind} {intent}")

        if kind == "skip":
            yield "Okay."
        elif kind == "repeat":
            for sent in s.last_spoken or ["I haven't said anything yet."]:
                yield sent
        elif kind == "log_sighting":
            subject = intent.get("subject") or text
            if s.walk_id is not None:
                self.store.add_sighting(s.walk_id, s.lat, s.lon, intent.get("subject_type"), subject, text)
            yield f"Logged: {subject}."
        elif kind == "plan_route":
            async for sent in self._plan(intent):
                yield sent
        elif kind == "end_walk":
            async for sent in self._end():
                yield sent
        else:  # ask / chitchat
            task = f"Answer the walker's question briefly: {text}"
            async for sent in llm.sentences(llm.chat_stream(prompts.narration_prompt(task, self._context()))):
                yield sent

    # ---------- helpers ----------
    async def _plan(self, intent: dict) -> AsyncIterator[str]:
        s = self.s
        if s.lat is None:
            yield "I don't have your location yet. Give me a few seconds."
            return
        try:
            route = await routing.plan_loop(s.lat, s.lon, intent.get("minutes"), intent.get("km"))
        except Exception as exc:
            print(f"[route] failed: {exc!r}")
            yield "Sorry, I couldn't plan a route just now."
            return
        s.route, s.next_step = route, 0
        if s.walk_id is not None:
            self.store.set_route(s.walk_id, route)
        km = route["distance_m"] / 1000
        yield f"Found a loop of about {km:.1f} kilometres, roughly {route['duration_min']} minutes."
        if route["steps"]:
            yield "I'll tell you when to turn."

    async def _end(self) -> AsyncIterator[str]:
        s = self.s
        sightings = self.store.sightings(s.walk_id) if s.walk_id else []
        ctx = "Logged sightings: " + (", ".join(x["subject"] for x in sightings) or "none") + "."
        task = "Give a warm two-sentence wrap-up of the walk and mention what they logged, if anything."
        parts = []
        async for sent in llm.sentences(llm.chat_stream(prompts.narration_prompt(task, ctx))):
            parts.append(sent)
            yield sent
        if s.walk_id is not None:
            self.store.end_walk(s.walk_id, " ".join(parts))
        s.ended = True

    def _context(self) -> str:
        s = self.s
        lines = []
        if s.weather:
            lines.append(
                f"Weather now: {s.weather.get('temperature_2m')} C, "
                f"wind {s.weather.get('wind_speed_10m')} km/h, precipitation {s.weather.get('precipitation')} mm."
            )
        if s.lat is not None and s.pois:
            near = sorted(s.pois, key=lambda p: geofence.distance_m(s.lat, s.lon, p["lat"], p["lon"]))[:5]
            lines.append("Nearby places, closest first:")
            for p in near:
                d = round(geofence.distance_m(s.lat, s.lon, p["lat"], p["lon"]))
                lines.append(f"- {p['name']} ({p.get('kind')}, {d} m away): {p.get('facts') or 'no details'}")
        if s.species.get("birds"):
            lines.append("Birds commonly recorded nearby this month: " + ", ".join(s.species["birds"]) + ".")
        if s.species.get("plants"):
            lines.append("Plants commonly recorded nearby this month: " + ", ".join(s.species["plants"]) + ".")
        return "\n".join(lines) or "No local data is available yet."
