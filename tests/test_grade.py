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


from sportpredict.grade import match_final


def side(name, score):
    return {"name": name, "record": None, "score": score}


def test_match_final_by_nickname_and_neutral_site():
    board = [
        {"completed": True, "home": side("LA Clippers", 101), "away": side("Utah Jazz", 99)},
        # ESPN lists the teams the other way around from our feed (neutral site)
        {"completed": True, "home": side("Montreal Canadiens", 2), "away": side("St. Louis Blues", 5)},
        {"completed": False, "home": side("Boston Bruins", 2), "away": side("Nashville Predators", 0)},
    ]
    assert match_final("Los Angeles Clippers", "Utah Jazz", board) == (101, 99)
    assert match_final("St Louis Blues", "Montréal Canadiens", board) == (5, 2)
    assert match_final("Boston Bruins", "Nashville Predators", board) is None
    assert match_final("Denver Nuggets", "Oklahoma City Thunder", board) is None
