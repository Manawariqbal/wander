"""Postcard tests: the LLM and the voice are mocked, the database is real."""
import asyncio
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from server import postcard
from server.db.store import Store


def _store():
    return Store(tempfile.mkdtemp() + "/t.db")


def _walk_with_data(store):
    wid = store.start_walk(18.0, 73.0)
    for lat in (18.0, 18.001, 18.002):
        store.add_track(wid, lat, 73.0)
    store.add_sighting(wid, 18.001, 73.0, "bird", "kingfisher", "I saw a kingfisher")
    store.add_sighting(wid, 18.002, 73.0, "challenge", "a red flower", "challenge: Find a flower.")
    return wid


async def _fake_stream(_messages, temperature=0.6):
    for tok in ["You walked ", "past the water."]:
        yield tok


def test_facts_include_new_species_and_challenges():
    store = _store()
    wid = _walk_with_data(store)
    facts = postcard.walk_facts(store, wid)
    assert facts["species"] == ["kingfisher"] and facts["new_species"] == ["kingfisher"]
    assert facts["challenges"] == [{"answer": "a red flower", "prompt": "Find a flower."}]
    ctx = postcard.facts_to_context(facts)
    assert "kingfisher" in ctx and "a red flower" in ctx


def test_species_is_not_new_on_a_second_walk():
    store = _store()
    _walk_with_data(store)
    second = store.start_walk(18.0, 73.0)
    store.add_sighting(second, 18.0, 73.0, "bird", "kingfisher", "again")
    assert postcard.walk_facts(store, second)["new_species"] == []


def test_ensure_postcard_saves_text_audio_and_caches():
    store = _store()
    wid = _walk_with_data(store)
    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(postcard, "AUDIO_DIR", Path(tmp)), \
         patch.object(postcard.llm, "chat_stream", _fake_stream), \
         patch.object(postcard.tts, "synthesize", AsyncMock(return_value=(b"abc", "audio/mpeg"))) as tts:
        first = asyncio.run(postcard.ensure_postcard(store, wid))
        assert first == {"text": "You walked past the water.", "audio": True}
        assert (Path(tmp) / f"{wid}.mp3").read_bytes() == b"abc"
        again = asyncio.run(postcard.ensure_postcard(store, wid))
        assert again["text"] == first["text"] and tts.await_count == 1  # served from cache


def test_voice_failure_keeps_the_text():
    store = _store()
    wid = _walk_with_data(store)
    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(postcard, "AUDIO_DIR", Path(tmp)), \
         patch.object(postcard.llm, "chat_stream", _fake_stream), \
         patch.object(postcard.tts, "synthesize", AsyncMock(side_effect=RuntimeError("no voice"))):
        out = asyncio.run(postcard.ensure_postcard(store, wid))
    assert out["text"] and out["audio"] is False and store.get_postcard(wid)


def test_old_database_gets_the_postcard_column():
    path = tempfile.mkdtemp() + "/old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE walks (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, ended_at TEXT, "
                "start_lat REAL, start_lon REAL, route_json TEXT, summary TEXT)")
    con.commit()
    con.close()
    store = Store(path)  # must migrate, not crash
    wid = store.start_walk(1.0, 2.0)
    store.set_postcard(wid, "hello")
    assert store.get_postcard(wid) == "hello"


def test_life_list_orders_by_first_seen():
    store = _store()
    wid = store.start_walk(0, 0)
    store.add_sighting(wid, 0, 0, "bird", "kingfisher", "x")
    store.add_sighting(wid, 0, 0, "plant", "peepal", "x")
    store.add_sighting(wid, 0, 0, "bird", "kingfisher", "x")
    ll = store.life_list()
    assert [r["subject"] for r in ll] == ["kingfisher", "peepal"] and ll[0]["times"] == 2