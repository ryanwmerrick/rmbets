# sportPredictLLM v2

A paper-betting experiment on NBA and NHL games. It asks one question: **does an AI analyst add anything beyond what the betting market already knows?**

Four portfolios bet the same games at flat 1-unit stakes, always using real prices from The Odds API:

| Portfolio | What it does |
| --- | --- |
| `market_ev` | Line shopping: bets the best US-book price when its EV against Pinnacle's de-vigged fair line is at least 2.5%. No AI. |
| `ai_analyst` | Gemini Flash adjusts the market's fair moneyline probability (by 5 points at most) using ESPN injury reports, records and back-to-backs. Code computes EV and bets when it's at least 3%. |
| `baseline_fav` | Control: always bets the moneyline favorite. |
| `baseline_random` | Control: bets a seeded coin-flip side. |

Results are scored on ROI, closing line value (CLV), and for the AI, a Brier score against the market's own probabilities.

## How it runs

| Workflow | When | What |
| --- | --- | --- |
| `daily.yml` | 15:00 UTC | Grades finished games, snapshots odds, runs every portfolio, publishes the dashboard |
| `snapshot.yml` | 23:00 UTC | Moneyline snapshot near game time for CLV, then publishes the dashboard |
| `pages.yml` | Push to `web/` | Republishes the dashboard |

- **Database:** Neon Postgres, schema `sportpredict` (`db/001_init.sql`). v1's `public.pick` table is untouched and exposed through the `v1_picks` view.
- **Dashboard:** a static page in `web/` that reads `data.json`, which `sportpredict.jobs.export` writes on every run. Hosted on GitHub Pages.
- **Secrets** (repo settings and `.env`): `DATABASE_URL`, `ODDS_API_KEY`, `GEMINI_API_KEY`.

## Local use

```bash
pip install -r requirements.txt
pytest -q tests
python -m sportpredict.jobs.daily      # uses ~6-12 Odds API credits
python -m sportpredict.jobs.export site/data.json && cp web/* site/ && python -m http.server -d site
```

## Rules

- Prices always come from the odds feed; the AI only gives a probability.
- Every prompt, response and cited fact is stored in `predictions`.
- Jobs fail loudly: errors turn the Action red and are logged in `runs`.
- Thresholds, prompts and models are versioned in `sportpredict/config.py`. Each version runs for 300 graded bets before anyone judges it.

v1 (Nov 2025 - Jan 2026) lives in `legacy/`. It went 105-136, -33 units (-13.7% ROI).
