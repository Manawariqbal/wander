"""The brain: turns utterances and GPS fixes into sentences to speak.

Everything here yields plain strings (sentences). Audio, websockets and
persistence glue live elsewhere. This is the file to wrap in LangGraph later
if you want an explicit graph; the seams are already node-shaped:
classify -> (plan | ask | log | stats | challenge | repeat | end) -> narrate.
"""
import re
import time
from typing import AsyncIterator

from server import config
from server.agent import llm, prompts
from server.agent.tools import routing, weather
from server.db.store import SPECIES_KINDS, Store, normalize_subject
from server.walk import challenges, geofence, prefetch, stats
from server.walk.session import Session

NAV_TRIGGER_M = 25
QUIET_BEFORE_CHALLENGE_S = 45  # never stack a challenge right after a narration


class WalkAgent:
    def __init__(self, store: Store):
        self.store = store
        self.s = Session()

    # ---------- position ----------
    def update_position(self, lat: float, lon: float) -> None:
        self.s.lat, self.s.lon = lat, lon
        if self.s.walk_id is None:
            self.s.walk_id = self.store.start_walk(lat, lon)
            self.s.started_ts = time.time()
        self.store.add_track(self.s.walk_id, lat, lon)

    # ---------- ambient (called on GPS pings when idle) ----------
    async def ambient(self) -> AsyncIterator[str]:
        s = self.s
        if s.lat is None or s.ended:
            return

        if not s.prefetched and not s.prefetching:
            s.prefetching = True
            try:
                data = await prefetch.prefetch_area(s.lat, s.lon, store=self.store)
                s.pois, s.species, s.weather, s.sun = (
                    data["pois"], data["species"], data["weather"], data["sun"]
                )
                s.prefetched = True
                s.last_challenge_ts = time.time()
            finally:
                s.prefetching = False
            temp = s.weather.get("temperature_2m")
            greeting = "Ready when you are."
            if temp is not None:
                greeting = (
                    f"Ready when you are. It's about {round(temp)} degrees out. "
                    "Tap the screen and tell me what you'd like to do."
                )
            yield greeting
            return

        # 1) turn-by-turn has priority
        if s.route and s.next_step < len(s.route["steps"]):
            step = s.route["steps"][s.next_step]
            if geofence.distance_m(s.lat, s.lon, step["lat"], step["lon"]) <= NAV_TRIGGER_M:
                s.next_step += 1
                yield step["instruction"] + "."
                return

        # 2) one-time daylight heads-up
        if s.sun and not s.sunset_warned:
            mins = weather.minutes_to_sunset(s.sun)
            if mins is not None and 0 < mins <= config.SUNSET_WARN_MIN:
                s.sunset_warned = True
                yield (
                    f"Heads up: sunset is in about {mins} minutes, "
                    "so you may want to start heading back."
                )
                return

        # 3) a nearby point of interest, rate-limited
        now = time.time()
        if now - s.last_narration_ts >= config.NARRATION_COOLDOWN_S:
            poi = geofence.nearest_unseen(
                s.pois, s.lat, s.lon, s.narrated, config.GEOFENCE_RADIUS_M
            )
            if poi:
                s.narrated.add(geofence.poi_key(poi))
                s.last_narration_ts = now
                ctx = f"{poi['name']} ({poi.get('kind')}): {poi['facts']}"
                task = "Mention this place the walker is passing right now, in 2 or 3 short sentences."
                async for sent in llm.sentences(
                    llm.chat_stream(prompts.narration_prompt(task, ctx))
                ):
                    yield sent
                return

        # 4) a touch-grass challenge every few minutes
        if (
            now - s.last_challenge_ts >= config.CHALLENGE_EVERY_S
            and now - s.last_narration_ts >= QUIET_BEFORE_CHALLENGE_S
        ):
            yield self._issue_challenge()

    # ---------- utterances ----------
    async def on_utterance(self, text: str) -> AsyncIterator[str]:
        s = self.s
        try:
            intent = await llm.chat_json(
                [
                    {"role": "system", "content": prompts.INTENT_SYSTEM},
                    {"role": "user", "content": text},
                ],
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
            s.pending_challenge = None
            yield self._log_sighting(intent, text)
        elif kind == "stats":
            yield self._stats_sentence()
        elif kind == "challenge":
            yield self._issue_challenge()
        elif kind == "plan_route":
            async for sent in self._plan(intent):
                yield sent
        elif kind == "end_walk":
            # a mis-heard phrase must not be able to end a walk
            if re.search(r"\b(done|finish|finished|end|over)\b", text.lower()):
                async for sent in self._end():
                    yield sent
            else:
                yield "Did you want to end the walk? Say I'm done to confirm."
        elif kind == "chitchat" and s.pending_challenge:
            async for sent in self._answer_challenge(text):
                yield sent
        else:
            # Special-case sunset / sunrise questions
            if re.search(r"\b(sunset|sunrise|sun\s*set|daylight|how much light)\b", text.lower()):
                async for sent in self._answer_sun(text):
                    yield sent
            else:
                # Generic ask / chitchat
                task = f"Answer the walker's question briefly: {text}"
                async for sent in llm.sentences(
                    llm.chat_stream(prompts.narration_prompt(task, self._context()))
                ):
                    yield sent

    # ---------- helpers ----------
    async def _answer_sun(self, text: str) -> AsyncIterator[str]:
        """Reliable answer for sunset / sunrise questions."""
        s = self.s
        if not s.sun:
            yield "I don't have the local sunset time yet. Give me a few more seconds to fetch it."
            return

        mins = weather.minutes_to_sunset(s.sun)
        sunset_clock = weather.format_clock(s.sun["sunset"])
        sunrise_clock = weather.format_clock(s.sun.get("sunrise", ""))

        if "sunrise" in text.lower():
            yield f"Sunrise today was at {sunrise_clock}."
            return

        if mins is None:
            yield f"Sunset today is at {sunset_clock}."
        elif mins > 0:
            yield f"Sunset today is at {sunset_clock}, about {mins} minutes from now."
        else:
            yield f"Sunset was at {sunset_clock}. It's already dark."

    def _issue_challenge(self) -> str:
        s = self.s
        _idx, text = challenges.next_challenge(s.used_challenges)
        s.pending_challenge = text
        s.last_challenge_ts = s.last_narration_ts = time.time()
        return text

    async def _answer_challenge(self, text: str) -> AsyncIterator[str]:
        s = self.s
        challenge, s.pending_challenge = s.pending_challenge, None
        if s.walk_id is not None:
            self.store.add_sighting(
                s.walk_id, s.lat, s.lon, "challenge", text, f"challenge: {challenge}"
            )
        ctx = f"Challenge you gave: {challenge}\nWhat the walker said: {text}"
        task = "React warmly to what the walker found in one or two short sentences. Do not add any facts."
        async for sent in llm.sentences(
            llm.chat_stream(prompts.narration_prompt(task, ctx))
        ):
            yield sent

    def _log_sighting(self, intent: dict, text: str) -> str:
        s = self.s
        subject = normalize_subject(intent.get("subject") or text)
        kind = intent.get("subject_type")
        reply = f"Logged: {subject}."
        if s.walk_id is not None:
            is_new = kind in SPECIES_KINDS and self.store.times_seen(subject) == 0
            self.store.add_sighting(s.walk_id, s.lat, s.lon, kind, subject, text)
            if is_new:
                reply += f" That's a new one for your life list, number {self.store.species_count()}."
        return reply

    def _stats_sentence(self) -> str:
        s = self.s
        points = self.store.track_points(s.walk_id) if s.walk_id else []
        elapsed = time.time() - s.started_ts if s.started_ts else 0.0
        return stats.stats_sentence(stats.track_distance_m(points), elapsed)

    async def _plan(self, intent: dict) -> AsyncIterator[str]:
        s = self.s
        if s.lat is None:
            yield "I don't have your location yet. Give me a few seconds."
            return
        try:
            route = await routing.plan_loop(
                s.lat, s.lon, intent.get("minutes"), intent.get("km")
            )
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
        """Warm, structured spoken summary when the walker says they're done."""
        s = self.s
        if s.walk_id is None:
            yield "Okay, take care."
            s.ended = True
            return

        # Collect facts
        points = self.store.track_points(s.walk_id)
        distance_m = stats.track_distance_m(points)
        elapsed = time.time() - s.started_ts if s.started_ts else 0.0
        minutes = max(1, round(elapsed / 60))

        sightings = self.store.sightings(s.walk_id)
        species = [x["subject"] for x in sightings if x["kind"] in SPECIES_KINDS]
        challenges = [x for x in sightings if x["kind"] == "challenge"]
        new_species = self.store.new_species_for_walk(s.walk_id)

        # Build a clear spoken summary
        parts = []

        if distance_m < 50:
            parts.append(f"That was a short one — about {minutes} minutes.")
        else:
            km = distance_m / 1000
            parts.append(f"You walked about {km:.1f} kilometres in {minutes} minutes.")

        if species:
            if len(species) == 1:
                parts.append(f"You logged one species: {species[0]}.")
            else:
                parts.append(f"You logged {len(species)} species, including {', '.join(species[:3])}.")
            if new_species:
                if len(new_species) == 1:
                    parts.append(f"{new_species[0].capitalize()} was new for your life list.")
                else:
                    parts.append(f"{len(new_species)} of them were new for your life list.")
        else:
            parts.append("You didn't log any birds or plants this time.")

        if challenges:
            parts.append(f"You also completed {len(challenges)} challenge{'s' if len(challenges) != 1 else ''}.")

        parts.append("Nice work getting outside. Your walk is saved in the journal.")

        summary_text = " ".join(parts)

        # Speak it sentence by sentence
        for sent in re.split(r'(?<=[.!?])\s+', summary_text):
            if sent.strip():
                yield sent.strip()

        # Persist
        self.store.end_walk(s.walk_id, summary_text)
        s.ended = True

    def _context(self) -> str:
        s = self.s
        lines = []
        if s.weather:
            lines.append(
                f"Weather now: {s.weather.get('temperature_2m')} C, "
                f"wind {s.weather.get('wind_speed_10m')} km/h, "
                f"precipitation {s.weather.get('precipitation')} mm."
            )
        if s.sun:
            mins = weather.minutes_to_sunset(s.sun)
            if mins is not None:
                when = f"in about {mins} minutes" if mins > 0 else "already passed"
                lines.append(
                    f"Sunset today is at {weather.format_clock(s.sun['sunset'])}, {when}."
                )
        if s.lat is not None and s.pois:
            near = sorted(
                s.pois,
                key=lambda p: geofence.distance_m(s.lat, s.lon, p["lat"], p["lon"]),
            )[:5]
            lines.append("Nearby places, closest first:")
            for p in near:
                d = round(geofence.distance_m(s.lat, s.lon, p["lat"], p["lon"]))
                lines.append(
                    f"- {p['name']} ({p.get('kind')}, {d} m away): "
                    f"{p.get('facts') or 'no details'}"
                )
        if s.species.get("birds"):
            lines.append(
                "Birds commonly recorded nearby this month: "
                + ", ".join(s.species["birds"]) + "."
            )
        if s.species.get("plants"):
            lines.append(
                "Plants commonly recorded nearby this month: "
                + ", ".join(s.species["plants"]) + "."
            )
        return "\n".join(lines) or "No local data is available yet."