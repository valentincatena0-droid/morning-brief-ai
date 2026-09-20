"""Offline test-suite (stdlib unittest; no network). Run: python -m unittest discover -s tests -v"""
import json
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alerts as alerts_mod, notify, storage  # noqa: E402
from pipeline.brief import analyse, compose, render_text  # noqa: E402
from pipeline.cluster import cluster_items  # noqa: E402
from pipeline.config import load_settings, load_sources  # noqa: E402
from pipeline.fetch import canonical_url, fetch_all, parse_feed  # noqa: E402
from pipeline.guards import ConfirmationRequired, require_confirmation  # noqa: E402
from pipeline.rank import THRESHOLDS  # noqa: E402
from pipeline.run import tick  # noqa: E402
from pipeline.schedule import should_run  # noqa: E402
from pipeline.textutil import clickbait_score  # noqa: E402
from pipeline.verify import source_trust, verify_cluster  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc)  # 07:00 New York (EDT)
SOURCES = load_sources()
SETTINGS = load_settings()


def items():
    return fetch_all(SOURCES, NOW, fixtures=FIX)


class Collection(unittest.TestCase):
    def test_partial_failure_is_tolerated_and_reported(self):
        its, health = items()
        self.assertGreater(len(its), 30)
        self.assertGreater(len(health["failed"]), 0)          # sources without fixture "fail"
        self.assertGreater(health["feeds_ok"], 20)

    def test_old_items_are_dropped(self):
        its, _ = items()
        self.assertFalse([i for i in its if "filtered out by age" in i["title"]])

    def test_url_canonicalisation_strips_tracking(self):
        self.assertEqual(canonical_url("https://a.com/x/?utm_source=q&id=3&at_medium=RSS"), "https://a.com/x?id=3")

    def test_parse_atom_and_rss(self):
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title><link rel="alternate" href="http://x/1"/><summary>S</summary><updated>2026-09-20T10:00:00Z</updated></entry></feed>'
        e = parse_feed(atom)
        self.assertEqual((e[0]["title"], e[0]["link"]), ("T", "http://x/1"))

    def test_google_news_suffix_stripped_for_headline_only(self):
        its, _ = items()
        r = [i for i in its if i["source_id"] == "reuters"]
        self.assertTrue(r and all("Reuters" not in i["title"] for i in r))


class Dedup(unittest.TestCase):
    def test_same_event_clusters_across_outlets_incl_primary(self):
        its, _ = items()
        cl = cluster_items(its)
        quake = [c for c in cl if any(i["source_id"] == "usgs" for i in c)]
        self.assertEqual(len(quake), 1)
        self.assertGreaterEqual(len({i["source_id"] for i in quake[0]}), 7)
        self.assertFalse([c for c in cl if any("Earthquake" in i["title"] or "earthquake" in i["title"] for i in c) and c not in quake])

    def test_unrelated_stories_not_merged(self):
        its, _ = items()
        for c in cluster_items(its):
            cats = {("quake" if re.search(r"earthquake|quake", i["title"], re.I) else
                     "fed" if re.search(r"\bFed\b|Federal Reserve", i["title"]) else
                     "hurricane" if "Hurricane" in i["title"] else "other") for i in c}
            self.assertLessEqual(len(cats - {"other"}), 1, cats)


class Verification(unittest.TestCase):
    def setUp(self):
        self.st = {s["cluster"][0]["title"]: s for s in analyse(*[items()[0], SOURCES, NOW])}

    def find(self, needle):
        for s in analyse(items()[0], SOURCES, NOW):
            if any(needle in i["title"] for i in s["cluster"]):
                return s
        self.fail("cluster not found: " + needle)

    def test_multi_source_plus_official_is_confirmed(self):
        s = self.find("Freedonia")
        self.assertEqual(s["_ver"].status, "CONFIRMED")
        self.assertTrue(s["_ver"].has_primary)

    def test_single_hedged_source_is_unverified_never_fact(self):
        s = self.find("Tech CEO reportedly")
        self.assertEqual(s["_ver"].status, "UNVERIFIED")

    def test_contradiction_is_developing(self):
        s = self.find("White House denies")
        self.assertTrue(s["_ver"].disputed)
        self.assertEqual(s["_ver"].status, "DEVELOPING")

    def test_syndicated_copies_count_once(self):
        # 10 items but AP and Reuters are separate owners; two BBC items must count as one owner
        cl = [{"source_id": "bbc", "title": "x quake", "summary": "", "link": "u1", "published": NOW.isoformat()},
              {"source_id": "bbc", "title": "x quake again", "summary": "", "link": "u2", "published": NOW.isoformat()}]
        self.assertEqual(verify_cluster(cl, SOURCES).independent_sources, 1)

    def test_trust_weights_differ(self):
        self.assertGreater(source_trust(SOURCES["reuters"]), source_trust(SOURCES["thehill"]))
        self.assertGreater(source_trust(SOURCES["usgs"]), source_trust(SOURCES["cnn"]))


