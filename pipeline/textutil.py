"""Text helpers: cleaning, tokenising, sentence splitting, clickbait and hedge detection."""
from __future__ import annotations

import html
import re
import unicodedata

STOP = set("""a an the and or but if of to in on at by for with from as is are was were be been being it its this that
these those he she they them his her their our we you your i not no yes new says say said after before over under
about into out up down amid more most less than then also just how why what when where who whom will would could
should may might can has have had do does did vs via per year years day days week today tonight latest live update
updates report reports reported reportedly news video watch photos""".split())

CLICKBAIT_PATTERNS = [
    r"you won'?t believe", r"shocking", r"jaw[- ]dropping", r"this is why", r"here'?s why", r"what happens next",
    r"\bslams?\b", r"\bdestroys?\b", r"\bobliterates?\b", r"\bblasts?\b", r"\beviscerates?\b", r"\bgoes viral\b",
    r"\bgoes off\b", r"\bmeltdown\b", r"\bepic\b", r"\bunbelievable\b", r"\bmind[- ]blowing\b", r"\bwatch:",
    r"\bthe internet is\b", r"\bhilarious\b", r"\bstuns?\b", r"\bbombshell\b", r"\bexplodes?\b(?! in)", r"\bwhat we know\b(?=.*\?)",
    r"\bnobody (is )?talking about\b", r"\bviral\b", r"\btrolls?\b", r"\bfans (react|erupt)\b",
]
_CB = [re.compile(p, re.I) for p in CLICKBAIT_PATTERNS]

HEDGE = re.compile(
    r"\b(reportedly|allegedly|alleged|unconfirmed|claims?|claimed|purportedly|rumou?rs?|sources? (say|said|familiar)|"
    r"according to (an? )?(anonymous|unnamed)|apparently|is said to|may have|could have|suspected|speculat\w+)\b", re.I)
DISPUTE = re.compile(
    r"\b(denies|denied|disputes?|disputed|refutes?|rejects?|false claim|debunk\w*|contradicts?|misleading|"
    r"no evidence|retract\w*|walks? back|conflicting)\b", re.I)
CONFIRM = re.compile(r"\b(confirms?|confirmed|announces?|announced|officials? said|authorities said|according to (the )?"
                     r"(government|ministry|agency|court|police|department|white house|pentagon))\b", re.I)


NOISE = re.compile(
    r"(^about\s|company announcement|press release|^obituar|\betf\b|\(\w{2,5}\.(n|o|oq|l)\)|sponsored|^watch\b|podcast|"
    r"\bquiz\b|newsletter|crossword|horoscope|\bbest deals?\b|\bpromo code\b|\bstock (pick|alert)s?\b|\bprice target\b|"
    r"\bmarket (size|research)\b|\bcookie\b|^today's (wordle|nyt)|^the (morning|evening) (briefing|newsletter))", re.I)
EXPLAINER = re.compile(r"^(why|how|what|inside|the (right|case|problem|truth)|can|is|are|should|do|does)\b", re.I)


def is_noise(title: str) -> bool:
    return bool(NOISE.search(title)) or len(title.split()) < 3       # bare topic-page titles ("Artificial intelligence")


def is_explainer(title: str) -> bool:
    return bool(EXPLAINER.search(title.strip())) or title.strip().endswith("?")


def clean_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_source_suffix(title: str) -> str:
    """Google News titles end with ' - Outlet'. Remove it."""
    title = re.sub(r"\s+[-–—|]\s+[\w-]+(\.[\w-]+)*\.(com|org|net|gov|co\.uk)$", "", title.strip())
    return re.sub(r"\s+[-–—|]\s+[A-Z][\w .&'’]+$", "", title).strip()


# tiny synonym map so differently-worded reports of one event can match
SYN = {"quake": "earthquake", "temblor": "earthquake", "lowers": "cut", "lowered": "cut", "lower": "cut", "cuts": "cut",
       "reduces": "cut", "reduced": "cut", "slashes": "cut", "dead": "kill", "deaths": "kill", "death": "kill", "died": "kill",
       "dies": "kill", "killed": "kill", "kills": "kill", "toll": "kill", "federal": "fed", "reserve": "fed", "fomc": "fed",
       "rates": "rate", "hikes": "hike", "raises": "hike", "lawmakers": "senate", "beat": "win", "defeat": "win", "defeats": "win",
       "wins": "win", "clinch": "win", "outage": "outage", "outages": "outage", "sues": "lawsuit", "sued": "lawsuit"}


def norm_tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = re.findall(r"[a-z0-9][a-z0-9'-]*", text)
    out = []
    for w in words:
        w = w.strip("'-")
        if len(w) < 3 and not w.isdigit():
            continue
        if w in STOP:
            continue
        # light stemming
        for suf in ("'s", "ing", "ed", "es", "s"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(SYN.get(w, w))
    return out


def sentences(text: str) -> list[str]:
    text = clean_html(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'])", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def clickbait_score(title: str) -> float:
    """0 = sober, 1 = pure bait."""
    score = 0.0
    for rx in _CB:
        if rx.search(title):
            score += 0.35
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6 and len(letters) > 12:
        score += 0.3
    if title.count("!") >= 1:
        score += 0.25
    if title.strip().endswith("?"):
        score += 0.1
    if re.search(r"^\d+ (things|reasons|ways|times)", title, re.I):
        score += 0.3
    return min(score, 1.0)


def has_hedge(text: str) -> bool:
    return bool(HEDGE.search(text))


def has_dispute(text: str) -> bool:
    return bool(DISPUTE.search(text))


def has_confirm(text: str) -> bool:
    return bool(CONFIRM.search(text))


def truncate_sentences(text: str, max_sentences: int = 4, max_chars: int = 620) -> str:
    out, total = [], 0
    for s in sentences(text):
        if total + len(s) > max_chars and out:
            break
        out.append(s)
        total += len(s) + 1
        if len(out) >= max_sentences:
            break
    return " ".join(out)
