"""Measure intent-classification accuracy for the write-up.

    python -m scripts.eval_intents
Needs Ollama running with the Gemma model pulled. Add more rows to CASES.
"""
import asyncio
import time

from server.agent import llm, prompts

CASES = [
    ("I've got forty five minutes, somewhere shady please", "plan_route"),
    ("plan me a two kilometer loop", "plan_route"),
    ("can you find a quiet route around the lake", "plan_route"),
    ("what birds should I hear around here", "ask"),
    ("what's the history of this place", "ask"),
    ("is it going to rain", "ask"),
    ("I just saw a kingfisher", "log_sighting"),
    ("there's a peepal tree right here, log it", "log_sighting"),
    ("I heard a koel", "log_sighting"),
    ("say that again", "repeat"),
    ("repeat that please", "repeat"),
    ("okay stop talking", "skip"),
    ("skip that", "skip"),
    ("I'm done for today", "end_walk"),
    ("let's finish the walk", "end_walk"),
    ("this is a nice day", "chitchat"),
]


async def main() -> None:
    correct, times = 0, []
    for text, want in CASES:
        t0 = time.perf_counter()
        got = (await llm.chat_json(
            [{"role": "system", "content": prompts.INTENT_SYSTEM}, {"role": "user", "content": text}],
            prompts.INTENT_SCHEMA,
        ))["intent"]
        times.append(time.perf_counter() - t0)
        ok = got == want
        correct += ok
        print(f"{'OK ' if ok else 'BAD'} {want:13} got {got:13} | {text}")
    times.sort()
    print(f"\naccuracy: {correct}/{len(CASES)} = {correct / len(CASES):.0%}")
    print(f"median intent latency: {times[len(times) // 2]:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
