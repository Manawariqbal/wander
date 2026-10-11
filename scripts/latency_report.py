"""Summarise per-turn latency for the write-up.

    python -m scripts.latency_report
Reads data/metrics.jsonl (written by the server on every spoken reply).
"""
import json
import statistics
from pathlib import Path

PATH = Path("data/metrics.jsonl")


def pct(values: list[float], p: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p * (len(values) - 1))))]


def main() -> None:
    if not PATH.exists():
        print("No data/metrics.jsonl yet: talk to the app first.")
        return
    rows = [json.loads(line) for line in PATH.read_text().splitlines() if line.strip()]
    print(f"{len(rows)} turns recorded\n")
    for key, label in (("stt_s", "speech-to-text"), ("first_audio_s", "first audio (you stop talking -> hear reply)"),
                       ("total_s", "whole reply")):
        vals = [r[key] for r in rows if key in r]
        if vals:
            print(f"{label:48} median {statistics.median(vals):5.2f}s   p90 {pct(vals, 0.9):5.2f}s")


if __name__ == "__main__":
    main()