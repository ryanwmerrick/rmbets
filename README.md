# RMBets (sportPredictLLM v2)

A paper-betting experiment on NBA, NHL and NFL games. It asks one question: **does an AI analyst add anything beyond what the betting market already knows?**

Four portfolios bet the same games at the same flat stake (shown as $10 on the dashboard), always using real prices from The Odds API:

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
| `daily.yml` | 14:00 UTC | Grades finished games from ESPN's scoreboard, snapshots odds for leagues playing that day, runs every portfolio, publishes the dashboard |
| `snapshot.yml` | 21:30 UTC daily, 16:15 UTC Sundays | Moneyline snapshot near game time for CLV, then publishes the dashboard |
| `grade.yml` | Every 30 min, 1pm-2:30am ET | Grades finished games from ESPN (no odds credits) and republishes when anything changed |
| `pages.yml` | Push to `web/` | Republishes the dashboard |

- **Database:** Neon Postgres, schema `sportpredict` (`db/001_init.sql`).
- **Dashboard:** a static page in `web/` that reads `data.json`, which `sportpredict.jobs.export` writes on every run. Hosted on GitHub Pages.
- **Secrets** (repo settings and `.env`): `DATABASE_URL`, `ODDS_API_KEY`, `GEMINI_API_KEY`.

## Local use

```bash
pip install -r requirements.txt
pytest -q tests
python -m sportpredict.jobs.daily      # ~3 Odds API credits per league with games that day
python -m sportpredict.jobs.export site/data.json && cp web/* site/ && python -m http.server -d site
```

## Odds API credits

The free tier gives 500 credits a month. Grading uses ESPN (free), and a free events check skips leagues with no games, so odds are only bought on game days: about 3 credits per league per game day, plus 1 per league for each CLV snapshot. NBA + NHL + NFL comes to roughly 300 a month.

## Rules

- Prices always come from the odds feed; the AI only gives a probability.
- Every prompt, response and cited fact is stored in `predictions`.
- Jobs fail loudly: errors turn the Action red and are logged in `runs`.
- Thresholds, prompts and models live in `sportpredict/config.py`. Give each setup 300 graded bets before judging it.

