"""Compose the daily briefing from ranked, verified clusters. Extractive only: every sentence is traceable
to a source item; nothing is generated that a source did not say."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .cluster import cluster_items
from .niches import load_niches, pick as pick_niche
from .rank import score_story, select_top
from .textutil import is_noise, clickbait_score, has_dispute, has_hedge, sentences, truncate_sentences, norm_tokens
from .verify import LABELS, source_trust, verify_cluster

MONTHS_ES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
SECTION_ORDER = ["world", "usa", "economy", "technology", "science", "climate", "sports", "culture"]
SECTION_ICON = {"world": "🌎", "usa": "🇺🇸", "economy": "💰", "technology": "🤖", "science": "🔬", "climate": "🌍", "sports": "⚽", "culture": "🎭"}
TAG_ES = {"world": "Mundo", "usa": "EE.UU.", "economy": "Economía", "technology": "Tecnología", "science": "Ciencia",
          "health": "Salud pública", "security": "Seguridad", "climate": "Clima", "sports": "Deportes", "culture": "Cultura"}


def _jacc(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0


def _best_items_per_owner(cluster, sources):
    best = {}
    for it in cluster:
        s = sources[it["source_id"]]
        key = s.get("owner", it["source_id"])
        tr = source_trust(s)
        # prefer items with a lead sentence, then higher trust
        rank = (bool(it.get("summary")), tr)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, it)
    return [v[1] for v in sorted(best.values(), key=lambda x: (-x[0][1], -x[0][0]))]


def _pick_headline(cluster, sources):
    # sober (non-clickbait) headline from the most trusted *news* outlet; official bulletins have terse titles
    cands = sorted(cluster, key=lambda it: (clickbait_score(it["title"]) > 0.3, bool(sources[it["source_id"]].get("primary")),
                                            -source_trust(sources[it["source_id"]]), clickbait_score(it["title"])))
    return cands[0]["title"].rstrip()


def _pick_summary(cluster, sources):
    withs = [it for it in cluster if it.get("summary")]
    withs.sort(key=lambda it: (has_hedge(it["summary"]), clickbait_score(it["title"]) > 0.3, -source_trust(sources[it["source_id"]]),
                               -min(len(it["summary"]), 400)))
    for it in withs:
        text = truncate_sentences(it["summary"], max_sentences=4, max_chars=620)
        if len(text) > 40:
            return text, it["source_id"]
    return "", None


def _why(rk, ver, n_out, sources_used, has_primary_name):
    sig = rk["why_signals"]
    parts = []
    if sig:
        parts.append("Relevant because it involves " + " and ".join(sig[:2]) + ".")
    else:
        parts.append("It is among the most widely covered developments of the last day.")
    if n_out == 1 and has_primary_name:
        parts.append(f"Published by an official/primary source ({has_primary_name}); independent coverage not yet found.")
    else:
        parts.append(f"Independently reported by {n_out} outlet{'s' if n_out != 1 else ''}"
                     + (f", including an official/primary source ({has_primary_name})." if has_primary_name else "."))
    return " ".join(parts)


def _know_unknown(cluster, sources, ver):
    know, unknown = [], []
    owners = _best_items_per_owner(cluster, sources)
    for it in owners[:4]:
        name = sources[it["source_id"]]["name"]
        line = it["summary"] and truncate_sentences(it["summary"], 1, 240) or it["title"]
        hedged = has_hedge(line + " " + it["title"])
        disp = has_dispute(line + " " + it["title"])
        tag = "Unconfirmed claim" if hedged else ("Contested" if disp else "Reported")
        know.append({"text": line, "source": name, "kind": tag})
    if ver.status == "UNVERIFIED":
        unknown.append("Only one outlet reports this so far; there is no independent confirmation yet.")
    if not ver.has_primary:
        unknown.append("No official or primary source (government, agency, court, journal) has been found confirming the details.")
    if ver.disputed:
        unknown.append("Some coverage contains denials or conflicting claims; the accounts have not been reconciled.")
    if ver.all_hedged:
        unknown.append("Coverage relies on attributed or anonymous claims that have not been independently verified.")
    if not unknown:
        unknown.append("Consequences and follow-up decisions are still to be reported; details may be updated.")
    return know, unknown


def build_story(cluster, ver, rk, sources) -> dict:
    headline = _pick_headline(cluster, sources)
    summary, lead_src = _pick_summary(cluster, sources)
    owners = _best_items_per_owner(cluster, sources)
    srcs = []
    for it in owners:
        s = sources[it["source_id"]]
        srcs.append({"id": it["source_id"], "name": s["name"], "url": it["link"], "title": it["title"],
                     "primary": bool(s.get("primary")), "trust": source_trust(s), "published": it["published"]})
    primary_name = next((x["name"] for x in srcs if x["primary"]), None)
    if not summary:
        names = ", ".join(x["name"] for x in srcs[:3])
        summary = f"Reported by {names}. These outlets published no summary text we can reuse; open the sources for details."
    know, unknown = _know_unknown(cluster, sources, ver)
    story_id = min(it["id"] for it in cluster)
    return {
        "id": story_id, "headline": headline, "summary": summary,
        "why_it_matters": _why(rk, ver, ver.independent_sources, len(srcs), primary_name),
        "know": know, "unknown": unknown,
        "status": ver.status, "status_label": LABELS[ver.status], "confidence": ver.confidence,
        "independent_sources": ver.independent_sources, "has_primary": ver.has_primary,
        "contested": ver.disputed, "attributed_only": ver.all_hedged, "verification_notes": ver.notes,
        "priority": rk["priority"], "category": rk["category"], "tags": rk["tags"], "must_know": rk["must_know"],
        "score": rk["score"], "newest_age_h": rk["newest_age_h"],
        "sources": srcs,
        "read_original": next((x["url"] for x in srcs if "news.google." not in x["url"]), srcs[0]["url"] if srcs else ""),
        "published": max(it["published"] for it in cluster),
        "political": "politics" in rk["tags"],
        "political_note": ("Statements by officials are shown as statements (\"X said\"), not as established facts."
                           if "politics" in rk["tags"] else ""),
    }


def analyse(items, sources, now, local_keywords=None):
    items = [i for i in items if not is_noise(i["title"])]
    clusters = cluster_items(items, sources)
    stories = []
    for c in clusters:
        ver = verify_cluster(c, sources)
        rk = score_story(c, ver, now, sources, local_keywords)
        stories.append({"cluster": c, "verification": {"status": ver.status}, "rank": rk, "_ver": ver})
    return stories


def compose(items, sources, settings, now: datetime, health: dict | None = None) -> dict:
    tz = ZoneInfo(settings["brief"]["timezone"])
    local = now.astimezone(tz)
    n = settings["brief"].get("max_stories", 10)
    pool_n = settings["brief"].get("pool_size", 25)
    analysed = analyse(items, sources, now, settings.get("local_keywords"))
    top = select_top(analysed, n)
    top_ids = {id(s) for s in top}
    rest = sorted([s for s in analysed if id(s) not in top_ids and s["rank"]["score"] >= 22 and s["_ver"].status != "UNVERIFIED"],
                  key=lambda s: -s["rank"]["score"])[: max(pool_n - len(top), 0)]

    def mk(s):
        return build_story(s["cluster"], s["_ver"], s["rank"], sources)

    top_st = [mk(s) for s in top]
    for i, st in enumerate(top_st, 1):
        st["position"] = i
        st["in_top"] = True
    pool_st = [mk(s) for s in rest]
    for st in pool_st:
        st["in_top"] = False

    base_pool = list(pool_st)          # sections and THE BIGGEST STORY are computed without niche extras
    # niche editions: focused lists over the same verified stories; their stories are added to the pool so every link works
    niches_out, known = [], {st["id"] for st in top_st + pool_st}
    by_cluster = {}
    for niche in load_niches():
        ids = []
        for s in pick_niche(analysed, niche):
            st = by_cluster.get(id(s)) or mk(s)
            by_cluster[id(s)] = st
            if st["id"] not in known:
                st["in_top"] = False
                pool_st.append(st)
                known.add(st["id"])
            ids.append(st["id"])
        if ids:
            niches_out.append({"id": niche["id"], "name": niche["name"], "subtitle": niche.get("subtitle", ""), "story_ids": ids})

    allst = top_st + base_pool
    sections = {}
    for cat in SECTION_ORDER:
        refs = sorted([s for s in allst if s["category"] == cat], key=lambda s: -s["score"])[:3]
        sections[cat] = [{"id": s["id"], "headline": s["headline"], "status": s["status"], "url": s["read_original"],
                          "source": s["sources"][0]["name"] if s["sources"] else ""} for s in refs]

    # THE BIGGEST STORY: the story that dominates coverage (most independent, credible outlets), factual only.
    biggest = None
    if allst:
        b = max(allst, key=lambda s: (s["independent_sources"] * (1 if s["status"] != "UNVERIFIED" else 0.3), s["score"]))
        biggest = {
            "story_id": b["id"], "headline": b["headline"], "description": b["summary"],
            "coverage": f"Covered independently by {b['independent_sources']} outlet(s)" +
                        (" including an official source" if b["has_primary"] else "") + ".",
            "status": b["status"], "sources": b["sources"][:4],
        }

    warnings = []
    if health:
        if health["feeds_ok"] < max(3, health["feeds_total"] * 0.4):
            warnings.append(f"Low source availability: {health['feeds_ok']}/{health['feeds_total']} feeds responded.")
        if len(top_st) < n:
            warnings.append(f"Only {len(top_st)} stories met the quality bar today.")
    unver = sum(1 for s in top_st if s["status"] == "UNVERIFIED")
    if unver:
        warnings.append(f"{unver} selected stor{'y is' if unver == 1 else 'ies are'} unconfirmed and labelled as such.")

    return {
        "schema": 1,
        "date": local.strftime("%Y-%m-%d"),
        "date_label_es": f"{local.day} {MONTHS_ES[local.month - 1]} {local.year}",
        "generated_at": now.isoformat(), "timezone": settings["brief"]["timezone"],
        "title": "MORNING BRIEF", "subtitle": f"{len(top_st)} COSAS QUE DEBES SABER HOY",
        "stories": top_st, "pool": pool_st, "niches": niches_out, "sections": sections, "biggest_story": biggest,
        "warnings": warnings,
        "stats": {"items": len(items), "clusters": len(analysed), "feeds_ok": (health or {}).get("feeds_ok"),
                  "feeds_total": (health or {}).get("feeds_total"),
                  "sources_used": (health or {}).get("sources_with_items", [])},
    }


def render_text(brief: dict) -> str:
    """Plain-text rendering (email/notification/CLI), following the requested layout."""
    bar = "━" * 20
    out = [bar, "GOOD MORNING", "MORNING BRIEF", brief["date_label_es"], brief["subtitle"], bar]
    for st in brief["stories"]:
        out += [f"{st['position']:02d} — {st['headline']}", st["summary"], "", f"¿Por qué importa?\n{st['why_it_matters']}", "",
                f"[{st['status_label']['es']}]", "Qué sabemos:"]
        out += [f"  • ({k['source']}, {k['kind']}) {k['text']}" for k in st["know"]]
        out += ["Qué todavía no sabemos:"] + [f"  • {u}" for u in st["unknown"]]
        out += ["Fuentes: " + " · ".join(s["name"] for s in st["sources"][:4]),
                "READ ORIGINAL: " + st["read_original"], bar]
    for cat in SECTION_ORDER:
        rows = brief["sections"].get(cat) or []
        if rows:
            out.append(f"{SECTION_ICON[cat]} {cat.upper()}")
            out += [f"  – {r['headline']} ({r['source']})" for r in rows]
    if brief.get("biggest_story"):
        b = brief["biggest_story"]
        out += ["", "THE BIGGEST STORY", b["headline"], b["description"], b["coverage"]]
    return "\n".join(out)
