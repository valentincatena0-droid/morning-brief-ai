"""Flat-file storage (JSON in docs/data). Git history = versioned archive; GitHub Pages = free hosting.
Indexes are rebuilt from the brief files each time, so they can never drift."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)  # atomic


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def existing_dates(docs: Path) -> set[str]:
    d = docs / "data" / "briefs"
    return {p.stem for p in d.glob("*.json")} if d.exists() else set()


def write_brief(docs: Path, brief: dict) -> None:
    data = docs / "data"
    _dump(data / "briefs" / f"{brief['date']}.json", brief)
    _dump(data / "latest.json", brief)
    rebuild_indexes(docs)


def rebuild_indexes(docs: Path) -> None:
    data = docs / "data"
    index, search = [], []
    for p in sorted((data / "briefs").glob("*.json"), reverse=True):
        b = _load(p, None)
        if not b:
            continue
        index.append({"date": b["date"], "label": b.get("date_label_es", b["date"]), "count": len(b["stories"]),
                      "headlines": [s["headline"] for s in b["stories"][:10]]})
        for s in b["stories"] + b.get("pool", []):
            search.append({"d": b["date"], "id": s["id"], "h": s["headline"], "s": s["summary"][:240], "c": s["category"],
                           "src": [x["name"] for x in s["sources"][:4]], "u": s["read_original"], "top": bool(s.get("in_top"))})
    _dump(data / "index.json", index)
    _dump(data / "search.json", search)


def load_alerts(docs: Path) -> list[dict]:
    return _load(docs / "data" / "alerts.json", [])


def save_alerts(docs: Path, alerts: list[dict]) -> None:
    _dump(docs / "data" / "alerts.json", alerts[:60])


def save_health(docs: Path, health: dict, note: str) -> None:
    _dump(docs / "data" / "health.json", {**health, "note": note})


def load_brief(docs: Path, date: str):
    return _load(docs / "data" / "briefs" / f"{date}.json", None)
