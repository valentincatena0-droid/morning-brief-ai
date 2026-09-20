# MORNING BRIEF AI — Architecture decision record

## Constraints (in priority order)
stability · automation · security · maintainability · iPhone + Android · ~$0 cost · room to scale.

## Decision

```
GitHub Actions (cron, every 30 min)
   └─ python -m pipeline.run tick
        1. schedule gate  (is it past brief_time in my timezone, and no brief yet today?)
        2. fetch  ─ ~45 RSS/API feeds in parallel, per-source fallback, health report
        3. dedupe + cluster related stories
        4. verify ─ independent-source corroboration, official-source check, contradiction/hedge detection
        5. rank   ─ internal importance score, anti-clickbait, category diversity → TOP 10 (+ pool of 25)
        6. compose brief JSON (facts / unknowns / sources)
        7. write docs/data/*.json  (+ history index + search index)
        8. notify via ntfy.sh  (☀️ brief ready / 🚨 breaking)
        9. git commit → GitHub Pages redeploys
   └─ every tick also runs the BREAKING check (separate alert state, rate limited)

GitHub Pages (HTTPS, free)  →  docs/  = static PWA (vanilla JS, no build step)
ntfy.sh (free) + ntfy app   →  reliable push on iPhone and Android
```

### Why not the alternatives

| Option | Verdict |
|---|---|
| Native iOS/Android app | Needs Apple Developer account (paid, $99/yr) and store review. Rejected on cost + maintenance. |
| Next.js/React + Vercel + Supabase | Adds a build chain, a DB and a server for something that is a daily static document. More things to break, no benefit. |
| Serverless functions + DB | Free tiers exist but need accounts/keys and cold-start/timeout limits; the pipeline is a batch job, not a request/response service. |
| **Static PWA + Actions batch job** | Zero servers, zero cost, HTTPS by default, git history = free versioned archive of every brief, installable on iPhone/Android. **Chosen.** |

### Push notifications
iOS Web Push works only for installed PWAs (iOS 16.4+) and requires a server holding subscriptions (VAPID + storage) — a paid-tier-shaped problem for a static site and historically flaky.
**ntfy.sh** is free, has native iOS and Android apps with proper APNs/FCM delivery, and needs one HTTP POST. Tapping a notification opens the PWA (`Click` header). Web Push can be added later without changing the pipeline (see README "Roadmap").
The ntfy topic is a secret (GitHub Actions secret); it is never in the frontend.

### Scheduling
GitHub cron is best-effort (delays of 5–30 min are normal) and UTC-only. So the workflow ticks every 30 min and the *gate* decides:
"local time ≥ brief_time AND frequency allows today AND no brief exists for today". This is self-healing: a delayed or skipped tick is caught by the next one, and DST is handled by `zoneinfo`.

### News acquisition (legit only)
1. Official RSS feeds (BBC, NPR, Guardian, NYT, Al Jazeera, CNBC, CBS, ABC, NBC, CNN, Politico, The Hill, WSJ, WaPo…).
2. Google News RSS with `site:` filter for outlets without public RSS (Reuters, AP, Bloomberg, FT) — headline + link only, no scraping.
3. Primary sources: USGS (earthquake API), WHO, UN News, NASA, Federal Reserve, SEC, ECB, BLS, Nature, Science.
No paywall bypassing, no HTML scraping of blocked sites. A failing feed is skipped and reported in `health`.

### Summaries without inventing anything
Default mode is **extractive**: text comes from the sources' own leads, attributed by outlet. Nothing is generated that isn't in a source. An optional LLM step (Gemini free tier, `GEMINI_API_KEY`) can add EXPLAIN / translation, under a grounded prompt; it is off by default and its output is labelled ANALYSIS, separate from FACTS.

### Personalisation
The pipeline emits a ranked pool; interests re-order it **client-side** with a bounded boost, and any story flagged `must_know` (very high importance) is always kept. Reading behaviour is stored only on-device and only nudges, never filters.

### Money rule
The system is read-only with respect to money: no broker/bank/payment integration exists, and `pipeline/guards.py` raises `ConfirmationRequired` for anything monetary. Nothing in the repo can spend, buy, sell or transfer.