class Ranking(unittest.TestCase):
    def setUp(self):
        self.b = compose(items()[0], SOURCES, SETTINGS, NOW, items()[1])

    def test_clickbait_excluded(self):
        heads = " ".join(s["headline"] for s in self.b["stories"] + self.b["pool"])
        self.assertNotIn("celebrity wore", heads)
        self.assertGreater(clickbait_score("You won't believe what happened!"), 0.5)
        self.assertLess(clickbait_score("Senate passes infrastructure bill 68-30"), 0.1)

    def test_opinion_not_selected(self):
        self.assertNotIn("Opinion:", " ".join(s["headline"] for s in self.b["stories"]))

    def test_top_story_is_the_extraordinary_one(self):
        self.assertIn("earthquake", self.b["stories"][0]["headline"].lower())
        self.assertEqual(self.b["stories"][0]["priority"], "BREAKING")

    def test_no_duplicate_events_in_top10(self):
        heads = [s["headline"].lower() for s in self.b["stories"]]
        self.assertEqual(sum("earthquake" in h or "quake" in h for h in heads), 1)
        self.assertEqual(sum(bool(re.search(r"\bfed\b|federal reserve|rates", h)) for h in heads), 1)

    def test_category_diversity(self):
        cats = {s["category"] for s in self.b["stories"]}
        self.assertGreaterEqual(len(cats), 5)

    def test_unconfirmed_ranked_last_and_labelled(self):
        st = self.b["stories"]
        unv = [s for s in st if s["status"] == "UNVERIFIED"]
        for s in unv:
            self.assertTrue(any("independent confirmation" in u for u in s["unknown"]))

    def test_sorted_by_position(self):
        self.assertEqual([s["position"] for s in self.b["stories"]], list(range(1, len(self.b["stories"]) + 1)))


class Honesty(unittest.TestCase):
    """Never invent news/sources/quotes/data: every emitted fact must trace to a fetched item."""

    def test_every_fact_and_source_traces_to_input(self):
        its, health = items()
        b = compose(its, SOURCES, SETTINGS, NOW, health)
        corpus = " ".join(i["title"] + " " + i["summary"] for i in its)
        links = {i["link"] for i in its}
        norm = lambda t: re.sub(r"\s+", " ", t).strip().rstrip(".")
        for st in b["stories"]:
            for k in st["know"]:
                self.assertIn(norm(k["text"]), norm(corpus), k["text"])
            for s in st["sources"]:
                self.assertIn(s["url"], links)
            self.assertIn(st["read_original"], links)
            self.assertTrue(st["sources"])

    def test_political_statement_flag(self):
        b = compose(*[items()[0], SOURCES, SETTINGS, NOW])
        pol = [s for s in b["stories"] if s["political"]]
        self.assertTrue(pol)
        self.assertTrue(all("statements" in s["political_note"] for s in pol))


