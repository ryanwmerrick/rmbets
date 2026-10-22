"""Control groups: always the favorite, and a seeded coin flip. Moneyline only."""
import random

from ..fair import best_prices, ev, fair_lines
from . import decision


def _h2h(game, rows):
    fair = fair_lines(rows)
    best = best_prices(rows)
    sides = []
    for team in (game["home"], game["away"]):
        key = ("h2h", team, None)
        if key in fair and key in best:
            sides.append((key, fair[key][0], fair[key][1], best[key]))
    return sides if len(sides) == 2 else []


def decide(game: dict, rows: list[dict]) -> list[dict]:
    sides = _h2h(game, rows)
    if not sides:
        return []
    out = []

    key, p, src, b = max(sides, key=lambda s: s[1])
    out.append(decision("baseline_fav", key, p, p, src, b, round(ev(p, float(b["price_decimal"])), 5)))

    key, p, src, b = random.Random(game["id"]).choice(sides)
    out.append(decision("baseline_random", key, p, p, src, b, round(ev(p, float(b["price_decimal"])), 5)))
    return out
