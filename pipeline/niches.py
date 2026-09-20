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
            n["_ex"] = re.compile(n["exclude"], re.I) if n.get("exclude") else None
        except (re.error, KeyError):
            continue
        out.append(n)
    return out


def _text(s: dict) -> str:
    return " ".join(it["title"] + ". " + it.get("summary", "") for it in s["cluster"])


def _matches(s: dict, niche: dict) -> bool:
    """The topic must be in a HEADLINE (body-only matches pull in unrelated politics/war stories that mention prices or banks
    in passing); shopping deals and animal-only stories never qualify."""
    from .rank import ANIMAL, HUMAN
    titles = [it["title"] for it in s["cluster"]]
    if not any(niche["_rx"].search(t) for t in titles):
        return False
    ex = niche.get("_ex")
    if ex and any(ex.search(t) for t in titles):
        return False
    text = _text(s)
    return not (ANIMAL.search(text) and not HUMAN.search(text))


def pick(analysed: list[dict], niche: dict) -> list[dict]:
    from .rank import _dup, _sig
    lim = int(niche.get("limit", 6))
    scored = []
    for s in analysed:
        if s["rank"]["category"] in ("sports", "culture") or s["_ver"].status == "UNVERIFIED":
            continue
        if not _matches(s, niche):
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