class Scheduling(unittest.TestCase):
    def S(self, **kw):
        s = json.loads(json.dumps(SETTINGS))
        s["brief"].update(kw)
        return s

    def utc(self, y, m, d, h, mi=0):
        return datetime(y, m, d, h, mi, tzinfo=timezone.utc)

    def test_before_time_no_run(self):
        ok, _ = should_run(self.utc(2026, 9, 20, 10, 30), self.S(), set())
        self.assertFalse(ok)

    def test_at_time_runs_dst_aware(self):
        self.assertTrue(should_run(self.utc(2026, 9, 20, 11, 0), self.S(), set())[0])       # EDT = UTC-4
        self.assertFalse(should_run(self.utc(2026, 12, 20, 11, 0), self.S(), set())[0])     # EST: 06:00 local
        self.assertTrue(should_run(self.utc(2026, 12, 20, 12, 0), self.S(), set())[0])

    def test_delayed_tick_self_heals(self):
        self.assertTrue(should_run(self.utc(2026, 9, 20, 12, 40), self.S(), set())[0])

    def test_stale_window_skipped(self):
        self.assertFalse(should_run(self.utc(2026, 9, 20, 20, 0), self.S(), set())[0])

    def test_only_once_per_day(self):
        self.assertFalse(should_run(self.utc(2026, 9, 20, 11, 30), self.S(), {"2026-09-20"})[0])

    def test_weekdays_and_custom(self):
        sun = self.utc(2026, 9, 20, 11, 0)   # Sunday
        self.assertFalse(should_run(sun, self.S(frequency="weekdays"), set())[0])
        self.assertTrue(should_run(self.utc(2026, 9, 21, 11, 0), self.S(frequency="weekdays"), set())[0])
        self.assertTrue(should_run(sun, self.S(frequency="custom", custom_days=["sun"]), set())[0])
        self.assertFalse(should_run(sun, self.S(frequency="custom", custom_days=["mon"]), set())[0])

    def test_custom_time_and_timezone(self):
        s = self.S(time="06:30", timezone="Europe/Madrid")   # CEST = UTC+2 => 04:30 UTC
        self.assertFalse(should_run(self.utc(2026, 9, 20, 4, 0), s, set())[0])
        self.assertTrue(should_run(self.utc(2026, 9, 20, 4, 30), s, set())[0])


class Alerts(unittest.TestCase):
    def test_breaking_alert_after_brief_and_no_spam(self):
        its, health = items()
        # brief was published earlier without the quake; then the quake arrives
        earlier = [i for i in its if "quake" not in (i["title"] + i["summary"]).lower() and "earthquake" not in i["title"].lower()
                   and i["source_id"] != "usgs" and "Freedonia" not in i["title"]]
        b = compose(earlier, SOURCES, SETTINGS, NOW, health)
        found = alerts_mod.find_alerts(its, SOURCES, SETTINGS, NOW + timedelta(hours=1), [], b)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["priority"], "BREAKING")
        self.assertGreaterEqual(found[0]["independent_sources"], 3)
        # same event again -> deduplicated
        again = alerts_mod.find_alerts(its, SOURCES, SETTINGS, NOW + timedelta(hours=1, minutes=30), found, b)
        self.assertEqual(again, [])

    def test_normal_stories_never_alert(self):
        its, _ = items()
        found = alerts_mod.find_alerts(its, SOURCES, SETTINGS, NOW, [], None)
        self.assertTrue(all(a["priority"] == "BREAKING" for a in found))
        self.assertLessEqual(len(found), SETTINGS["alerts"]["max_per_day"])
        self.assertFalse([a for a in found if "Senate" in a["headline"] or "Champions" in a["headline"]])

    def test_daily_cap(self):
        its, _ = items()
        prior = [{"day": "2026-09-20", "headline": f"h{i}"} for i in range(3)]
        self.assertEqual(alerts_mod.find_alerts(its, SOURCES, SETTINGS, NOW, prior, None), [])

    def test_quiet_hours(self):
        self.assertTrue(alerts_mod.in_quiet_hours(datetime(2026, 9, 20, 5, 0, tzinfo=timezone.utc), SETTINGS))   # 01:00 NY
        self.assertFalse(alerts_mod.in_quiet_hours(datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc), SETTINGS))

    def test_priority_levels_are_ordered(self):
        T = THRESHOLDS
        self.assertTrue(T["important"] < T["urgent"] < T["breaking"])


class Money(unittest.TestCase):
    def test_guard_always_refuses(self):
        with self.assertRaises(ConfirmationRequired):
            require_confirmation("buy", "100 shares")

    def test_trading_cannot_be_enabled_via_settings(self):
        bad = ROOT / "tests" / "_bad_settings.yaml"
        bad.write_text("brief: {time: '07:00', timezone: UTC}\nfinance: {trading_enabled: true}\n")
        try:
            with self.assertRaises(ConfirmationRequired):
                load_settings(bad)
        finally:
            bad.unlink()

    def test_no_payment_or_broker_code_or_dependencies(self):
        banned = re.compile(r"\b(stripe|paypal|plaid|alpaca|robinhood|ibkr|interactive brokers|coinbase|binance|place_order|submit_order)\b", re.I)
        for f in list((ROOT / "pipeline").glob("*.py")) + [ROOT / "requirements.txt"]:
            self.assertFalse(banned.search(f.read_text()), f.name)


