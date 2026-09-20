"""Internal importance ranking. Scores are never shown as "truth"; they only decide selection order.

Priority: importance + credibility + impact + verification. NOT clicks, virality or controversy.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .textutil import clickbait_score

# ---- tunables (documented in README) ---------------------------------------------------------
THRESHOLDS = {
    "min_score": 22,          # below this a story is never selected
    "diversity_floor": 34,    # a category is only "pulled in" for diversity if its best story clears this
    "extraordinary": 74,      # such a story may occupy several slots (exempt from per-category cap)
    "must_know": 60,          # never removed by personalisation
    "important": 48,
    "urgent": 66,
    "breaking": 80,
}
GROUP_CAP = 3
DIVERSITY_ORDER = ["world", "usa", "economy", "technology", "science", "health", "security", "climate", "culture_sports"]
GROUP_OF = {"sports": "culture_sports", "culture": "culture_sports"}

# (regex, weight 0..1, tags, "why" phrase)
SIGNALS = [
    (r"\b(killed|dead|deaths?|died|fatalities|casualties|massacre)\b", 0.70, ["security"], "loss of life"),
    (r"\b(war|invasion|invade[sd]?|offensive|airstrikes?|missiles?|shelling|troops|ceasefire|truce|hostages?)\b", 0.72, ["world", "security"], "armed conflict or its diplomacy"),
    (r"\b(nuclear|radiation|atomic)\b", 0.65, ["security"], "nuclear risk"),
    (r"\b(pandemic|outbreak|epidemic|virus|measles|cholera|ebola|bird flu|h5n1|mpox|public health emergency)\b", 0.72, ["health"], "public health"),
    (r"\b(earthquake|tsunami|hurricane|typhoon|cyclone|tornado|wildfires?|flood(s|ing)?|eruption|heat ?wave|storm)\b", 0.62, ["climate"], "natural hazard affecting people"),
    (r"\b(election|elections|vote|voters?|ballot|referendum|coup|impeach\w*|resigns?|resignation|assassinat\w*)\b", 0.62, ["politics"], "political leadership and governance"),
    (r"\b(supreme court|congress|senate|house of representatives|white house|parliament|prime minister|president)\b", 0.42, ["politics"], "government decisions"),
    (r"\b(sanctions?|tariffs?|treaty|summit|embassy|diplomat\w*|un security council|nato)\b", 0.52, ["world", "economy"], "international relations and trade"),
    (r"\b(interest rates?|rate (cut|hike)|federal reserve|the fed|inflation|cpi|jobs report|unemployment|payrolls|recession|gdp)\b", 0.66, ["economy"], "prices, borrowing costs and jobs"),
    (r"\b(stocks?|shares|wall street|s&p 500|nasdaq|dow|markets?)\b.*\b(plunge[sd]?|tumble[sd]?|surge[sd]?|soar(s|ed)?|crash(es|ed)?|rall(y|ies|ied)|sell-?off)\b", 0.58, ["economy"], "financial markets"),
    (r"\b(oil prices?|crude|opec|natural gas prices?|gold prices?)\b", 0.46, ["economy"], "energy and commodity prices"),
    (r"\b(bank (failure|collapse|run)|bankrupt\w*|default|debt ceiling|shutdown)\b", 0.62, ["economy"], "financial stability"),
    (r"\b(cyber ?attack|ransomware|data breach|hack(ed|ers?)?|outage|zero-day)\b", 0.55, ["technology", "security"], "digital security and services"),
    (r"\b(artificial intelligence|\bAI\b|openai|anthropic|chatgpt|gemini|llm|chips?|semiconductors?)\b", 0.40, ["technology", "ai"], "technology shifts"),
    (r"\b(breakthrough|discover(y|ed|s)|clinical trial|study finds|researchers|peer-reviewed|fda approv\w*|vaccine)\b", 0.45, ["science", "health"], "scientific and medical progress"),
    (r"\b(nasa|spacex|rocket|launch(es|ed)?|artemis|mars|moon|telescope|asteroid|satellite|space station)\b", 0.40, ["space", "science"], "space exploration"),
    (r"\b(climate|emissions|carbon|global warming|drought|sea level|cop\d+)\b", 0.42, ["climate"], "climate and environment"),
    (r"\b(bitcoin|ethereum|crypto\w*|stablecoin|sec (charges|sues))\b", 0.35, ["crypto", "economy"], "crypto markets and regulation"),
    (r"\b(evacuat\w+|state of emergency|martial law|curfew|lockdown|recall)\b", 0.58, ["security"], "public safety"),
    (r"\b(world cup|olympics?|super bowl|champions league|nba finals|world series|grand slam|stanley cup)\b", 0.34, ["sports"], "major sporting event"),
    (r"\b(oscars?|grammys?|emmys?|cannes|box office|album|film festival|nobel)\b", 0.28, ["entertainment", "culture"], "cultural event"),
    (r"\b(game|gaming|playstation|xbox|nintendo|steam|esports)\b", 0.20, ["gaming"], "gaming industry"),
]
_SIG = [(re.compile(p, re.I), w, t, why) for p, w, t, why in SIGNALS]

FLUFF = re.compile(r"\b(celebrity|kardashian|red carpet|dating|dress|outfit|horoscope|recipe|gossip|influencer|tiktok trend|"
                   r"quiz|best deals?|black friday|review:|podcast|newsletter|opinion|column|editorial)\b", re.I)
OPINION_TITLE = re.compile(r"^\s*(opinion|analysis|editorial|column|letters?|commentary|review)\b\s*[:|-]", re.I)
OPINION_URL = re.compile(r"/(opinion|opinions|commentisfree|editorial|voices|analysis-opinion|blogs?)/", re.I)

CAT_KEYWORDS = {
    "usa": r"\b(u\.?s\.?|united states|american|trump|biden|harris|vance|congress|senate|white house|pentagon|supreme court|fbi|doj|federal|washington)\b",
    "economy": r"\b(econom\w+|inflation|fed|rates?|markets?|stocks?|shares|earnings|gdp|jobs|tariffs?|oil|bank\w*|trade|prices?|dollar|wall street)\b",
    "technology": r"\b(tech\w*|ai|artificial intelligence|software|chip\w*|apple|google|microsoft|meta|nvidia|openai|cyber\w*|app|startup|robot\w*|cloud|outage|internet|websites?|hack\w*|data breach)\b",
    "science": r"\b(scien\w+|researchers?|study|nasa|space|telescope|physics|species|fossil|discover\w+|astronom\w+|quantum)\b",
    "health": r"\b(health|virus|outbreak|disease|vaccine|hospital|cancer|fda|who|cdc|drug|medic\w+|pandemic|measles)\b",
    "security": r"\b(attack\w*|shooting|terror\w*|police|military|troops|missile|war|security|bomb\w*|killed|hostage\w*|crime)\b",
    "climate": r"\b(climate|weather|hurricane|wildfire|flood\w*|storm|earthquake|tsunami|drought|emissions|heat ?wave|environment)\b",
    "sports": r"\b(sport\w*|nba|nfl|mlb|nhl|fifa|olympic\w*|world cup|match|league|tournament|championship|coach|goal|tennis|golf|f1|formula 1)\b",
    "culture": r"\b(film|movie|music|album|celebrity|festival|oscar\w*|grammy\w*|art|museum|book|tv|series|actor|singer|theatre|nobel)\b",
}
_CAT = {k: re.compile(v, re.I) for k, v in CAT_KEYWORDS.items()}
HINT_MAP = {"world": "world", "usa": "usa", "economy": "economy", "technology": "technology", "science": "science",
            "health": "health", "climate": "climate", "sports": "sports", "politics": "usa", "general": None}
TAG_KEYWORDS = {
    "ai": r"\b(ai|artificial intelligence|openai|chatgpt|anthropic|gemini|llm|machine learning)\b",
    "space": r"\b(nasa|spacex|space|rocket|moon|mars|asteroid|telescope|satellite|orbit)\b",
    "crypto": r"\b(bitcoin|ethereum|crypto\w*|stablecoin|blockchain)\b",
    "gaming": r"\b(gaming|video ?games?|playstation|xbox|nintendo|steam|esports)\b",
    "politics": r"\b(election|congress|senate|parliament|president|prime minister|minister|policy|government|legislat\w+|campaign|party)\b",
    "business": r"\b(company|companies|ceo|earnings|merger|acquisition|ipo|revenue|profit|layoffs?|startup|business)\b",
    "entertainment": r"\b(film|movie|music|album|celebrity|tv|series|actor|singer|box office|streaming)\b",
}
_TAG = {k: re.compile(v, re.I) for k, v in TAG_KEYWORDS.items()}

NUM_CASUALTY = re.compile(r"\b(\d[\d,]*)\s+(?:people\s+)?(?:have been\s+)?(?:killed|dead|deaths|died|injured|displaced|missing|evacuated)", re.I)
QUAKE_MAG = re.compile(r"magnitude\s+(\d(?:\.\d)?)", re.I)


def classify(cluster: list[dict], text: str, local_keywords: list[str]) -> tuple[str, list[str]]:
    scores = {k: len(rx.findall(text)) for k, rx in _CAT.items()}
    for it in cluster:  # feed hint acts as a prior
        h = HINT_MAP.get(it["category_hint"])
        if h:
            scores[h] = scores.get(h, 0) + 1.5
    world_hits = len(re.findall(r"\b(china|russia|ukraine|israel|gaza|iran|india|europe\w*|africa\w*|asia\w*|middle east|"
                                r"un\b|nato|eu\b|london|paris|beijing|moscow|tehran|brazil|mexico|japan|korea|pakistan)\b", text, re.I))
    scores["world"] = scores.get("world", 0) + world_hits * 0.8
    # sports/culture must be dominant to win; otherwise hard news categories take precedence
    best = max(scores, key=lambda k: scores[k])
    if best in ("sports", "culture") and scores[best] < 3:
        rest = {k: v for k, v in scores.items() if k not in ("sports", "culture")}
        best = max(rest, key=lambda k: rest[k])
    if scores[best] == 0:
        best = "world"
    tags = {best}
    for k, rx in _TAG.items():
        if rx.search(text):
            tags.add(k)
    if local_keywords and any(k.lower() in text.lower() for k in local_keywords):
        tags.add("local")
    if best == "usa":
        tags.add("usa")
    if best == "economy":
        tags.add("business")
    return best, sorted(tags)


def impact_signals(text: str) -> tuple[float, list[tuple[str, float]], float]:
    hits = []
    for rx, w, tags, why in _SIG:
        if rx.search(text):
            hits.append((why, w))
    hits.sort(key=lambda x: -x[1])
    base = hits[0][1] if hits else 0.15
    bonus = 0.06 * min(len(hits) - 1, 3) if hits else 0
    scale = 0.0
    for m in NUM_CASUALTY.finditer(text):
        n = int(m.group(1).replace(",", ""))
        if n < 10_000_000:
            scale = max(scale, min(math.log10(max(n, 1)) / 5, 1.0))
    q = QUAKE_MAG.search(text)
    if q:
        mag = float(q.group(1))
        scale = max(scale, min(max(mag - 4.5, 0) / 3, 1.0))
        base = max(base, 0.5 + 0.1 * max(mag - 6, 0))
    return min(base + bonus + 0.25 * scale, 1.0), hits, scale


def score_story(cluster: list[dict], ver, now: datetime, sources: dict, local_keywords=None) -> dict:
    text = " ".join(it["title"] + ". " + it.get("summary", "") for it in cluster)
    category, tags = classify(cluster, text, local_keywords or [])
    impact, hits, scale = impact_signals(text)

    ages = []
    for it in cluster:
        p = datetime.fromisoformat(it["published"])
        ages.append((now - p).total_seconds() / 3600)
    newest_h = max(min(ages), 0)
    recency = max(0.0, 1 - newest_h / 30)
    breadth = min(ver.independent_sources / 6, 1.0)
    daily = 0.7 if any(w in ("prices, borrowing costs and jobs", "public health", "public safety", "energy and commodity prices",
                             "digital security and services", "natural hazard affecting people") for w, _ in hits) else 0.2
    cb = sum(clickbait_score(it["title"]) for it in cluster) / len(cluster)
    fluff = bool(FLUFF.search(text))
    opinion = all(OPINION_URL.search(it["link"]) or OPINION_TITLE.search(it["title"]) for it in cluster)

    raw = (0.30 * impact + 0.22 * breadth + 0.18 * ver.confidence + 0.10 * recency + 0.08 * daily + 0.12 * scale
           + 0.05 * (1 if ver.has_primary else 0)) * 100
    raw = raw / 0.95  # normalise weights (sum .95+.05)
    raw -= 28 * cb
    if fluff:
        raw -= 18
    if opinion:
        raw -= 30  # opinion pieces are not "what happened"
    if ver.status == "UNVERIFIED":
        raw -= 12
    score = round(min(max(raw, 0), 100), 1)

    # priority level with explicit, auditable criteria
    if (score >= THRESHOLDS["breaking"] and ver.status in ("CONFIRMED", "LIKELY") and newest_h <= 3
            and (ver.independent_sources >= 3 or (ver.has_primary and ver.independent_sources >= 2)) and impact >= 0.8):
        priority = "BREAKING"
    elif score >= THRESHOLDS["urgent"] and ver.status in ("CONFIRMED", "LIKELY") and newest_h <= 12:
        priority = "URGENT"
    elif score >= THRESHOLDS["important"]:
        priority = "IMPORTANT"
    else:
        priority = "NORMAL"
    return {
        "category": category, "tags": tags, "score": score, "impact": round(impact, 3), "newest_age_h": round(newest_h, 1),
        "why_signals": [w for w, _ in hits[:3]], "clickbait": round(cb, 2), "priority": priority,
        "must_know": score >= THRESHOLDS["must_know"] and ver.status != "UNVERIFIED",
    }


def _group(cat: str) -> str:
    return GROUP_OF.get(cat, cat)


def select_top(stories: list[dict], n: int = 10) -> list[dict]:
    """stories: each has ['rank'] dict and ['verification'].status. Returns ordered selection."""
    T = THRESHOLDS
    cands = [s for s in stories if s["rank"]["score"] >= T["min_score"]]
    ok = [s for s in cands if s["verification"]["status"] != "UNVERIFIED"]
    weak = [s for s in cands if s["verification"]["status"] == "UNVERIFIED"]
    ok.sort(key=lambda s: -s["rank"]["score"])
    weak.sort(key=lambda s: -s["rank"]["score"])
    chosen: list[dict] = []
    counts: dict[str, int] = {}

    def add(s):
        chosen.append(s)
        counts[_group(s["rank"]["category"])] = counts.get(_group(s["rank"]["category"]), 0) + 1

    if ok:
        add(ok[0])
    # diversity pass: best story per group, only if it clears the floor (never forced)
    for g in DIVERSITY_ORDER:
        if len(chosen) >= n:
            break
        for s in ok:
            if s in chosen or _group(s["rank"]["category"]) != g:
                continue
            if s["rank"]["score"] >= T["diversity_floor"]:
                add(s)
            break
    # fill by score; per-group cap unless extraordinary
    for s in ok:
        if len(chosen) >= n:
            break
        if s in chosen:
            continue
        g = _group(s["rank"]["category"])
        if counts.get(g, 0) >= GROUP_CAP and s["rank"]["score"] < T["extraordinary"]:
            continue
        add(s)
    for s in ok:  # relax cap if still short
        if len(chosen) >= n:
            break
        if s not in chosen:
            add(s)
    for s in weak:  # last resort: clearly labelled unconfirmed
        if len(chosen) >= n:
            break
        add(s)
    chosen.sort(key=lambda s: -s["rank"]["score"])
    return chosen
