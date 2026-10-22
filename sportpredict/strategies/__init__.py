"""Each strategy turns one game's odds into decisions.

A decision is a dict with the prediction fields (market, outcome, point, prob,
fair_prob, fair_source, ...) and `bet`: None, or the book/price/EV to bet.
"""
from .. import config


def decision(strategy, key, prob, fair_prob, fair_source, best_row=None, ev=None, **extra):
    market, outcome, point = key
    bet = None
    if best_row is not None:
        bet = {
            "book": best_row["book"],
            "price_american": best_row["price_american"],
            "price_decimal": float(best_row["price_decimal"]),
            "ev": ev,
        }
    return {
        "strategy": strategy,
        "strategy_version": config.STRATEGY_VERSIONS[strategy],
        "market": market,
        "outcome": outcome,
        "point": point,
        "prob": prob,
        "fair_prob": fair_prob,
        "fair_source": fair_source,
        "bet": bet,
        **extra,
    }
