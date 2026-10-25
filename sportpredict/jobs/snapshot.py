"""Evening job: moneyline snapshot near game time, used to score CLV.

    python -m sportpredict.jobs.snapshot
"""
from datetime import datetime, timedelta, timezone

from .. import config, db
from ..fair import fair_lines, key_of
from ..odds_api import OddsAPI, flatten_odds
from .common import insert_snapshots

API_KEY_FOR = {league: key for key, league in config.LEAGUES.items()}


def main() -> None:
    conn = db.connect()
    if db.already_ran(conn, "snapshot", "now() - interval '3 hours'"):
        print("[skip] a snapshot already ran in the last 3 hours (set FORCE=1 to run again)")
        return
    api = OddsAPI()
    with db.run_log(conn, "snapshot") as state:
        now = datetime.now(timezone.utc)
        # Only spend credits on leagues where we hold moneyline bets on games not yet started
        leagues = [r["league"] for r in conn.execute(
            "select distinct g.league from bets b join games g on g.id = b.game_id "
            "where b.result = 'pending' and b.market = 'h2h' and g.commence_time > now()").fetchall()]
        updated = 0
        for league in leagues:
            events = api.odds(API_KEY_FOR[league], config.EVENING_MARKETS, now,
                              now + timedelta(hours=config.LOOKAHEAD_HOURS))
            for event in events:
                known = conn.execute("select 1 from games where id = %s", (event["id"],)).fetchone()
                if not known:
                    continue
                rows = flatten_odds(event)
                insert_snapshots(conn, event["id"], "evening", rows)
                fair = fair_lines(rows)
                for b in conn.execute(
                    "select id, market, outcome, point, price_decimal from bets "
                    "where game_id = %s and market = 'h2h' and result = 'pending'", (event["id"],)
                ).fetchall():
                    k = key_of(b)
                    if k in fair:
                        p = fair[k][0]
                        conn.execute("update bets set close_fair_prob = %s, clv = %s where id = %s",
                                     (round(p, 5), round(float(b["price_decimal"]) * p - 1, 5), b["id"]))
                        updated += 1
            conn.commit()
        state["notes"] = {"leagues": leagues, "bets_with_clv": updated}
        state["credits_used"], state["credits_remaining"] = api.credits_used, api.credits_remaining
        print(f"CLV set on {updated} bets; credits used {api.credits_used}, remaining {api.credits_remaining}")


if __name__ == "__main__":
    main()
