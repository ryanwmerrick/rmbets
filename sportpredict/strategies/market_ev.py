"""Line shopping: bet the best US-book price when it beats the fair line."""
from .. import config
from ..fair import best_prices, ev, fair_lines
from . import decision

NAME = "market_ev"


def decide(game: dict, rows: list[dict]) -> list[dict]:
    fair = fair_lines(rows)
    best = best_prices(rows)
    out = []
    for market in config.MORNING_MARKETS:
        candidates = []
        for key, (p, source) in fair.items():
            if key[0] != market or key not in best:
                continue
            candidates.append((ev(p, float(best[key]["price_decimal"])), key, p, source))
        if not candidates:
            continue
        top_ev, key, p, source = max(candidates, key=lambda c: c[0])
        if top_ev >= config.MARKET_EV_MIN:
            out.append(decision(NAME, key, p, p, source, best[key], round(top_ev, 5)))
    return out
