"""OPTIONAL grounded explanations (off by default). Uses a free-tier LLM only if GEMINI_API_KEY is set.
Prompt forces: use ONLY the supplied facts; separate FACTS / POSSIBLE CONSEQUENCES / ANALYSIS; say 'unknown' when unsure."""
from __future__ import annotations

import json
import logging

from .config import env

log = logging.getLogger("mb.explain")

PROMPT = """You explain news to a general reader. Use ONLY the facts below. Do not add names, numbers, quotes or events that are not in them.
If something is unknown, say it is unknown. Political statements must be attributed ("X said"), never presented as fact.
Return strict JSON with keys: "simple" (3-4 plain sentences, no jargon), "possible_consequences" (list of up to 3 cautious 'could/might' statements clearly hypothetical), "analysis" (2-3 sentences of context, labelled as analysis, neutral tone).

HEADLINE: {headline}
FACTS (each attributed to its source):
{facts}
STILL UNKNOWN:
{unknown}
"""


def explain_story(story: dict, language: str = "en") -> dict | None:
    key = env("GEMINI_API_KEY")
    if not key:
        return None
    import requests
    facts = "\n".join(f"- ({k['source']}) {k['text']}" for k in story["know"])
    unknown = "\n".join(f"- {u}" for u in story["unknown"])
    prompt = PROMPT.format(headline=story["headline"], facts=facts, unknown=unknown)
    if language != "en":
        prompt += f"\nWrite the JSON values in language code '{language}'."
    model = env("GEMINI_MODEL", "gemini-2.0-flash")
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          headers={"x-goog-api-key": key}, timeout=40,
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}})
        r.raise_for_status()
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        d = json.loads(txt)
        if not isinstance(d.get("simple"), str):
            return None
        return {"simple": d["simple"], "possible_consequences": [str(x) for x in d.get("possible_consequences", [])][:3],
                "analysis": str(d.get("analysis", "")), "generated_by": "llm", "grounded_on": "source excerpts only"}
    except Exception as e:  # noqa: BLE001  optional feature must never break the brief
        log.warning("explain failed: %s", e)
        return None
