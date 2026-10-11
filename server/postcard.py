"""Walk postcard: a short spoken story of a finished walk, written by Gemma and read by ElevenLabs."""
from datetime import datetime
from pathlib import Path

from server.agent import llm
from server.audio import tts
from server.db.store import SPECIES_KINDS, Store
from server.walk import stats

AUDIO_DIR = Path("data/postcards")

POSTCARD_SYSTEM = """You write short spoken postcards about a walk that just ended.
Rules:
- 70 to 110 words, in the second person ("you").
- Warm, specific and a little poetic, but plain. No lists, no markdown, no emojis. It will be read aloud.
- Use ONLY the facts provided. Never invent sights, sounds, weather, places or feelings the facts do not support.
- If little was logged, say so gently and write about the simple act of going outside.
- End with one short, kind line that invites another walk."""


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def walk_facts(store: Store, walk_id: int) -> dict | None:
    """Collect everything a postcard may mention. Returns None if the walk does not exist."""
    walk = store.get_walk(walk_id)
    if not walk:
        return None
    start = _parse(walk["started_at"])
    end = _parse(walk.get("ended_at") or store.last_track_ts(walk_id) or walk["started_at"])
    minutes = max(0, round((end - start).total_seconds() / 60))
    distance = stats.track_distance_m([tuple(p) for p in walk["track"]])

    spotted, challenges, other = [], [], []
    for s in walk["sightings"]:
        if s["kind"] == "challenge":
            prompt = (s.get("transcript") or "").removeprefix("challenge: ")
            challenges.append({"answer": s["subject"], "prompt": prompt})
        elif s["kind"] in SPECIES_KINDS:
            spotted.append(s["subject"])
        else:
            other.append(s["subject"])
    return {
        "minutes": minutes,
        "distance_m": distance,
        "species": list(dict.fromkeys(spotted)),
        "new_species": store.new_species_for_walk(walk_id),
        "other": list(dict.fromkeys(other)),
        "challenges": challenges,
    }


def facts_to_context(f: dict) -> str:
    length = f"about {f['minutes']} minutes" if f["minutes"] >= 2 else "a short walk"
    if f["distance_m"] >= 100:
        length += f", {f['distance_m'] / 1000:.1f} kilometres"
    lines = [f"Walk length: {length}."]
    if f["species"]:
        lines.append("Birds, plants and animals the walker logged: " + ", ".join(f["species"]) + ".")
    if f["new_species"]:
        lines.append("New for their life list on this walk: " + ", ".join(f["new_species"]) + ".")
    if f["other"]:
        lines.append("Other things they noted: " + ", ".join(f["other"]) + ".")
    for c in f["challenges"]:
        lines.append(f'Challenge "{c["prompt"]}" - the walker answered: "{c["answer"]}".')
    if len(lines) == 1:
        lines.append("Nothing else was logged on this walk.")
    return "\n".join(lines)


def audio_path(walk_id: int) -> Path | None:
    for ext in ("mp3", "wav"):
        p = AUDIO_DIR / f"{walk_id}.{ext}"
        if p.exists():
            return p
    return None


def _clean(text: str) -> str:
    return text.replace("*", "").replace("#", "").strip()


async def ensure_postcard(store: Store, walk_id: int, regenerate: bool = False) -> dict:
    """Return the postcard text (and whether audio exists), writing it first if needed."""
    existing = store.get_postcard(walk_id)
    if existing and not regenerate:
        return {"text": existing, "audio": audio_path(walk_id) is not None}

    facts = walk_facts(store, walk_id)
    if facts is None:
        raise KeyError(walk_id)
    messages = [
        {"role": "system", "content": POSTCARD_SYSTEM},
        {"role": "user", "content": f"FACTS:\n{facts_to_context(facts)}\n\nWrite the postcard."},
    ]
    text = _clean("".join([tok async for tok in llm.chat_stream(messages, temperature=0.7)]))
    if not text:
        raise RuntimeError("the model returned an empty postcard")
    store.set_postcard(walk_id, text)

    # voice is a bonus: if it fails, the text postcard still stands
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for old in AUDIO_DIR.glob(f"{walk_id}.*"):
        old.unlink()
    has_audio = False
    try:
        audio, mime = await tts.synthesize(text)
        (AUDIO_DIR / f"{walk_id}.{'mp3' if mime == 'audio/mpeg' else 'wav'}").write_bytes(audio)
        has_audio = True
    except Exception as exc:
        print(f"[postcard] voice failed, text only: {exc!r}")
    return {"text": text, "audio": has_audio}