"""Thin Ollama client for Gemma: streaming chat + JSON-schema-constrained calls."""
import json
import re
from typing import AsyncIterator

import httpx

from server import config

_SENT_END = re.compile(r"(?<=[.!?])\s+")


async def chat_stream(messages: list[dict], temperature: float = 0.6) -> AsyncIterator[str]:
    """Yield text tokens as Gemma generates them."""
    payload = {
        "model": config.GEMMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                tok = data.get("message", {}).get("content", "")
                if tok:
                    yield tok
                if data.get("done"):
                    break


async def chat_json(messages: list[dict], schema: dict) -> dict:
    """One-shot call constrained to a JSON schema (Ollama `format` field)."""
    payload = {
        "model": config.GEMMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{config.OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


async def sentences(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Group a token stream into whole sentences so TTS can start early."""
    buf = ""
    async for tok in token_stream:
        buf += tok
        parts = _SENT_END.split(buf)
        # everything except the last fragment is a complete sentence
        for s in parts[:-1]:
            s = s.strip()
            if s:
                yield s
        buf = parts[-1]
    if buf.strip():
        yield buf.strip()
