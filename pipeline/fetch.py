"""News acquisition: RSS/Atom + USGS GeoJSON, parallel, resilient. Legit feeds only (no scraping)."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from .textutil import clean_html, strip_source_suffix

log = logging.getLogger("mb.fetch")
UA = "MorningBriefAI/1.0 (+personal news digest; RSS reader)"
NS = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/elements/1.1/",
      "content": "http://purl.org/rss/1.0/modules/content/", "media": "http://search.yahoo.com/mrss/"}


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url)
        q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "at_", "ocid", "smid", "cmp", "ref"))]
        return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urlencode(q), ""))
    except Exception:  # pragma: no cover
        return url


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _text(el, path):
    x = el.find(path, NS)
    return (x.text or "").strip() if x is not None and x.text else ""


def parse_feed(xml_bytes: bytes) -> list[dict]:
    """Parse RSS 2.0 / Atom / RDF into raw entry dicts."""
    root = ET.fromstring(xml_bytes)
    entries: list[dict] = []
    tag = root.tag.lower()
    if tag.endswith("feed"):  # Atom
        for e in root.findall("atom:entry", NS):
            link = ""
            for l in e.findall("atom:link", NS):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            entries.append({"title": _text(e, "atom:title"), "link": link,
                            "summary": _text(e, "atom:summary") or _text(e, "atom:content"),
                            "published": _text(e, "atom:published") or _text(e, "atom:updated")})
    else:  # RSS / RDF
        items = root.findall(".//item")
        for e in items:
            entries.append({
                "title": _text(e, "title"), "link": _text(e, "link"),
                "summary": _text(e, "description") or _text(e, "content:encoded"),
                "published": _text(e, "pubDate") or _text(e, "dc:date"),
            })
    return entries


def parse_usgs(body: bytes) -> list[dict]:
    data = json.loads(body)
    out = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        mag, place = p.get("mag"), p.get("place")
        if mag is None or not place:
            continue
        t = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).isoformat()
        tsu = " A tsunami warning was associated with this event." if p.get("tsunami") else ""
        out.append({"title": f"Magnitude {mag} earthquake strikes {place}", "link": p.get("url", ""),
                    "summary": f"USGS recorded a magnitude {mag} earthquake, {place}. Alert level: {p.get('alert') or 'not assigned'}.{tsu}",
                    "published": t})
    return out


def _http_get(url: str, timeout: float, retries: int = 2) -> bytes:
    import requests  # local import so tests with fixtures need no network stack
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
                             timeout=timeout)
            if r.status_code == 200 and r.content:
                return r.content
            last = f"HTTP {r.status_code}"
            if r.status_code in (401, 403, 404, 410):  # blocked/missing: retrying will not help
                break
        except Exception as ex:  # noqa: BLE001
            last = repr(ex)
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(last or "unknown error")


def _fetch_one(src_id: str, src: dict, feed: dict, max_age: timedelta, now: datetime, timeout: float, fixtures: Path | None):
    url = feed["url"]
    t0 = time.time()
    if fixtures:
        fx = fixtures / f"{src_id}__{hashlib.md5(url.encode()).hexdigest()[:8]}.xml"
        fx_alt = fixtures / f"{src_id}.xml"
        path = fx if fx.exists() else fx_alt
        if not path.exists():
            raise RuntimeError("no fixture")
        body = path.read_bytes()
    else:
        body = _http_get(url, timeout)
    raw = parse_usgs(body) if src.get("parser") == "usgs_geojson" else parse_feed(body)
    items = []
    for r in raw:
        title = strip_source_suffix(clean_html(r["title"])) if src.get("headline_only") else clean_html(r["title"])
        link = r["link"].strip()
        if not title or not link:
            continue
        pub = parse_date(r["published"]) or now
        if now - pub > max_age or pub - now > timedelta(hours=2):
            continue
        summ = "" if src.get("headline_only") else clean_html(r["summary"])
        if summ.lower().startswith(title.lower()[:40]) and len(summ) < len(title) + 15:
            summ = ""
        items.append({
            "id": hashlib.sha1(canonical_url(link).encode()).hexdigest()[:12],
            "title": title, "summary": summ, "link": link, "published": pub.isoformat(),
            "source_id": src_id, "category_hint": feed.get("category", "general"),
        })
    return items, round(time.time() - t0, 2)


def fetch_all(sources: dict, now: datetime, max_age_hours: int = 30, workers: int = 12,
              timeout: float = 15, fixtures: Path | None = None):
    """Returns (items, health). A failing feed never aborts the run."""
    jobs = [(sid, s, f) for sid, s in sources.items() for f in s["feeds"]]
    items, health = [], {"feeds_total": len(jobs), "feeds_ok": 0, "failed": [], "per_source": {}}
    max_age = timedelta(hours=max_age_hours)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one, sid, s, f, max_age, now, timeout, fixtures): (sid, f) for sid, s, f in jobs}
        for fu in as_completed(futs):
            sid, f = futs[fu]
            try:
                got, secs = fu.result()
                items.extend(got)
                health["feeds_ok"] += 1
                health["per_source"][sid] = health["per_source"].get(sid, 0) + len(got)
            except Exception as e:  # noqa: BLE001
                health["failed"].append({"source": sid, "url": f["url"], "error": str(e)[:160]})
                log.warning("feed failed %s: %s", f["url"], e)
    # exact-URL dedupe (same story appearing in several feeds of one outlet)
    seen, uniq = set(), []
    for it in items:
        key = (it["source_id"], it["id"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    health["items"] = len(uniq)
    health["sources_with_items"] = sorted(health["per_source"])
    return uniq, health
