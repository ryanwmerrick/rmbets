import pytest

from sportpredict import fair


def row(book, market, outcome, price, point=None):
    return {"book": book, "market": market, "outcome": outcome, "point": point,
            "price_american": price, "price_decimal": fair.american_to_decimal(price)}


def test_american_to_decimal():
    assert fair.american_to_decimal(-110) == pytest.approx(1.909091, abs=1e-6)
    assert fair.american_to_decimal(150) == 2.5
    assert fair.american_to_decimal(100) == 2.0


def test_devig_removes_margin():
    probs = fair.devig([1.909091, 1.909091])
    assert probs == pytest.approx([0.5, 0.5])
    assert sum(fair.devig([1.5, 2.8])) == pytest.approx(1.0)


def test_ev_and_profit():
    assert fair.ev(0.5, 2.1) == pytest.approx(0.05)
    assert fair.profit_units("win", 2.5) == 1.5
    assert fair.profit_units("loss", 2.5) == -1
    assert fair.profit_units("push", 2.5) == 0


def test_fair_lines_prefers_pinnacle_and_pairs_spreads():
    rows = [
        row("pinnacle", "h2h", "Celtics", -150), row("pinnacle", "h2h", "Knicks", 140),
        row("pinnacle", "spreads", "Celtics", -105, -3.5), row("pinnacle", "spreads", "Knicks", -105, 3.5),
        row("draftkings", "h2h", "Celtics", -160), row("draftkings", "h2h", "Knicks", 135),
    ]
    f = fair.fair_lines(rows)
    p_cel, src = f[("h2h", "Celtics", None)]
    assert src == "pinnacle"
    assert p_cel + f[("h2h", "Knicks", None)][0] == pytest.approx(1.0)
    assert f[("spreads", "Celtics", -3.5)][0] == pytest.approx(0.5)


def test_consensus_needs_enough_books():
    two_books = [row(b, "totals", side, -110, 220.5) for b in ("fanduel", "betmgm") for side in ("Over", "Under")]
    assert fair.fair_lines(two_books) == {}
    three = two_books + [row("draftkings", "totals", s, -110, 220.5) for s in ("Over", "Under")]
    assert fair.fair_lines(three)[("totals", "Over", 220.5)] == (pytest.approx(0.5), "consensus")


def test_best_prices_ignores_pinnacle():
    rows = [row("pinnacle", "h2h", "Knicks", 150), row("fanduel", "h2h", "Knicks", 140),
            row("draftkings", "h2h", "Knicks", 145)]
    assert fair.best_prices(rows)[("h2h", "Knicks", None)]["book"] == "draftkings"
