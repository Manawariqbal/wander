import asyncio

from server.agent.llm import sentences


async def _tokens(parts):
    for p in parts:
        yield p


def _run(parts):
    async def go():
        return [s async for s in sentences(_tokens(parts))]
    return asyncio.run(go())


def test_splits_on_sentence_boundaries():
    out = _run(["Hello the", "re. How are", " you? Fine", "."])
    assert out == ["Hello there.", "How are you?", "Fine."]


def test_flushes_trailing_fragment():
    assert _run(["No end punctuation"]) == ["No end punctuation"]
