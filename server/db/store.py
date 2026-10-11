"""SQLite persistence for walks, sightings and GPS track."""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SPECIES_KINDS = ("bird", "plant", "animal")
_ARTICLES = re.compile(r"^(a|an|the|some)\s+", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_subject(subject: str) -> str:
    """'A Kingfisher.' -> 'kingfisher', so the life list matches repeats."""
    s = subject.strip().rstrip(".!?").strip().lower()
    return _ARTICLES.sub("", s) or s


class Store:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript((Path(__file__).parent / "schema.sql").read_text())
        self.conn.commit()

    def start_walk(self, lat: float, lon: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO walks(started_at, start_lat, start_lon) VALUES (?,?,?)", (_now(), lat, lon)
        )
        self.conn.commit()
        return cur.lastrowid

    def add_track(self, walk_id: int, lat: float, lon: float) -> None:
        self.conn.execute("INSERT INTO track(walk_id, ts, lat, lon) VALUES (?,?,?,?)", (walk_id, _now(), lat, lon))
        self.conn.commit()

    def track_points(self, walk_id: int) -> list[tuple[float, float]]:
        rows = self.conn.execute("SELECT lat, lon FROM track WHERE walk_id=? ORDER BY id", (walk_id,)).fetchall()
        return [(r["lat"], r["lon"]) for r in rows]

    def add_sighting(self, walk_id: int, lat, lon, kind: str | None, subject: str, transcript: str) -> None:
        self.conn.execute(
            "INSERT INTO sightings(walk_id, ts, lat, lon, kind, subject, transcript) VALUES (?,?,?,?,?,?,?)",
            (walk_id, _now(), lat, lon, kind, subject, transcript),
        )
        self.conn.commit()

    def times_seen(self, subject: str) -> int:
        """How many times this (normalized) subject was logged, across all walks."""
        row = self.conn.execute("SELECT COUNT(*) AS n FROM sightings WHERE subject=?", (subject,)).fetchone()
        return row["n"]

    def species_count(self) -> int:
        """Distinct birds/plants/animals ever logged (the 'life list')."""
        marks = ",".join("?" * len(SPECIES_KINDS))
        row = self.conn.execute(
            f"SELECT COUNT(DISTINCT subject) AS n FROM sightings WHERE kind IN ({marks})", SPECIES_KINDS
        ).fetchone()
        return row["n"]

    def set_route(self, walk_id: int, route: dict) -> None:
        self.conn.execute("UPDATE walks SET route_json=? WHERE id=?", (json.dumps(route), walk_id))
        self.conn.commit()

    def end_walk(self, walk_id: int, summary: str) -> None:
        self.conn.execute("UPDATE walks SET ended_at=?, summary=? WHERE id=?", (_now(), summary, walk_id))
        self.conn.commit()

    def sightings(self, walk_id: int) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM sightings WHERE walk_id=? ORDER BY ts", (walk_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_walks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, started_at, ended_at, summary FROM walks ORDER BY id DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_walk(self, walk_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM walks WHERE id=?", (walk_id,)).fetchone()
        if not row:
            return None
        walk = dict(row)
        walk["route"] = json.loads(walk.pop("route_json")) if walk.get("route_json") else None
        walk["sightings"] = self.sightings(walk_id)
        walk["track"] = [
            [r["lat"], r["lon"]]
            for r in self.conn.execute("SELECT lat, lon FROM track WHERE walk_id=? ORDER BY id", (walk_id,))
        ]
        return walk