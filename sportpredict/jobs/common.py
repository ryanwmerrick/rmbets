from datetime import datetime

from psycopg.types.json import Jsonb


def upsert_game(conn, event: dict, league: str) -> dict:
    game = {
        "id": event["id"],
        "league": league,
        "home": event["home_team"],
        "away": event["away_team"],
        "commence_time": datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00")),
    }
    conn.execute(
        "insert into games (id, league, home, away, commence_time) values (%(id)s, %(league)s, %(home)s, %(away)s, "
        "%(commence_time)s) on conflict (id) do update set commence_time = excluded.commence_time, updated_at = now()",
        game,
    )
    return game


def insert_snapshots(conn, game_id: str, kind: str, rows: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "insert into odds_snapshots (game_id, kind, book, market, outcome, point, price_american, price_decimal) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            [(game_id, kind, r["book"], r["market"], r["outcome"], r["point"], r["price_american"],
              r["price_decimal"]) for r in rows],
        )


def save_decisions(conn, game_id: str, decisions: list[dict]) -> int:
    """Insert predictions (and bets). Re-runs on the same day are no-ops."""
    bets = 0
    for d in decisions:
        row = conn.execute(
            "insert into predictions (strategy, strategy_version, game_id, market, outcome, point, prob, fair_prob, "
            "fair_source, model, prompt, raw_response, details) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s) on conflict do nothing returning id",
            (d["strategy"], d["strategy_version"], game_id, d["market"], d["outcome"], d["point"], d["prob"],
             d["fair_prob"], d["fair_source"], d.get("model"), d.get("prompt"), d.get("raw_response"),
             Jsonb(d["details"]) if d.get("details") else None),
        ).fetchone()
        if row is None or d["bet"] is None:
            continue
        b = d["bet"]
        cur = conn.execute(
            "insert into bets (prediction_id, strategy, strategy_version, game_id, market, outcome, point, book, "
            "price_american, price_decimal, ev) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "on conflict do nothing",
            (row["id"], d["strategy"], d["strategy_version"], game_id, d["market"], d["outcome"], d["point"],
             b["book"], b["price_american"], b["price_decimal"], b["ev"]),
        )
        bets += cur.rowcount
    return bets
