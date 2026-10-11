"""SQLite persistence for walks, sightings and GPS track."""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

SPECIES_KINDS = ("bird", "plant", "animal")
_ARTICLES = re.compile(r"^(a|an|the|some)\s+", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_subject(subject: str) -> str:
    """'A Kingfisher.' -> 'kingfisher', so the life list matches repeats."""
    s = subject.strip().rstrip(".!?").strip().lower()
    return _ARTICLES.sub("", s) or s


def _cell_key(lat: float, lon: float, precision: float = 0.01) -> str:
    """~1 km grid cell (0.01° ≈ 1.1 km)."""
    return f"{round(lat / precision) * precision:.2f}_{round(lon / precision) * precision:.2f}"


class Store:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript((Path(__file__).parent / "schema.sql").read_text())
        self.conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Add columns introduced after a database file was first created."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(walks)")}
        if "postcard" not in cols:
            self.conn.execute("ALTER TABLE walks ADD COLUMN postcard TEXT")
            self.conn.commit()

    def start_walk(self, lat: float, lon: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO walks(started_at, start_lat, start_lon) VALUES (?,?,?)", (_now(), lat, lon)
        )
        self.conn.commit()
        return cur.lastrowid

    def add_track(self, walk_id: int, lat: float, lon: float) -> None:
        self.conn.execute(
            "INSERT INTO track(walk_id, ts, lat, lon) VALUES (?,?,?,?)",
            (walk_id, _now(), lat, lon),
        )
        self.conn.commit()

    def track_points(self, walk_id: int) -> list[tuple[float, float]]:
        rows = self.conn.execute(
            "SELECT lat, lon FROM track WHERE walk_id=? ORDER BY id", (walk_id,)
        ).fetchall()
        return [(r["lat"], r["lon"]) for r in rows]

    def add_sighting(
        self, walk_id: int, lat, lon, kind: str | None, subject: str, transcript: str
    ) -> None:
        self.conn.execute(
            "INSERT INTO sightings(walk_id, ts, lat, lon, kind, subject, transcript) VALUES (?,?,?,?,?,?,?)",
            (walk_id, _now(), lat, lon, kind, subject, transcript),
        )
        self.conn.commit()

    def times_seen(self, subject: str) -> int:
        """How many times this (normalized) subject was logged, across all walks."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM sightings WHERE subject=?", (subject,)
        ).fetchone()
        return row["n"]

    def species_count(self) -> int:
        """Distinct birds/plants/animals ever logged (the 'life list')."""
        marks = ",".join("?" * len(SPECIES_KINDS))
        row = self.conn.execute(
            f"SELECT COUNT(DISTINCT subject) AS n FROM sightings WHERE kind IN ({marks})",
            SPECIES_KINDS,
        ).fetchone()
        return row["n"]

    def last_track_ts(self, walk_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT ts FROM track WHERE walk_id=? ORDER BY id DESC LIMIT 1", (walk_id,)
        ).fetchone()
        return row["ts"] if row else None

    def new_species_for_walk(self, walk_id: int) -> list[str]:
        """Species first logged on this walk (not seen on any earlier walk)."""
        marks = ",".join("?" * len(SPECIES_KINDS))
        rows = self.conn.execute(
            f"""SELECT DISTINCT s.subject FROM sightings s
                WHERE s.walk_id=? AND s.kind IN ({marks})
                  AND NOT EXISTS (
                      SELECT 1 FROM sightings o
                      WHERE o.subject=s.subject AND o.walk_id < s.walk_id
                  )""",
            (walk_id, *SPECIES_KINDS),
        ).fetchall()
        return [r["subject"] for r in rows]

    def life_list(self) -> list[dict]:
        """Every distinct bird/plant/animal ever logged, oldest first."""
        marks = ",".join("?" * len(SPECIES_KINDS))
        rows = self.conn.execute(
            f"""SELECT subject, MIN(kind) AS kind, COUNT(*) AS times, MIN(ts) AS first_seen
                FROM sightings WHERE kind IN ({marks})
                GROUP BY subject ORDER BY first_seen""",
            SPECIES_KINDS,
        ).fetchall()
        return [dict(r) for r in rows]

    def set_postcard(self, walk_id: int, text: str) -> None:
        self.conn.execute("UPDATE walks SET postcard=? WHERE id=?", (text, walk_id))
        self.conn.commit()

    def get_postcard(self, walk_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT postcard FROM walks WHERE id=?", (walk_id,)
        ).fetchone()
        return row["postcard"] if row and row["postcard"] else None

    def set_route(self, walk_id: int, route: dict) -> None:
        self.conn.execute(
            "UPDATE walks SET route_json=? WHERE id=?", (json.dumps(route), walk_id)
        )
        self.conn.commit()

    def end_walk(self, walk_id: int, summary: str) -> None:
        self.conn.execute(
            "UPDATE walks SET ended_at=?, summary=? WHERE id=?",
            (_now(), summary, walk_id),
        )
        self.conn.commit()

    def sightings(self, walk_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sightings WHERE walk_id=? ORDER BY ts", (walk_id,)
        ).fetchall()
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
            for r in self.conn.execute(
                "SELECT lat, lon FROM track WHERE walk_id=? ORDER BY id", (walk_id,)
            )
        ]
        return walk

    # ---------- poi_cache (offline place + species cache) ----------

    def get_poi_cache(self, lat: float, lon: float, max_age_hours: int = 24) -> dict | None:
        """Return cached data for the ~1 km grid cell, or None if missing/expired."""
        cell = _cell_key(lat, lon)
        row = self.conn.execute(
            "SELECT pois_json, species_json, weather_json, sun_json, fetched_at "
            "FROM poi_cache WHERE cell=?",
            (cell,),
        ).fetchone()
        if not row:
            return None

        fetched = datetime.fromisoformat(row["fetched_at"])
        if datetime.now(timezone.utc) - fetched > timedelta(hours=max_age_hours):
            return None

        return {
            "pois": json.loads(row["pois_json"]),
            "species": json.loads(row["species_json"]),
            "weather": json.loads(row["weather_json"]) if row["weather_json"] else {},
            "sun": json.loads(row["sun_json"]) if row["sun_json"] else {},
        }

    def set_poi_cache(self, lat: float, lon: float, data: dict) -> None:
        """Store prefetched data for the ~1 km grid cell."""
        cell = _cell_key(lat, lon)
        self.conn.execute(
            """INSERT OR REPLACE INTO poi_cache
               (cell, pois_json, species_json, weather_json, sun_json, fetched_at)
               VALUES (?,?,?,?,?,?)""",
            (
                cell,
                json.dumps(data.get("pois", [])),
                json.dumps(data.get("species", {})),
                json.dumps(data.get("weather", {})),
                json.dumps(data.get("sun", {})),
                _now(),
            ),
        )
        self.conn.commit()