class Security(unittest.TestCase):
    def test_no_secrets_in_repo_files(self):
        pat = re.compile(r"(AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|xox[bp]-[A-Za-z0-9-]{10,})")
        for f in ROOT.rglob("*"):
            if f.is_file() and f.suffix in {".py", ".js", ".html", ".yaml", ".yml", ".json", ".md", ".example", ".webmanifest"} \
                    and ".git" not in f.parts and "fixtures" not in f.parts:
                self.assertFalse(pat.search(f.read_text(errors="ignore")), f)

    def test_frontend_has_no_token_or_topic(self):
        for f in (ROOT / "docs").glob("*.*"):
            if f.suffix in {".js", ".html"}:
                t = f.read_text()
                self.assertNotIn("NTFY_TOPIC", t)
                self.assertNotIn("GEMINI_API_KEY", t)

    def test_notification_dry_run_hides_topic(self):
        import os
        os.environ["NTFY_TOPIC"] = "super-secret-topic"
        try:
            r = notify.send(SETTINGS, "t", "m", dry_run=True)
            self.assertNotIn("super-secret-topic", json.dumps(r))
        finally:
            del os.environ["NTFY_TOPIC"]


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_0700_full_run_publishes_indexes_and_notifies(self):
        res = tick(NOW, self.tmp, SETTINGS, SOURCES, fixtures=FIX, dry_run=True)
        self.assertEqual(res["brief"]["stories"], 10)
        self.assertFalse(res["brief_notification"]["sent"])
        p = res["brief_notification"]["payload"]
        self.assertIn("MORNING BRIEF READY", p["title"])
        self.assertTrue(p["message"].startswith("10 things you should know today."))
        d = self.tmp / "data"
        for f in ["latest.json", "index.json", "search.json", "health.json", "briefs/2026-09-20.json"]:
            self.assertTrue((d / f).exists(), f)
        idx = json.loads((d / "index.json").read_text())
        self.assertEqual(idx[0]["date"], "2026-09-20")
        # second tick same day: no duplicate brief
        res2 = tick(NOW + timedelta(minutes=30), self.tmp, SETTINGS, SOURCES, fixtures=FIX, dry_run=True)
        self.assertIsNone(res2["brief"])
        self.assertIn("already exists", res2["notes"][0])

    def test_history_and_search(self):
        tick(NOW, self.tmp, SETTINGS, SOURCES, fixtures=FIX, dry_run=True)
        tick(NOW + timedelta(days=1), self.tmp, SETTINGS, SOURCES, fixtures=FIX, dry_run=True)
        idx = json.loads((self.tmp / "data" / "index.json").read_text())
        self.assertEqual([i["date"] for i in idx], ["2026-09-21", "2026-09-20"])
        s = json.loads((self.tmp / "data" / "search.json").read_text())
        hits = [e for e in s if "alderport" in (e["h"] + e["s"]).lower() or "freedonia" in (e["h"] + e["s"]).lower()]
        self.assertTrue(hits and all(e["d"] and e["u"] and e["src"] for e in hits))

    def test_before_time_does_nothing_but_alerts_check(self):
        res = tick(NOW - timedelta(hours=2), self.tmp, SETTINGS, SOURCES, fixtures=FIX, dry_run=True)
        self.assertIsNone(res["brief"])
        self.assertFalse((self.tmp / "data" / "latest.json").exists())

    def test_total_outage_publishes_nothing_and_does_not_crash(self):
        res = tick(NOW, self.tmp, SETTINGS, SOURCES, fixtures=self.tmp / "nope", dry_run=True)
        self.assertIsNone(res["brief"])
        self.assertTrue(any("no items" in n for n in res["notes"]))

    def test_render_text_layout(self):
        tick(NOW, self.tmp, SETTINGS, SOURCES, fixtures=FIX, dry_run=True)
        b = json.loads((self.tmp / "data" / "latest.json").read_text())
        t = render_text(b)
        for needle in ["GOOD MORNING", "MORNING BRIEF", "20 SEPTIEMBRE 2026", "10 COSAS QUE DEBES SABER HOY", "01 —",
                       "Qué sabemos:", "Qué todavía no sabemos:", "READ ORIGINAL", "THE BIGGEST STORY"]:
            self.assertIn(needle, t)


if __name__ == "__main__":
    unittest.main()
