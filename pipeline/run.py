"""CLI entry point.

  python -m pipeline.run tick                # what the scheduler runs every 30 min
  python -m pipeline.run tick --force        # build today's brief now regardless of the clock
  python -m pipeline.run tick --now 2026-09-20T11:00:00Z --fixtures tests/fixtures --out /tmp/x --dry-run
  python -m pipeline.run text                # print latest brief as text
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import alerts as alerts_mod
from . import notify, storage
from .brief import compose, render_text
from .config import DEFAULT_DOCS, load_settings, load_sources
from .explain import explain_story
from .translate import translate_brief
from .publish import build_kit, load_cfg as load_dist_cfg
from .telegram import post_editions
from .fetch import fetch_all
from .schedule import should_run

log = logging.getLogger("mb")


def tick(now: datetime, docs: Path, settings: dict, sources: dict, force=False, fixtures: Path | None = None,
         dry_run=False) -> dict:
    result = {"now": now.isoformat(), "brief": None, "alerts": [], "notes": []}
    existing = storage.existing_dates(docs)
    due, reason = should_run(now, settings, existing)
    if force:
        due, reason = True, "forced"
        local_date = now.astimezone(__import__("zoneinfo").ZoneInfo(settings["brief"]["timezone"])).strftime("%Y-%m-%d")
    result["notes"].append(f"schedule: {reason}")
    alerts_on = settings.get("alerts", {}).get("enabled", True)
    if not due and not alerts_on:
        return result

    items, health = fetch_all(sources, now, fixtures=fixtures)
    if due:  # only write when a brief is built, so 30-min alert-only ticks create no git noise
        storage.save_health(docs, health, "fetch health at brief time")
    if not items:
        result["notes"].append("WARNING: no items fetched from any source; nothing published")
        return result

    if due:
        brief = compose(items, sources, settings, now, health)
        if settings.get("llm", {}).get("enabled"):
            if settings["llm"].get("translate"):
                translate_brief(brief, settings["llm"].get("language", "en"))
            for st in brief["stories"]:
                ex = explain_story(st, settings["llm"].get("language", "en"))
                if ex:
                    st["explain"] = ex
        if not brief["stories"]:
            result["notes"].append("WARNING: no story met quality bar; brief not published")
        else:
            storage.write_brief(docs, brief)
            try:
                build_kit(brief, docs)      # free distribution kit; failure must never block the brief
                result["telegram"] = post_editions(brief, docs, load_dist_cfg(), settings, dry_run=dry_run or bool(fixtures))
            except Exception as exc:  # noqa: BLE001
                result["notes"].append(f"distribution kit skipped: {exc}")
            result["brief"] = {"date": brief["date"], "stories": len(brief["stories"]), "warnings": brief["warnings"]}
            result["brief_notification"] = notify.notify_brief(settings, brief, dry_run=dry_run)
            result["text"] = render_text(brief)

    prior = storage.load_alerts(docs)
    today_brief = storage.load_brief(docs, now.astimezone(__import__("zoneinfo").ZoneInfo(settings["brief"]["timezone"])).strftime("%Y-%m-%d"))
    new = alerts_mod.find_alerts(items, sources, settings, now, prior, today_brief)
    for st in new:
        res = notify.notify_alert(settings, st, dry_run=dry_run)
        result["alerts"].append({"headline": st["headline"], "priority": st["priority"], "notification": res})
    if new:
        storage.save_alerts(docs, new + prior)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="morning-brief")
    ap.add_argument("cmd", choices=["tick", "text", "reindex"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="never send push notifications")
    ap.add_argument("--now", help="ISO time (UTC) to simulate, e.g. 2026-09-20T11:00:00Z")
    ap.add_argument("--fixtures", type=Path, help="read feeds from local XML fixtures instead of the network")
    ap.add_argument("--out", type=Path, default=DEFAULT_DOCS, help="docs directory to write to")
    ap.add_argument("--settings", type=Path)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings, sources = load_settings(a.settings), load_sources()
    if a.cmd == "reindex":
        storage.rebuild_indexes(a.out)
        return 0
    if a.cmd == "text":
        b = json.loads((a.out / "data" / "latest.json").read_text(encoding="utf-8"))
        print(render_text(b))
        return 0
    now = datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now else datetime.now(timezone.utc)
    res = tick(now, a.out, settings, sources, force=a.force, fixtures=a.fixtures, dry_run=a.dry_run)
    text = res.pop("text", None)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if text and a.verbose:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
