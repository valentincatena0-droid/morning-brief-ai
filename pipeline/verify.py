"""Source credibility + cross-verification (corroboration) engine.

We never conclude "X is true because outlet Y printed it". A cluster gets a *confidence* from:
  - how many INDEPENDENT owners report it (syndicated/wire copies count once),
  - the credibility of each (reputation, accuracy record, correction transparency, primary-ness),
  - whether a primary/official source is among them,
  - contradiction markers (denials, disputes, conflicting claims) across items,
  - whether the wording is attributed/hedged ("reportedly", "sources say") everywhere.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .textutil import has_confirm, has_dispute, has_hedge

LABELS = {
    "CONFIRMED": {"en": "Confirmed", "es": "Alta confianza"},
    "LIKELY": {"en": "Largely confirmed", "es": "Parcialmente confirmada"},
    "DEVELOPING": {"en": "Developing", "es": "En desarrollo"},
    "UNVERIFIED": {"en": "Unconfirmed", "es": "No confirmada"},
}


def source_trust(s: dict) -> float:
    t = (0.40 * s.get("reputation", 0.5) + 0.25 * s.get("accuracy", 0.5)
         + 0.10 * s.get("corrections", 0.5) + 0.25 * float(s.get("primary", 0)))
    return round(min(max(t, 0.0), 1.0), 3)


@dataclass
class Verification:
    status: str
    confidence: float
    independent_sources: int
    has_primary: bool
    disputed: bool
    all_hedged: bool
    notes: list[str]


def verify_cluster(cluster: list[dict], sources: dict) -> Verification:
    by_owner: dict[str, float] = {}
    has_primary = False
    for it in cluster:
        s = sources[it["source_id"]]
        tr = source_trust(s) * (0.85 if s.get("headline_only") else 1.0)
        owner = s.get("owner", it["source_id"])
        by_owner[owner] = max(by_owner.get(owner, 0), tr)
        if s.get("primary"):
            has_primary = True
    n_owner = len(by_owner)

    # noisy-OR of independent, discounted trust values
    miss = 1.0
    for tr in by_owner.values():
        miss *= 1 - 0.6 * tr
    conf = 1 - miss

    texts = [it["title"] + ". " + it.get("summary", "") for it in cluster]
    disputed = any(has_dispute(t) for t in texts)
    hedged_flags = [has_hedge(t) for t in texts]
    all_hedged = all(hedged_flags)
    official_confirm = any(has_confirm(t) for t in texts)
    notes: list[str] = []

    if has_primary:
        conf += 0.10
        notes.append("primary/official source present")
    elif official_confirm:
        conf += 0.03
    else:
        notes.append("no primary/official source found yet")
    if disputed:
        conf -= 0.25
        notes.append("sources contain denials or conflicting claims")
    if all_hedged:
        conf -= 0.15
        notes.append("all coverage relies on attributed/unconfirmed claims")
    conf = round(min(max(conf, 0.05), 0.99), 3)

    if disputed:
        status = "DEVELOPING"
    elif has_primary and n_owner >= 2 and conf >= 0.8 and not all_hedged:
        status = "CONFIRMED"
    elif n_owner >= 3 and conf >= 0.85 and not all_hedged:
        status = "CONFIRMED"
    elif has_primary and not all_hedged:
        status = "LIKELY" if n_owner == 1 else "CONFIRMED"
    elif n_owner >= 2 and conf >= 0.6 and not all_hedged:
        status = "LIKELY"
    elif n_owner >= 2:
        status = "DEVELOPING"
    else:
        status = "UNVERIFIED"
    if n_owner == 1 and not has_primary:
        status = "UNVERIFIED" if all_hedged or conf < 0.55 else "DEVELOPING"
    return Verification(status, conf, n_owner, has_primary, disputed, all_hedged, notes)
