"""Niche editions: focused lists (e.g. personal finance, family health & safety) drawn from the already-verified stories.

Nothing new is written: a niche only SELECTS among analysed clusters by keyword match on the original text, with a small
bonus when an official (primary) source is involved. Verification labels and sources are carried through unchanged."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "niches.yaml"


def load_niches(path: Path | None = None) -> list[dict]:
    p = path or DEFAULT
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for n in data.get("niches", []):
        try:
            n["_rx"] = re.compile(n["keywords"], re.I)
        except (re.error, KeyError):
            continue
        out.append(n)
    return out


def _text(s: dict) -> str:
    return " ".join(it["title"] + ". " + it.get("summary", "") for it in s["cluster"])


def _matches(s: dict, rx) -> bool:
    """A keyword in any HEADLINE, or at least two different keywords in the body text (one stray word is not a topic)."""
    if any(rx.search(it["title"]) for it in s["cluster"]):
        return True
    return len({m.group(0).lower() for m in rx.finditer(_text(s))}) >= 2


def pick(analysed: list[dict], niche: dict) -> list[dict]:
    from .rank import _dup, _sig
    rx, lim = niche["_rx"], int(niche.get("limit", 6))
    scored = []
    for s in analysed:
        if s["rank"]["category"] in ("sports", "culture") or s["_ver"].status == "UNVERIFIED":
            continue
        if not _matches(s, rx):
            continue
        sc = s["rank"]["score"] + (niche.get("official_bonus", 0) if s["_ver"].has_primary else 0)
        if sc >= niche.get("min_score", 15):
            scored.append((sc, s))
    scored.sort(key=lambda x: -x[0])
    out, sigs = [], []
    for _, s in scored:                       # drop a second telling of the same event (e.g. official bulletin + news write-up)
        sg = _sig(s)
        if any(_dup(sg, g) for g in sigs):
            continue
        out.append(s); sigs.append(sg)
        if len(out) >= lim:
            break
    return out
