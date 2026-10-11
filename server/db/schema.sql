CREATE TABLE IF NOT EXISTS walks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  start_lat REAL, start_lon REAL,
  route_json TEXT,
  summary TEXT,
  postcard TEXT
);
CREATE TABLE IF NOT EXISTS sightings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  walk_id INTEGER NOT NULL REFERENCES walks(id),
  ts TEXT NOT NULL,
  lat REAL, lon REAL,
  kind TEXT,
  subject TEXT,
  transcript TEXT
);
CREATE TABLE IF NOT EXISTS track (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  walk_id INTEGER NOT NULL REFERENCES walks(id),
  ts TEXT NOT NULL,
  lat REAL, lon REAL
);
-- TODO(poi_cache): cache prefetched POIs/species per ~1km grid cell for offline use