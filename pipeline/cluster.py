"""Group items about the same event (near-duplicate + related-coverage clustering)."""
from __future__ import annotations

import math
from collections import Counter

from .textutil import norm_tokens


def _vec(item: dict) -> Counter:
    toks = norm_tokens(item["title"])
    # lead text adds signal, but titles dominate
    lead = norm_tokens(item.get("summary", "")[:240])
    c = Counter(toks * 3)
    c.update(lead)
    return c


def _cos(a: Counter, b: Counter, idf: dict) -> float:
    num = sum(a[t] * b[t] * idf.get(t, 1) ** 2 for t in a.keys() & b.keys())
    da = math.sqrt(sum((a[t] * idf.get(t, 1)) ** 2 for t in a))
    db = math.sqrt(sum((b[t] * idf.get(t, 1)) ** 2 for t in b))
    return num / (da * db) if da and db else 0.0


def cluster_items(items: list[dict], threshold: float = 0.42, min_shared_title: int = 2) -> list[list[dict]]:
    """Union-find over TF-IDF cosine similarity. Requires >= min_shared_title shared title tokens
    (with at least one rare token) to prevent chaining unrelated stories through generic words."""
    n = len(items)
    vecs = [_vec(i) for i in items]
    tsets = [set(norm_tokens(i["title"])) for i in items]
    df: Counter = Counter()
    for v in vecs:
        df.update(v.keys())
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    tdf: Counter = Counter()
    for ts in tsets:
        tdf.update(ts)
    tidf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in tdf.items()}
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # inverted index to avoid O(n^2) on large pools
    inv: dict[str, list[int]] = {}
    for i, ts in enumerate(tsets):
        for t in ts:
            inv.setdefault(t, []).append(i)
    checked = set()
    for t, idxs in inv.items():
        if len(idxs) > 60:  # very common token: skip as a blocking key
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if (i, j) in checked or find(i) == find(j):
                    continue
                checked.add((i, j))
                shared = tsets[i] & tsets[j]
                if len(shared) < 1:
                    continue
                if len(shared) < min_shared_title and (items[i]["source_id"] == items[j]["source_id"]):
                    continue
                if not any(df[s] <= max(14, n * 0.04) for s in shared):
                    continue
                same_src = items[i]["source_id"] == items[j]["source_id"]
                thr = threshold + (0.15 if same_src else 0)  # same-outlet pairs need to be closer
                cos = _cos(vecs[i], vecs[j], idf)
                # rule 2: several distinctive shared title tokens (entity + event) => same story even if the
                # lead texts differ a lot (e.g. an official press release vs. a news write-up)
                distinctive = sum(tidf[s] for s in shared if tdf[s] <= max(12, n * 0.04))
                if cos >= thr or (not same_src and distinctive >= 6.5 and cos >= 0.12):
                    parent[find(i)] = find(j)
                elif (not same_src and cos >= 0.28 and len(vecs[i].keys() & vecs[j].keys()) >= 5):
                    parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    return list(groups.values())
