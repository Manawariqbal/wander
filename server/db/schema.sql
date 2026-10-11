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

-- Grid-cell cache so a walk can run mostly offline (except TTS)
CREATE TABLE IF NOT EXISTS poi_cache (
  cell TEXT PRIMARY KEY,          -- e.g. "18.52_73.85"  (~1 km grid)
  pois_json TEXT NOT NULL,        -- list of place dicts
  species_json TEXT NOT NULL,     -- {"birds": [...], "plants": [...]}
  weather_json TEXT,              -- optional, expires faster
  sun_json TEXT,
  fetched_at TEXT NOT NULL
);