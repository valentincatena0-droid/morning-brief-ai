"""Group items about the same event WITHOUT transitive chaining.

Leader clustering: items are processed best-source-first; an item joins a cluster only if it is similar to the
cluster CENTROID (not merely to one member), so unrelated stories cannot be glued together through generic words
("Trump", "Iran", "US", "market"). Wrongly merging stories would fabricate corroboration, so we prefer to under-merge.
"""
from __future__ import annotations

import math
from collections import Counter

from .textutil import norm_tokens

MIN_DISTINCT = 5.5      # summed idf of shared distinctive title tokens
JOIN_COS = 0.30         # cosine to cluster centroid
NEAR_DUP_COS = 0.60     # same-outlet items must be near-duplicates
# event-generic words: they say *what kind* of thing happened, not *which* event, so they never justify linking stories
WEAK = {"suspect", "polic", "official", "forc", "govern", "presid", "minist", "court", "found", "first", "last", "plan", "deal",
        "talk", "warn", "sign", "announc", "call", "fac", "face", "back", "move", "open", "start", "begin", "end", "lead", "rise",
        "fall", "drop", "hit", "leader", "member", "group"}


def _vec(item: dict) -> Counter:
    c = Counter(norm_tokens(item["title"]) * 3)
    c.update(norm_tokens(item.get("summary", "")[:240]))
    return c


def _cos(a: Counter, b: Counter, idf: dict) -> float:
    num = sum(a[t] * b[t] * idf.get(t, 1) ** 2 for t in a.keys() & b.keys())
    da = math.sqrt(sum((v * idf.get(t, 1)) ** 2 for t, v in a.items()))
    db = math.sqrt(sum((v * idf.get(t, 1)) ** 2 for t, v in b.items()))
    return num / (da * db) if da and db else 0.0


def cluster_items(items: list[dict], sources: dict | None = None) -> list[list[dict]]:
    n = len(items)
    if n == 0:
        return []
    vecs = [_vec(i) for i in items]
    tsets = [set(norm_tokens(i["title"])) for i in items]
    df: Counter = Counter()
    for v in vecs:
        df.update(v.keys())
    tdf: Counter = Counter()
    for ts in tsets:
        tdf.update(ts)
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    tidf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in tdf.items()}
    common = max(25, n * 0.05)      # tokens more frequent than this are too generic to link stories
    weak = WEAK

    def prio(i):  # seeds: trusted sources with body text first
        s = (sources or {}).get(items[i]["source_id"], {})
        return (-(s.get("reputation", 0.5) + 0.25 * float(s.get("primary", 0))), -len(items[i].get("summary", "")))

    order = sorted(range(n), key=prio)
    clusters: list[dict] = []     # {"members": [idx], "centroid": Counter, "titles": Counter, "srcs": set}
    inv: dict[str, list[int]] = {}
    for i in order:
        cand: Counter = Counter()
        for t in tsets[i]:
            if tdf[t] <= common:
                for ci in inv.get(t, ()):
                    cand[ci] += 1
        best, best_score = None, 0.0
        for ci in cand:
            c = clusters[ci]
            shared = tsets[i] & set(c["titles"])
            size = len(c["members"])
            # a shared token only counts as evidence if it (almost) lives in this cluster: template words that appear in
            # dozens of unrelated headlines ("Trump administration ... plan draws criticism") never justify a merge
            anchored = [s for s in shared if s not in weak and tdf[s] <= 1.6 * size + 3]
            if not anchored:
                continue
            distinct = sum(tidf[s] for s in shared if tdf[s] <= common and s not in weak)
            # similarity: full text vs centroid, but also vs the cluster's *title* profile so that long bodies
            # (which dilute the centroid) and headline-only wire items are compared fairly
            cos = max(_cos(vecs[i], c["centroid"], idf), _cos(Counter(tsets[i]), c["titles"], tidf), _cos(vecs[i], c["titles"], tidf) * 0.9)
            same_src = items[i]["source_id"] in c["srcs"]
            if same_src and cos < NEAR_DUP_COS:
                continue
            ok = (len(shared) >= 2 and distinct >= MIN_DISTINCT and cos >= JOIN_COS) or cos >= 0.55 or (len(shared) >= 2 and distinct >= 8.0 and cos >= 0.15)
            if ok and cos > best_score:
                best, best_score = ci, cos
        if best is None:
            clusters.append({"members": [i], "centroid": Counter(vecs[i]), "titles": Counter(tsets[i]), "srcs": {items[i]["source_id"]}})
            for t in tsets[i]:
                inv.setdefault(t, []).append(len(clusters) - 1)
        else:
            c = clusters[best]
            c["members"].append(i)
            c["centroid"].update(vecs[i])
            for t in tsets[i]:
                if t not in c["titles"]:
                    inv.setdefault(t, []).append(best)
            c["titles"].update(tsets[i])
            c["srcs"].add(items[i]["source_id"])
    # Merge pass: leader clustering is order dependent (a headline-only wire item may have seeded its own cluster before
    # its siblings arrived). Merge clusters whose aggregated TITLE profiles agree; still cluster-vs-cluster, so no chaining.
    alive = list(range(len(clusters)))
    changed = True
    rounds = 0
    while changed and rounds < 4:
        changed, rounds = False, rounds + 1
        cand_inv: dict[str, list[int]] = {}
        for ci in alive:
            for t in clusters[ci]["titles"]:
                if tdf[t] <= common:
                    cand_inv.setdefault(t, []).append(ci)
        merged: set[int] = set()
        for a in list(alive):
            if a in merged:
                continue
            peers = Counter()
            for t in clusters[a]["titles"]:
                for b in cand_inv.get(t, ()):
                    if b > a and b not in merged:
                        peers[b] += 1
            for b, k in peers.most_common(6):
                if k < 2:
                    break
                ca, cb = clusters[a], clusters[b]
                shared = set(ca["titles"]) & set(cb["titles"])
                distinct = sum(tidf[t] for t in shared if tdf[t] <= common and t not in weak)
                big = max(len(ca["members"]), len(cb["members"]))
                if not [t for t in shared if t not in weak and tdf[t] <= 1.6 * big + 3]:
                    continue
                single = min(len(ca["members"]), len(cb["members"])) == 1      # e.g. a terse official bulletin
                anchored_n = len([t for t in shared if t not in weak and tdf[t] <= 1.6 * big + 3])
                if single and anchored_n >= 3 and distinct >= 7.0 and _cos(ca["titles"], cb["titles"], tidf) >= 0.15:
                    pass                                                        # relaxed: several distinctive shared tokens
                elif distinct < MIN_DISTINCT + 1 or _cos(ca["titles"], cb["titles"], tidf) < 0.40:
                    continue
                if ca["srcs"] & cb["srcs"] and len(ca["members"]) + len(cb["members"]) > 6:
                    continue      # two big clusters with overlapping outlets are probably different stories
                ca["members"] += cb["members"]
                ca["centroid"].update(cb["centroid"])
                ca["titles"].update(cb["titles"])
                ca["srcs"] |= cb["srcs"]
                merged.add(b)
                changed = True
        alive = [ci for ci in alive if ci not in merged]
    return [[items[i] for i in clusters[ci]["members"]] for ci in alive]
