"""Write the dashboard's data file.

    python -m sportpredict.jobs.export site/data.json
"""
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from zoneinfo import ZoneInfo

from .. import config, db, espn


def _json(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    raise TypeError(type(v))


def build(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": q("select * from v_portfolio_summary order by strategy"),
        "daily_units": q("select * from v_daily_units order by day"),
        "today": q("select * from v_bets_detail where result = 'pending' order by commence_time, matchup, strategy"),
        # Up to 200 settled bets per portfolio, newest first
        "settled": q(
            "select * from (select *, row_number() over (partition by strategy "
            "order by commence_time desc, id desc) as rn from v_bets_detail where result <> 'pending') t "
            "where rn <= 200 order by commence_time desc, id desc"),
        "ai_vs_market": q("select * from v_ai_vs_market"),
        "ai_reads": q(
            "select g.league, g.away || ' @ ' || g.home as matchup, g.home, g.commence_time, "
            "round(p.prob, 4) as ai_prob, round(p.fair_prob, 4) as market_prob, "
            "p.details ->> 'summary' as summary, p.details -> 'factors' as factors, "
            "p.details ->> 'confidence' as confidence "
            "from predictions p join games g on g.id = p.game_id "
            "where p.strategy = 'ai_analyst' and p.outcome = g.home and not g.completed "
            "and g.commence_time > now() - interval '6 hours' order by g.commence_time"),
    }


def team_info(leagues: set[str]) -> dict:
    """Logos and records for the dashboard. Cosmetic, so an ESPN outage only drops logos."""
    today = datetime.now(ZoneInfo("America/New_York")).date()
    out = {}
    for league in sorted(leagues):
        try:
            out[league] = espn.teams(league, today)
        except Exception as e:
            print(f"[warn] ESPN team info for {league} unavailable: {e}")
    return out


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "site/data.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build(db.connect())
    data["teams"] = team_info({r["league"] for r in data["today"] + data["ai_reads"]} or set(config.LEAGUES.values()))
    out.write_text(json.dumps(data, default=_json, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
