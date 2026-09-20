"""Generates SYNTHETIC RSS fixtures for offline tests. Events/places are fictional ("Freedonia"); this is test data,
never real news. Run: python tests/make_fixtures.py"""
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc)  # 07:00 in New York


def h(hours_ago):
    return format_datetime(NOW - timedelta(hours=hours_ago))


# source_id -> list of (title, desc, link, hours_ago, category)
S = {
 "bbc": [
  ("Freedonia earthquake: more than 100 killed as rescue teams search rubble", "A magnitude 7.2 earthquake struck the coast of Freedonia early on Sunday. Officials said at least 120 people were killed and hundreds are missing. Rescue teams are searching collapsed buildings in the port city of Alderport.", "https://www.bbc.example/news/world-fd-quake?at_medium=RSS", 2, "world"),
  ("Central bank cuts interest rates by quarter point", "The Federal Reserve lowered its benchmark rate by 0.25 percentage points on Saturday, citing a cooling labour market. Inflation remains above target.", "https://www.bbc.example/news/business-rates", 5, "economy"),
  ("Cloud provider outage disrupts thousands of websites", "A major cloud provider suffered a multi-hour outage affecting banking apps and retailers. The company said it was investigating the cause.", "https://www.bbc.example/news/tech-outage", 6, "technology"),
  ("WHO reports measles outbreak spreading across three regions", "The World Health Organization said 4,200 cases of measles were confirmed this month and urged vaccination campaigns.", "https://www.bbc.example/news/health-measles", 8, "health"),
  ("Champions League final: City beat Inter 2-1 in extra time", "Manchester City won the Champions League final 2-1 after extra time in Istanbul.", "https://www.bbc.example/sport/cl-final", 9, "world"),
  ("Old story that should be filtered out by age", "This item is 60 hours old.", "https://www.bbc.example/news/old", 60, "world"),
 ],
 "npr": [
  ("Earthquake in Freedonia kills at least 120, officials say", "Rescuers are digging through rubble in Alderport after a 7.2 magnitude quake. The government has declared a state of emergency.", "https://www.npr.example/2026/09/20/fd-quake", 2.5, "world"),
  ("Senate passes bipartisan infrastructure bill 68-30", "The Senate passed a bipartisan infrastructure package on Saturday. The bill now goes to the House, where its prospects are uncertain.", "https://www.npr.example/2026/09/20/senate-bill", 7, "general"),
  ("Fed cuts rates for first time this year", "The Federal Reserve announced a quarter-point cut, saying labor market risks had increased.", "https://www.npr.example/2026/09/20/fed-cut", 5, "economy"),
 ],
 "guardian": [
  ("Freedonia quake death toll passes 100 as aid arrives", "International aid began arriving in Freedonia after Sunday's earthquake, which the US Geological Survey measured at magnitude 7.2.", "https://www.guardian.example/world/2026/sep/20/freedonia-quake", 3, "world"),
  ("Hurricane Marta strengthens to category 4, heads for Gulf coast", "The US National Hurricane Center said Marta could make landfall on Tuesday. Evacuation orders are expected for coastal counties.", "https://www.guardian.example/us-news/2026/sep/20/hurricane-marta", 4, "climate"),
  ("Champions League: City clinch title in extra-time thriller", "Manchester City beat Inter 2-1 in Istanbul.", "https://www.guardian.example/sport/2026/sep/20/city-inter", 9, "sport"),
  ("Outage at cloud giant knocks out banks and shops", "Customers reported failures for around five hours.", "https://www.guardian.example/technology/2026/sep/20/cloud-outage", 6, "technology"),
  ("Opinion: Why the rate cut is a mistake", "An opinion column.", "https://www.guardian.example/commentisfree/2026/sep/20/rate-cut-opinion", 5, "economy"),
 ],
 "nyt": [
  ("Deadly Earthquake Hits Freedonia, Killing Over 100", "A powerful earthquake struck Freedonia's coast, killing at least 120 people, according to government officials.", "https://www.nytimes.example/2026/09/20/world/freedonia-earthquake.html", 2, "world"),
  ("Fed Lowers Rates, Citing Softer Job Market", "The Federal Reserve cut interest rates by a quarter point, its first reduction of the year.", "https://www.nytimes.example/2026/09/20/business/fed-cut.html", 5, "economy"),
  ("Senate Passes Infrastructure Bill After Weeks of Talks", "The 68-30 vote sends the measure to the House.", "https://www.nytimes.example/2026/09/20/us/senate-infrastructure.html", 7, "usa"),
  ("Study Finds New Drug Slows Early Alzheimer's Progression", "Researchers reported in a peer-reviewed trial of 1,800 patients that the drug slowed cognitive decline by 27 percent over 18 months. Experts cautioned that side effects remain a concern.", "https://www.nytimes.example/2026/09/20/health/alzheimers-drug.html", 10, "health"),
 ],
 "cnn": [
  ("You won't believe what this celebrity wore to the red carpet!", "Fans erupt over shocking dress.", "https://www.cnn.example/style/red-carpet", 3, "general"),
  ("Freedonia earthquake: at least 120 dead", "The quake struck at 3 a.m. local time.", "https://www.cnn.example/world/freedonia-quake", 2.2, "world"),
  ("Tech CEO reportedly planning to step down, sources say", "Sources familiar with the matter say the chief executive of Nimbus Corp may be preparing to resign. The company did not comment.", "https://www.cnn.example/business/nimbus-ceo", 1, "general"),
 ],
 "thehill": [
  ("Senate passes infrastructure bill in 68-30 vote", "The bill heads to the House.", "https://thehill.example/policy/infrastructure-vote", 6.5, "politics"),
  ("Senator claims election rules change is unconstitutional, White House denies", "Sen. Doe claimed the new rules violate the constitution; the White House denied the claim and called it misleading.", "https://thehill.example/policy/election-rules-dispute", 3, "politics"),
 ],
 "politico": [
  ("White House denies Senator's claim on election rules", "The White House rejected the senator's assertion, saying the rules were reviewed by counsel. Doe stood by the claim.", "https://politico.example/news/2026/09/20/election-rules", 3, "politics"),
 ],
 "cnbc": [
  ("Fed cuts rates by 25 basis points; stocks rally", "U.S. stocks rallied after the Federal Reserve announced a quarter point cut. The S&P 500 rose 1.4%.", "https://www.cnbc.example/2026/09/20/fed-cut-stocks.html", 5, "economy"),
  ("Cloud outage: what businesses lost", "A cloud outage hit online retailers for hours.", "https://www.cnbc.example/2026/09/20/cloud-outage.html", 6, "technology"),
 ],
 "wsj": [
  ("Fed Cuts Rates as Labor Market Cools", "The Fed lowered rates a quarter point, signalling caution on further cuts.", "https://www.wsj.example/economy/fed-cut", 5, "economy"),
 ],
 "cbs": [
  ("Hurricane Marta grows to Category 4; Gulf Coast braces", "Forecasters warned of life-threatening storm surge along the Gulf Coast.", "https://www.cbsnews.example/news/hurricane-marta", 4, "general"),
  ("Senate approves infrastructure package", "The Senate voted 68-30.", "https://www.cbsnews.example/news/senate-infrastructure", 7, "general"),
 ],
 "abc": [
  ("Hurricane Marta: evacuation orders issued for Gulf counties", "Officials ordered evacuations in coastal counties ahead of the storm.", "https://abcnews.example/US/hurricane-marta-evacuations", 3, "general"),
 ],
 "nbc": [
  ("Earthquake devastates Freedonia coast; rescue efforts underway", "More than 100 people are confirmed dead.", "https://www.nbcnews.example/world/freedonia-earthquake", 2.4, "general"),
 ],
 "aljazeera": [
  ("Freedonia earthquake: rescuers race to find survivors in Alderport", "Rescue workers were digging through collapsed buildings on Sunday.", "https://www.aljazeera.example/news/2026/9/20/freedonia-quake", 2.1, "world"),
  ("Film festival awards top prize to debut director", "The jury awarded the top prize to a first-time director for a drama set in a fishing village.", "https://www.aljazeera.example/culture/film-festival-prize", 12, "world"),
 ],
 "who": [
  ("WHO: Measles cases rising in three regions, vaccination gaps to blame", "WHO said confirmed measles cases reached 4,200 this month and called for catch-up immunization.", "https://www.who.example/news/measles-update", 8.5, "health"),
 ],
 "fed": [
  ("Federal Reserve issues FOMC statement", "The Committee decided to lower the target range for the federal funds rate by 1/4 percentage point.", "https://www.federalreserve.example/newsevents/pressreleases/monetary20260920a.htm", 5.2, "economy"),
 ],
 "nature": [
  ("Phase 3 trial: antibody therapy slows early Alzheimer's decline", "Nature published results of a randomized trial in 1,800 participants showing a 27% slowing of cognitive decline over 18 months.", "https://www.nature.example/articles/d41586-026-alz", 11, "science"),
 ],
 "reuters": [  # Google News style: titles carry ' - Reuters' suffix, no description
  ("Freedonia quake kills more than 100, rescuers search rubble - Reuters", "", "https://news.google.example/rss/articles/CBMi_reuters_fd", 2.3, "general"),
  ("Fed cuts rates by 25 bps, flags labor market risks - Reuters", "", "https://news.google.example/rss/articles/CBMi_reuters_fed", 5.1, "economy"),
 ],
 "ap": [
  ("Powerful earthquake kills at least 120 in Freedonia - AP News", "", "https://news.google.example/rss/articles/CBMi_ap_fd", 2.6, "general"),
 ],
}


def rss(items):
    body = "".join(
        f"<item><title>{escape(t)}</title><link>{escape(l)}</link><description>{escape(d)}</description><pubDate>{h(a)}</pubDate></item>"
        for t, d, l, a, c in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>fixture</title>{body}</channel></rss>'


def main():
    OUT.mkdir(exist_ok=True)
    for sid, items in S.items():
        (OUT / f"{sid}.xml").write_text(rss(items), encoding="utf-8")
    usgs = {"features": [{"properties": {"mag": 7.2, "place": "45 km W of Alderport, Freedonia", "time": int((NOW - timedelta(hours=2.7)).timestamp() * 1000),
                                         "url": "https://earthquake.usgs.example/earthquakes/eventpage/fd7000abc", "tsunami": 1, "alert": "red"}}]}
    (OUT / "usgs.xml").write_text(json.dumps(usgs), encoding="utf-8")
    print("fixtures written:", len(S) + 1)


if __name__ == "__main__":
    main()
