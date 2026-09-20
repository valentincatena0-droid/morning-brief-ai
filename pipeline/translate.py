"""OPTIONAL translation of the brief text (off by default; needs GEMINI_API_KEY and llm.translate: true).

Only text is translated (source names and URLs are never sent). The model is told to keep names, numbers and dates
unchanged, and the original text is kept in `original` so nothing is lost. If the model output does not have the exact shape we sent, that story is
left in its original language rather than shipping something malformed."""
from __future__ import annotations

import json
import logging

from .config import env

log = logging.getLogger("mb.translate")

PROMPT = """Translate the JSON values below into {language_name}. Rules: translate faithfully, add nothing, remove nothing.
Keep names of people, organisations, places, numbers, dates and quoted statements exactly as they are. Do not add opinions.
Attributed statements ("X said") must stay attributed. Return strict JSON with EXACTLY the same keys and list lengths.

{payload}
"""
LANG_NAMES = {"es": "Spanish", "pt": "Portuguese", "fr": "French", "de": "German"}


def _payload(st: dict) -> dict:
    return {"headline": st["headline"], "summary": st["summary"], "why_it_matters": st["why_it_matters"],
            "know": [k["text"] for k in st["know"]], "unknown": list(st["unknown"])}


def _valid(src: dict, out) -> bool:
    return (isinstance(out, dict) and all(isinstance(out.get(k), str) and out[k].strip() for k in ("headline", "summary", "why_it_matters"))
            and isinstance(out.get("know"), list) and len(out["know"]) == len(src["know"]) and all(isinstance(x, str) for x in out["know"])
            and isinstance(out.get("unknown"), list) and len(out["unknown"]) == len(src["unknown"]) and all(isinstance(x, str) for x in out["unknown"]))


def _call(prompt: str, key: str) -> dict | None:
    import requests
    model = env("GEMINI_MODEL", "gemini-flash-lite-latest")
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": key}, timeout=60,
                      json={"contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}})
    r.raise_for_status()
    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def translate_story(st: dict, language: str, call=_call) -> bool:
    key = env("GEMINI_API_KEY")
    if not key or language == "en":
        return False
    src = _payload(st)
    prompt = PROMPT.format(language_name=LANG_NAMES.get(language, language),
                           payload=json.dumps(src, ensure_ascii=False, indent=1))
    try:
        out = call(prompt, key)
    except Exception as e:  # noqa: BLE001  optional feature must never break the brief
        log.warning("translate failed: %s", e)
        return False
    if not _valid(src, out):
        log.warning("translate: unexpected shape for %s; keeping original", st.get("id"))
        return False
    st["original"] = {"language": "en", **src}
    st["headline"], st["summary"], st["why_it_matters"] = out["headline"], out["summary"], out["why_it_matters"]
    for k, t in zip(st["know"], out["know"]):
        k["text"] = t
    st["unknown"] = out["unknown"]
    st["language"] = language
    return True


def translate_brief(brief: dict, language: str, call=_call) -> int:
    allst = brief["stories"] + brief.get("pool", [])
    n = sum(translate_story(st, language, call) for st in allst)
    if n:
        by_id = {s["id"]: s for s in allst}
        for rows in brief.get("sections", {}).values():
            for r in rows:
                if r.get("id") in by_id:
                    r["headline"] = by_id[r["id"]]["headline"]
        b = brief.get("biggest_story")
        if b and b.get("story_id") in by_id:
            b["headline"], b["description"] = by_id[b["story_id"]]["headline"], by_id[b["story_id"]]["summary"]
        brief["language"] = language
    return n
