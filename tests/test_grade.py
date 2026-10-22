from sportpredict.grade import grade_bet

H, A = "Boston Celtics", "New York Knicks"


def test_moneyline():
    assert grade_bet("h2h", H, None, H, A, 110, 100) == "win"
    assert grade_bet("h2h", A, None, H, A, 110, 100) == "loss"


def test_spreads():
    assert grade_bet("spreads", H, -3.5, H, A, 110, 100) == "win"
    assert grade_bet("spreads", H, -10.5, H, A, 110, 100) == "loss"
    assert grade_bet("spreads", A, 10.0, H, A, 110, 100) == "push"
    assert grade_bet("spreads", A, 12.5, H, A, 110, 100) == "win"


def test_totals():
    assert grade_bet("totals", "Over", 205.5, H, A, 110, 100) == "win"
    assert grade_bet("totals", "Under", 205.5, H, A, 110, 100) == "loss"
    assert grade_bet("totals", "Under", 210, H, A, 110, 100) == "push"
