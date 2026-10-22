"""Morning job: grade yesterday, snapshot odds, run every portfolio, write bets.

    python -m sportpredict.jobs.daily
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import config, db, espn, grade
from ..odds_api import OddsAPI, flatten_odds
from ..strategies import baselines, market_ev
from ..strategies.ai_analyst import AIAnalyst
from .common import insert_snapshots, save_decisions, upsert_game


def main() -> None:
    conn = db.connect()
    api = OddsAPI()
    ai = AIAnalyst()
    with db.run_log(conn, "daily") as state:
        notes = state["notes"]
        notes["grading"] = grade.run(conn)

        now = datetime.now(timezone.utc)
        today_et = now.astimezone(ZoneInfo("America/New_York")).date()
        active = api.active_sports()
        notes["games"], notes["bets"] = {}, {}

        for sport_key, league in config.LEAGUES.items():
            if sport_key not in active:
                print(f"[skip] {league} is out of season")
                continue
            end = now + timedelta(hours=config.LOOKAHEAD_HOURS)
            # Free check first, so odds credits are only spent on days the league plays
            if not api.events(sport_key, now, end):
                notes["games"][league] = 0
                print(f"[skip] no {league} games today")
                continue
            events = api.odds(sport_key, config.MORNING_MARKETS, now, end)
            notes["games"][league] = len(events)
            print(f"{league}: {len(events)} games")
            if not events:
                continue
            ctx = espn.league_context(league, today_et)

            for event in events:
                game = upsert_game(conn, event, league)
                rows = flatten_odds(event)
                insert_snapshots(conn, game["id"], "morning", rows)
                decisions = market_ev.decide(game, rows) + baselines.decide(game, rows)
                already = conn.execute(
                    "select 1 from predictions where game_id = %s and strategy = 'ai_analyst' and strategy_version = %s",
                    (game["id"], config.STRATEGY_VERSIONS["ai_analyst"]),
                ).fetchone()
                if not already:
                    decisions += ai.decide(game, rows, ctx)
                placed = save_decisions(conn, game["id"], decisions)
                conn.commit()
                for d in decisions:
                    if d["bet"]:
                        notes["bets"][d["strategy"]] = notes["bets"].get(d["strategy"], 0) + 1
                print(f"  {game['away']} @ {game['home']}: {len(rows)} prices, {placed} bets")

        notes["ai"] = {"calls": ai.calls, "failures": ai.failures, "skipped_out_of_time": ai.skipped,
                       "models": ai.models_used}
        state["credits_used"], state["credits_remaining"] = api.credits_used, api.credits_remaining
        print(f"credits used {api.credits_used}, remaining {api.credits_remaining}; notes: {notes}")

        missed, attempted = ai.failures + ai.skipped, ai.calls + ai.skipped
        if attempted and missed > attempted / 2:
            raise RuntimeError(f"ai_analyst missed {missed} of {attempted} games (Gemini busy or failing)")


if __name__ == "__main__":
    main()
