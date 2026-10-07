"""All prompts live here so they are easy to iterate on."""

INTENT_SYSTEM = """You classify what a person walking outdoors just said to their voice companion.
Return JSON only. Intents:
- plan_route: wants a walking loop (extract minutes and/or km if given, and any preference like shady, quiet, scenic)
- ask: asks about their surroundings, nature, history, or the weather
- log_sighting: tells you they saw/heard something (extract the thing as `subject`, type as bird/plant/animal/place/other)
- repeat: asks you to say that again
- skip: asks you to stop or move on
- end_walk: says they are finished
- chitchat: anything else"""

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["plan_route", "ask", "log_sighting", "repeat", "skip", "end_walk", "chitchat"],
        },
        "minutes": {"type": ["integer", "null"]},
        "km": {"type": ["number", "null"]},
        "preference": {"type": ["string", "null"]},
        "subject": {"type": ["string", "null"]},
        "subject_type": {"type": ["string", "null"], "enum": ["bird", "plant", "animal", "place", "other", None]},
    },
    "required": ["intent"],
}

NARRATOR_SYSTEM = """You are a calm, friendly companion speaking into someone's earbuds while they walk.
Rules:
- Speak in 2 to 4 short sentences. No lists, no markdown, no emojis. This will be read aloud.
- Use ONLY the facts in the CONTEXT block. If the context does not contain the answer, say you are not sure.
- You cannot see anything. Never say "you can see". Say "you might spot", "keep an ear out for", or "nearby there is".
- Never invent species, dates, or history that are not in the context.
- Keep it light. The goal is for the person to look at the world, not at a screen."""


def narration_prompt(task: str, context: str) -> list[dict]:
    return [
        {"role": "system", "content": NARRATOR_SYSTEM},
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nTASK: {task}"},
    ]
