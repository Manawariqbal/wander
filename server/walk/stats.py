"""Walk statistics from the GPS breadcrumb track."""
from server.walk.geofence import distance_m

MIN_STEP_M = 4      # ignore GPS jitter smaller than this
MAX_JUMP_M = 300    # ignore single-ping teleports
STEP_LENGTH_M = 0.75


def track_distance_m(points: list[tuple[float, float]]) -> float:
    total, prev = 0.0, None
    for lat, lon in points:
        if prev is None:
            prev = (lat, lon)
            continue
        d = distance_m(prev[0], prev[1], lat, lon)
        if d > MAX_JUMP_M:
            continue
        if d >= MIN_STEP_M:
            total += d
            prev = (lat, lon)
    return total


def stats_sentence(distance: float, elapsed_s: float) -> str:
    minutes = max(1, round(elapsed_s / 60))
    mins = f"{minutes} minute" + ("" if minutes == 1 else "s")
    if distance < 20:
        return f"You've only just started, about {mins} in so far."
    if distance < 100:
        far = f"about {round(distance / 10) * 10} metres"
    else:
        far = f"{distance / 1000:.1f} kilometres"
    sent = f"You've walked {far} in about {mins}"
    if distance >= 200:
        sent += f", roughly {round(distance / STEP_LENGTH_M / 10) * 10:,} steps"
    return sent + "."