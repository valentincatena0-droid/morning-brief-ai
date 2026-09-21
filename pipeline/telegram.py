"""Optional, free: post the daily niche edition to your own Telegram channel through a bot YOU create (BotFather).

Needs two secrets in GitHub Actions: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (e.g. @yourchannel). Without them this is a no-op.
It only ever posts text the pipeline already built (publish.render_text), at most once per niche per brief date."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import env
from .publish import niche_stories, render_text

log = logging.getLogger("mb.telegram")
LIMIT = 4000          # Telegram hard limit is 4096 characters per message
STATE = "telegram_posted.json"


def _state(docs: Path) -> dict:
    try:
        return json.loads((docs / "data" / STATE).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(docs: Path, st: dict) -> None:
    p = docs / "data" / STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = dict(sorted(st.items())[-14:])              # last two weeks are enough
    p.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")


def fit(text: str) -> str:
    """Trim whole trailing items (never mid-sentence) until the message fits Telegram's limit."""
    if len(text) <= LIMIT:
        return text
    head, *items = text.split("\n\n")
    foot = items.pop() if items and items[-1].startswith("Información") else ""
    while items and len("\n\n".join([head, *items, foot])) > LIMIT:
        items.pop()
    return "\n\n".join([head, *items, foot]).strip() + "\n"


def _post(token: str, chat_id: str, text: str) -> dict:
    import requests
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True}, timeout=20)
    return {"ok": r.status_code < 300, "status": r.status_code}


def post_editions(brief: dict, docs: Path, cfg: dict, settings: dict | None = None, dry_run=False, poster=_post) -> list[dict]:
    tg = (cfg or {}).get("telegram", {})
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID") or tg.get("chat_id", "")
    if not tg.get("enabled") or not token or not chat:
        return []
    state = _state(docs)
    done = set(state.get(brief["date"], []))
    out = []
    for niche in brief.get("niches", []):
        if niche["id"] not in tg.get("niches", []) or niche["id"] in done:
            continue
        stories = niche_stories(brief, niche)[: int(tg.get("max_items", 5))]
        if not stories:
            continue
        text = fit(render_text(brief, niche, stories, cfg))
        if dry_run:
            out.append({"niche": niche["id"], "sent": False, "reason": "dry-run", "chars": len(text)})
            continue
        try:
            res = poster(token, chat, text)
        except Exception as e:  # noqa: BLE001   a failed post must never fail the pipeline
            log.error("telegram failed: %s", e)
            res = {"ok": False, "status": str(e)[:80]}
        out.append({"niche": niche["id"], "sent": res["ok"], "status": res.get("status")})
        if res["ok"]:
            done.add(niche["id"])
            state[brief["date"]] = sorted(done)
            _save(docs, state)
    return out
