"""Write the dashboard's data file.

    python -m sportpredict.jobs.export site/data.json
"""
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from .. import db


def _json(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    raise TypeError(type(v))


def v1_summary(conn) -> dict:
    rows = conn.execute("select version, odds, result from v1_picks where result in ('WIN', 'LOSS')").fetchall()
    out = {"bets": 0, "wins": 0, "units": 0.0}
    for r in rows:
        try:
            o = float(r["odds"])
        except (TypeError, ValueError):
            continue
        out["bets"] += 1
        if r["result"] == "WIN":
            out["wins"] += 1
            out["units"] += o / 100 if o > 0 else 100 / abs(o)
        else:
            out["units"] -= 1
    out["units"] = round(out["units"], 2)
    out["roi"] = round(out["units"] / out["bets"], 4) if out["bets"] else None
    out["period"] = "Nov 24, 2025 - Jan 10, 2026"
    return out


def build(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": q("select * from v_portfolio_summary order by strategy"),
        "daily_units": q("select * from v_daily_units order by day"),
        "today": q("select * from v_bets_detail where result = 'pending' order by commence_time, matchup, strategy"),
        "recent": q("select * from v_bets_detail where result <> 'pending' order by commence_time desc, id desc limit 150"),
        "ai_vs_market": q("select * from v_ai_vs_market"),
        "ai_reads": q(
            "select g.league, g.away || ' @ ' || g.home as matchup, g.home, g.commence_time, "
            "round(p.prob, 4) as ai_prob, round(p.fair_prob, 4) as market_prob, "
            "p.details ->> 'summary' as summary, p.details -> 'factors' as factors, "
            "p.details ->> 'confidence' as confidence "
            "from predictions p join games g on g.id = p.game_id "
            "where p.strategy = 'ai_analyst' and p.outcome = g.home and not g.completed "
            "and g.commence_time > now() - interval '6 hours' order by g.commence_time"),
        "runs": q("select * from v_runs_recent"),
        "v1": v1_summary(conn),
    }


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "site/data.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(db.connect()), default=_json, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
