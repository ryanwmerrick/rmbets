import os
from datetime import datetime, timezone

import requests

from . import config

BASE = "https://api.the-odds-api.com/v4"


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OddsAPI:
    """Thin client that tracks credits from the response headers."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ["ODDS_API_KEY"]
        self.credits_used = 0
        self.credits_remaining: int | None = None

    def _get(self, path: str, **params) -> list[dict]:
        r = requests.get(f"{BASE}{path}", params={"apiKey": self.api_key, **params}, timeout=30)
        if "x-requests-last" in r.headers:
            self.credits_used += int(float(r.headers["x-requests-last"]))
        if "x-requests-remaining" in r.headers:
            self.credits_remaining = int(float(r.headers["x-requests-remaining"]))
        if r.status_code != 200:
            raise RuntimeError(f"Odds API {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def active_sports(self) -> set[str]:
        """Sports currently in season (this endpoint costs no credits)."""
        return {s["key"] for s in self._get("/sports") if s.get("active")}

    def odds(self, sport_key: str, markets: list[str], start: datetime, end: datetime) -> list[dict]:
        return self._get(
            f"/sports/{sport_key}/odds",
            bookmakers=",".join([config.SHARP_BOOK] + config.US_BOOKS),
            markets=",".join(markets),
            oddsFormat="american",
            commenceTimeFrom=iso_z(start),
            commenceTimeTo=iso_z(end),
        )

    def events(self, sport_key: str, start: datetime, end: datetime) -> list[dict]:
        """Games scheduled in the window (this endpoint costs no credits)."""
        return self._get(f"/sports/{sport_key}/events", commenceTimeFrom=iso_z(start), commenceTimeTo=iso_z(end))


def flatten_odds(event: dict) -> list[dict]:
    """One row per book x market x outcome, ready for odds_snapshots."""
    from .fair import american_to_decimal

    rows = []
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            for o in market.get("outcomes", []):
                price = int(o["price"])
                rows.append({
                    "book": book["key"],
                    "market": market["key"],
                    "outcome": o["name"],
                    "point": o.get("point"),
                    "price_american": price,
                    "price_decimal": american_to_decimal(price),
                })
    return rows
