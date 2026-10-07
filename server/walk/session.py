"""Per-connection walk state."""
from dataclasses import dataclass, field


@dataclass
class Session:
    walk_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    pois: list[dict] = field(default_factory=list)
    species: dict = field(default_factory=dict)
    weather: dict = field(default_factory=dict)
    narrated: set[str] = field(default_factory=set)
    last_narration_ts: float = 0.0
    last_spoken: list[str] = field(default_factory=list)
    route: dict | None = None
    next_step: int = 0
    prefetched: bool = False
    prefetching: bool = False
    ended: bool = False
