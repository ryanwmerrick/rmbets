"""Odds math: de-vig, fair lines, EV, CLV, profit. No AI anywhere in here."""
from collections import defaultdict
from statistics import median

from . import config


def american_to_decimal(price: int) -> float:
    price = int(price)
    if price > 0:
        return round(1 + price / 100, 6)
    return round(1 + 100 / abs(price), 6)


def devig(decimals: list[float]) -> list[float]:
    """Remove the bookmaker margin proportionally: p_i = (1/d_i) / sum(1/d_j)."""
    implied = [1 / d for d in decimals]
    total = sum(implied)
    return [p / total for p in implied]


def ev(prob: float, decimal_price: float) -> float:
    return prob * decimal_price - 1


def profit_units(result: str, decimal_price: float, stake: float = 1.0) -> float:
    if result == "win":
        return round(stake * (decimal_price - 1), 4)
    if result == "loss":
        return -stake
    return 0.0


def key_of(row: dict) -> tuple:
    """Identify one side of one line: (market, outcome, point)."""
    point = row.get("point")
    return (row["market"], row["outcome"], None if point is None else float(point))


def _book_pairs(rows: list[dict]) -> dict[str, list[tuple[tuple, float]]]:
    """Per book, the de-vigged probability of each side of each two-way line.

    Two outcomes belong to the same line when they share a market and the same
    absolute point (spreads: -3.5 / +3.5, totals: Over 220.5 / Under 220.5).
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        point = r.get("point")
        line = None if point is None else abs(float(point))
        groups[(r["book"], r["market"], line)].append(r)

    by_book: dict[str, list[tuple[tuple, float]]] = defaultdict(list)
    for (book, _market, _line), sides in groups.items():
        if len(sides) != 2:
            continue
        probs = devig([float(s["price_decimal"]) for s in sides])
        for s, p in zip(sides, probs):
            by_book[book].append((key_of(s), p))
    return by_book


def fair_lines(rows: list[dict]) -> dict[tuple, tuple[float, str]]:
    """Fair probability for every side we can price: {key: (prob, source)}.

    Pinnacle's de-vigged line wins. For sides Pinnacle doesn't quote, fall back
    to the median de-vigged probability across books (needs MIN_CONSENSUS_BOOKS).
    """
    by_book = _book_pairs(rows)
    fair: dict[tuple, tuple[float, str]] = {}
    for key, p in by_book.get(config.SHARP_BOOK, []):
        fair[key] = (p, "pinnacle")

    pooled: dict[tuple, list[float]] = defaultdict(list)
    for book, sides in by_book.items():
        if book == config.SHARP_BOOK:
            continue
        for key, p in sides:
            pooled[key].append(p)
    for key, ps in pooled.items():
        if key not in fair and len(ps) >= config.MIN_CONSENSUS_BOOKS:
            fair[key] = (median(ps), "consensus")
    return fair


def best_prices(rows: list[dict]) -> dict[tuple, dict]:
    """Best US-book price for every side: {key: row}."""
    best: dict[tuple, dict] = {}
    for r in rows:
        if r["book"] not in config.US_BOOKS:
            continue
        k = key_of(r)
        if k not in best or float(r["price_decimal"]) > float(best[k]["price_decimal"]):
            best[k] = r
    return best
