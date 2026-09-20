"""Push notifications via ntfy (free, native iOS/Android apps). JSON publish API => UTF-8 safe.
The topic is a secret (env NTFY_TOPIC). Notification dry-run returns the payload without sending."""
from __future__ import annotations

import logging

from .config import env

log = logging.getLogger("mb.notify")


def _app_link(settings: dict, fragment: str = "") -> str:
    base = env("APP_URL") or settings.get("notify", {}).get("app_url", "")
    return (base.rstrip("/") + "/" + fragment) if base else ""


def send(settings: dict, title: str, message: str, fragment: str = "", priority: int = 3, tags=None, dry_run: bool = False) -> dict:
    n = settings.get("notify", {})
    payload = {"topic": env("NTFY_TOPIC") or "<NTFY_TOPIC not set>", "title": title, "message": message,
               "priority": priority, "tags": tags or []}
    click = _app_link(settings, fragment)
    if click:
        payload["click"] = click
    if dry_run or n.get("provider", "ntfy") == "none":
        return {"sent": False, "reason": "dry-run" if dry_run else "provider none", "payload": {**payload, "topic": "***"}}
    if not env("NTFY_TOPIC"):
        log.warning("NTFY_TOPIC not set; skipping push")
        return {"sent": False, "reason": "NTFY_TOPIC missing", "payload": {**payload, "topic": "***"}}
    import requests
    headers = {"Content-Type": "application/json"}
    if env("NTFY_TOKEN"):
        headers["Authorization"] = "Bearer " + env("NTFY_TOKEN")
    try:
        r = requests.post(n.get("server", "https://ntfy.sh"), json=payload, headers=headers, timeout=15)
        ok = r.status_code < 300
        return {"sent": ok, "status": r.status_code, "payload": {**payload, "topic": "***"}}
    except Exception as e:  # noqa: BLE001  a failed push must never fail the pipeline
        log.error("ntfy failed: %s", e)
        return {"sent": False, "reason": str(e)[:120], "payload": {**payload, "topic": "***"}}


def notify_brief(settings: dict, brief: dict, dry_run=False) -> dict:
    top = brief["stories"][:3]
    msg = f"{len(brief['stories'])} things you should know today."
    if top:
        msg += "\n" + "\n".join(f"{s['position']}. {s['headline']}" for s in top)
    return send(settings, "☀️ MORNING BRIEF READY", msg, "#/today", priority=3, tags=["sunny"], dry_run=dry_run)


def notify_alert(settings: dict, story: dict, dry_run=False) -> dict:
    srcs = " · ".join(s["name"] for s in story["sources"][:3])
    title = ("🚨 BREAKING NEWS" if story["priority"] == "BREAKING" else "🚨 IMPORTANT UPDATE")
    msg = f"{story['headline']}\n{story['summary'][:220]}\n{srcs}"
    return send(settings, title, msg, f"#/story/{story['id']}", priority=5 if story["priority"] == "BREAKING" else 4,
                tags=["rotating_light"], dry_run=dry_run)
