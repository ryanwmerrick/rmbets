"""Pull final scores from ESPN's free scoreboard and grade pending bets."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, espn
from .fair import profit_units

ET = ZoneInfo("America/New_York")


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


def match_final(home: str, away: str, board: list[dict]) -> tuple[int, int] | None:
    """Final (home_score, away_score) for our game from an ESPN scoreboard, matched by team nicknames.

    Matches regardless of which side ESPN lists as home (neutral-site games), and
    returns scores in our home/away order. None if the game isn't final yet.
    """
    hk, ak = espn.team_key(home), espn.team_key(away)
    for g in board:
        if not g["completed"]:
            continue
        scores = {espn.team_key(side["name"]): side["score"] for side in espn.sides(g)}
        if set(scores) == {hk, ak} and None not in scores.values():
            return scores[hk], scores[ak]
    return None


def update_scores(conn) -> int:
    pending = conn.execute(
        "select id, league, home, away, commence_time from games where not completed "
        "and commence_time < now() and commence_time > now() - make_interval(days => %s)",
        (config.VOID_AFTER_DAYS + 1,),
    ).fetchall()
    boards: dict[tuple, list[dict]] = {}
    by_day = defaultdict(list)
    for g in pending:
        by_day[(g["league"], g["commence_time"].astimezone(ET).date())].append(g)
    updated = 0
    for (league, day), games in by_day.items():
        if (league, day) not in boards:
            boards[(league, day)] = espn.scoreboard(league, day)
        for g in games:
            final = match_final(g["home"], g["away"], boards[(league, day)])
            if final:
                conn.execute(
                    "update games set home_score = %s, away_score = %s, completed = true, updated_at = now() "
                    "where id = %s", (final[0], final[1], g["id"]),
                )
                updated += 1
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


def run(conn) -> dict:
    return {"games_completed": update_scores(conn), "graded": grade_pending(conn)}
