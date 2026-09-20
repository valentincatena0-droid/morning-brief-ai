"""Breaking-news detection with explicit priority levels and interruption rules.

NORMAL     score < 48                      -> only appears in search/pool
IMPORTANT  score >= 48                     -> can enter the daily brief; no push
URGENT     score >= 66, confirmed/likely, newest report <= 12h   -> push only if URGENT is enabled in settings
BREAKING   score >= 80, confirmed/likely, newest <= 3h, >=3 independent owners (or primary + 2), high impact
           -> push (max alerts/day, quiet hours respected except BREAKING)
Alerts are de-duplicated against earlier alerts and today's brief by headline similarity.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .brief import analyse, build_story
from .textutil import norm_tokens


def _sim(a: str, b: str) -> float:
    A, B = set(norm_tokens(a)), set(norm_tokens(b))
    return len(A & B) / len(A | B) if A | B else 0


def in_quiet_hours(now: datetime, settings: dict) -> bool:
    q = settings.get("alerts", {}).get("quiet_hours")
    if not q:
        return False
    local = now.astimezone(ZoneInfo(settings["brief"]["timezone"])).strftime("%H:%M")
    s, e = q["start"], q["end"]
    return (local >= s or local < e) if s > e else (s <= local < e)


def find_alerts(items, sources, settings, now, prior_alerts: list[dict], todays_brief: dict | None) -> list[dict]:
    cfg = settings.get("alerts", {})
    if not cfg.get("enabled", True):
        return []
    levels = set(cfg.get("notify_levels", ["BREAKING"]))
    today = now.astimezone(ZoneInfo(settings["brief"]["timezone"])).strftime("%Y-%m-%d")
    sent_today = [a for a in prior_alerts if a.get("day") == today]
    room = cfg.get("max_per_day", 3) - len(sent_today)
    if room <= 0:
        return []
    known = [a["headline"] for a in prior_alerts[:40]]
    if todays_brief:
        known += [s["headline"] for s in todays_brief["stories"] if s["priority"] in levels]
    out = []
    quiet = in_quiet_hours(now, settings)
    cands = [s for s in analyse(items, sources, now, settings.get("local_keywords")) if s["rank"]["priority"] in levels]
    for s in sorted(cands, key=lambda s: -s["rank"]["score"]):
        if quiet and s["rank"]["priority"] != "BREAKING":
            continue
        story = build_story(s["cluster"], s["_ver"], s["rank"], sources)
        if any(_sim(story["headline"], k) >= 0.5 for k in known):
            continue
        story["day"] = today
        story["alerted_at"] = now.isoformat()
        out.append(story)
        known.append(story["headline"])
        if len(out) >= room:
            break
    return out
