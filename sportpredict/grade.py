"""Pull final scores (matched by The Odds API game id) and grade pending bets."""
from datetime import datetime, timedelta, timezone

from . import config
from .fair import profit_units

API_KEY_FOR = {league: key for key, league in config.LEAGUES.items()}


def grade_bet(market: str, outcome: str, point, home: str, away: str, hs: int, as_: int) -> str:
    if market == "h2h":
        if hs == as_:
            return "push"
        winner = home if hs > as_ else away
        return "win" if outcome == winner else "loss"
    if market == "spreads":
        mine, theirs = (hs, as_) if outcome == home else (as_, hs)
        margin = mine + float(point) - theirs
    elif market == "totals":
        total = hs + as_
        margin = total - float(point) if outcome == "Over" else float(point) - total
    else:
        raise ValueError(f"unknown market {market}")
    return "win" if margin > 0 else "loss" if margin < 0 else "push"


def update_scores(conn, api) -> int:
    leagues = [r["league"] for r in conn.execute(
        "select distinct league from games where not completed and commence_time < now()").fetchall()]
    updated = 0
    for league in leagues:
        for g in api.scores(API_KEY_FOR[league]):
            if not g.get("completed") or not g.get("scores"):
                continue
            scores = {s["name"]: int(s["score"]) for s in g["scores"]}
            cur = conn.execute(
                "update games set home_score = %s, away_score = %s, completed = true, updated_at = now() "
                "where id = %s and not completed",
                (scores.get(g["home_team"]), scores.get(g["away_team"]), g["id"]),
            )
            updated += cur.rowcount
    conn.commit()
    return updated


def grade_pending(conn) -> dict:
    counts = {"win": 0, "loss": 0, "push": 0, "void": 0}
    pending = conn.execute(
        "select b.id, b.market, b.outcome, b.point, b.price_decimal, b.stake_units, "
        "g.home, g.away, g.home_score, g.away_score, g.completed, g.commence_time "
        "from bets b join games g on g.id = b.game_id where b.result = 'pending'"
    ).fetchall()
    void_before = datetime.now(timezone.utc) - timedelta(days=config.VOID_AFTER_DAYS)
    for b in pending:
        if b["completed"] and b["home_score"] is not None:
            result = grade_bet(b["market"], b["outcome"], b["point"], b["home"], b["away"],
                               b["home_score"], b["away_score"])
        elif b["commence_time"] < void_before:
            result = "void"
        else:
            continue
        conn.execute(
            "update bets set result = %s, profit_units = %s, graded_at = now() where id = %s",
            (result, profit_units(result, float(b["price_decimal"]), float(b["stake_units"])), b["id"]),
        )
        counts[result] += 1
    conn.commit()
    return counts


def run(conn, api) -> dict:
    return {"games_completed": update_scores(conn, api), "graded": grade_pending(conn)}
