"""Free distribution kit: turns the niche editions into files that are ready to send (newsletter, Telegram/WhatsApp, RSS).

It only re-formats what the pipeline already verified (headline, short summary, verification label, source names + links).
Nothing is invented, nothing is posted anywhere: it writes files under docs/data/out and docs/data/feeds. Cost: $0."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

import yaml

DEFAULT_CFG = Path(__file__).resolve().parent.parent / "config" / "distribution.yaml"
LABEL_ES = {"CONFIRMED": "Confirmado", "LIKELY": "Probable", "DEVELOPING": "En desarrollo", "UNVERIFIED": "Sin confirmar"}
SUM_MAX = 240


def load_cfg(path: Path | None = None) -> dict:
    p = path or DEFAULT_CFG
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    cfg = cfg or {}
    cfg.setdefault("site_url", "")
    cfg.setdefault("brand", "Morning Brief")
    cfg.setdefault("tagline", "")
    cfg.setdefault("channels", {})
    cfg.setdefault("disclaimer_es", "")
    return cfg


def _clip(s: str, n: int = SUM_MAX) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def _srcs(st: dict) -> str:
    return ", ".join(x["name"] for x in st.get("sources", [])[:3])


def _label(st: dict) -> str:
    return LABEL_ES.get(st.get("status", ""), st.get("status_label", ""))


def niche_stories(brief: dict, niche: dict) -> list[dict]:
    pool = {s["id"]: s for s in brief.get("stories", []) + brief.get("pool", [])}
    return [pool[i] for i in niche.get("story_ids", []) if i in pool]


def render_text(brief: dict, niche: dict, stories: list[dict], cfg: dict) -> str:
    """Plain text for Telegram / WhatsApp / SMS."""
    lines = [f"{cfg['brand']} · {niche['name']} · {brief.get('date_label_es', brief['date'])}", ""]
    for n, st in enumerate(stories, 1):
        lines += [f"{n}. {st['headline']}", f"   {_clip(st['summary'])}", f"   [{_label(st)}] Fuentes: {_srcs(st)}", f"   {st['read_original']}", ""]
    if cfg.get("disclaimer_es"):
        lines.append(cfg["disclaimer_es"])
    if cfg["site_url"]:
        lines.append(f"Edición completa: {cfg['site_url']}/#/niche/{niche['id']}")
    return "\n".join(lines).strip() + "\n"


def render_md(brief: dict, niche: dict, stories: list[dict], cfg: dict) -> str:
    """Markdown for Substack / Buttondown / any newsletter editor (paste as is)."""
    out = [f"# {niche['name']}", f"*{niche.get('subtitle', '')}* — {brief.get('date_label_es', brief['date'])}", ""]
    for st in stories:
        out += [f"## {st['headline']}", _clip(st["summary"]), "",
                f"**{_label(st)}** · Fuentes: {_srcs(st)} · [Leer la fuente]({st['read_original']})", ""]
    out += ["---", cfg.get("disclaimer_es", "")]
    if cfg["site_url"]:
        out.append(f"[{cfg['brand']}]({cfg['site_url']}/#/niche/{niche['id']})")
    return "\n".join(out).strip() + "\n"


def render_html(brief: dict, niche: dict, stories: list[dict], cfg: dict) -> str:
    """Self-contained, inline-styled HTML (email clients ignore <style> blocks)."""
    e = escape
    body = []
    for st in stories:
        body.append(
            f'<div style="margin:0 0 18px"><h2 style="font:600 18px/1.3 Georgia,serif;margin:0 0 4px">{e(st["headline"])}</h2>'
            f'<p style="font:15px/1.5 Arial,sans-serif;margin:0 0 4px">{e(_clip(st["summary"]))}</p>'
            f'<p style="font:13px/1.4 Arial,sans-serif;color:#555;margin:0">{e(_label(st))} · {e(_srcs(st))} · '
            f'<a href="{e(st["read_original"], quote=True)}">Leer la fuente</a></p></div>')
    foot = f'<p style="font:12px/1.4 Arial,sans-serif;color:#777">{e(cfg.get("disclaimer_es", ""))}</p>'
    return (f'<!doctype html><meta charset="utf-8"><title>{e(niche["name"])}</title>'
            f'<div style="max-width:560px;margin:0 auto;padding:16px"><h1 style="font:700 24px Georgia,serif;margin:0">{e(niche["name"])}</h1>'
            f'<p style="font:14px Arial,sans-serif;color:#555">{e(brief.get("date_label_es", brief["date"]))} · {e(cfg["brand"])}</p>'
            + "".join(body) + foot + "</div>\n")


def render_rss(brief: dict, niche: dict, stories: list[dict], cfg: dict) -> str:
    e = escape
    site = cfg["site_url"]
    now = format_datetime(datetime.now(timezone.utc))
    items = []
    for st in stories:
        desc = f"{_clip(st['summary'])} [{_label(st)}] Fuentes: {_srcs(st)}"
        items.append(f"<item><title>{e(st['headline'])}</title><link>{e(st['read_original'])}</link>"
                     f"<guid isPermaLink=\"false\">{e(brief['date'] + '-' + st['id'])}</guid><description>{e(desc)}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>{e(cfg['brand'])} · {e(niche['name'])}</title><link>{e(site)}</link>"
            f"<description>{e(niche.get('subtitle', ''))}</description><language>es</language><lastBuildDate>{now}</lastBuildDate>"
            + "".join(items) + "</channel></rss>\n")


def build_kit(brief: dict, docs: Path, cfg: dict | None = None) -> list[str]:
    """Write the kit for every niche of `brief`. Returns the list of written relative paths."""
    cfg = cfg or load_cfg()
    written, index = [], []
    for niche in brief.get("niches", []):
        stories = niche_stories(brief, niche)
        if not stories:
            continue
        for ext, fn in (("txt", render_text), ("md", render_md), ("html", render_html)):
            p = docs / "data" / "out" / f"{niche['id']}.{ext}"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(fn(brief, niche, stories, cfg), encoding="utf-8")
            written.append(f"data/out/{niche['id']}.{ext}")
        f = docs / "data" / "feeds" / f"{niche['id']}.xml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(render_rss(brief, niche, stories, cfg), encoding="utf-8")
        written.append(f"data/feeds/{niche['id']}.xml")
        index.append({"id": niche["id"], "name": niche["name"], "count": len(stories)})
    ch = {k: v for k, v in cfg.get("channels", {}).items() if v}
    meta = docs / "data" / "distribution.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"date": brief["date"], "channels": ch, "niches": index}, ensure_ascii=False), encoding="utf-8")
    written.append("data/distribution.json")
    return written
