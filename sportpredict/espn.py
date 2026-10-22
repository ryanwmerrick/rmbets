"""Free ESPN public feeds: injuries, records, and who played yesterday.

These give the AI analyst real, current facts instead of its training memory.
"""
import re
import unicodedata
from datetime import date, timedelta

import requests

from . import config

BASE = "https://site.api.espn.com/apis/site/v2/sports"


def team_key(name: str) -> str:
    """Match team names across sources by nickname ("LA Clippers" == "Los Angeles Clippers")."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", s).split()[-1]


def injuries_url(league: str) -> str:
    return f"https://www.espn.com/{league.lower()}/injuries"


def _get(path: str, **params) -> dict:
    r = requests.get(f"{BASE}/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def injuries(league: str) -> dict[str, list[str]]:
    data = _get(f"{config.ESPN_PATHS[league]}/injuries")
    out: dict[str, list[str]] = {}
    for team in data.get("injuries", []):
        lines = []
        for i in team.get("injuries", []):
            athlete = i.get("athlete", {})
            pos = athlete.get("position", {}).get("abbreviation", "")
            comment = (i.get("shortComment") or "").strip()
            lines.append(f"{athlete.get('displayName', '?')} ({pos}) - {i.get('status', '?')}: {comment[:160]}")
        out[team_key(team["displayName"])] = lines
    return out


def scoreboard(league: str, day: date) -> list[dict]:
    """Games on one US date: {"home": {...}, "away": {...}, "completed": bool}.

    Each side has name, record and score (None until the game has one).
    """
    data = _get(f"{config.ESPN_PATHS[league]}/scoreboard", dates=day.strftime("%Y%m%d"))
    games = []
    for event in data.get("events", []):
        comp = event["competitions"][0]
        game = {"completed": bool(comp["status"]["type"].get("completed"))}
        for c in comp["competitors"]:
            records = c.get("records") or []
            score = c.get("score")
            game[c["homeAway"]] = {
                "name": c["team"]["displayName"],
                "record": records[0].get("summary") if records else None,
                "score": int(score) if score not in (None, "") else None,
            }
        games.append(game)
    return games


def sides(game: dict) -> tuple[dict, dict]:
    return game["home"], game["away"]


def teams(league: str, today: date) -> dict[str, dict]:
    """Display info per team for the dashboard: short name, abbreviation, logos, today's record."""
    data = _get(f"{config.ESPN_PATHS[league]}/teams")
    records = {}
    for g in scoreboard(league, today):
        for side in sides(g):
            records[team_key(side["name"])] = side["record"]
    out = {}
    for entry in data["sports"][0]["leagues"][0]["teams"]:
        t = entry["team"]
        logos = {tuple(l.get("rel", [])): l["href"] for l in t.get("logos", [])}
        key = team_key(t["displayName"])
        out[key] = {
            "abbr": t["abbreviation"],
            "short": t.get("shortDisplayName") or t["displayName"],
            "logo": logos.get(("full", "default")),
            "logo_dark": logos.get(("full", "dark")),
            "record": records.get(key),
        }
    return out


def league_context(league: str, today: date) -> dict:
    """Everything the AI analyst gets for one league, fetched once per run."""
    records = {}
    for g in scoreboard(league, today):
        for side in sides(g):
            records[team_key(side["name"])] = side["record"]
    played_yesterday = {
        team_key(side["name"]) for g in scoreboard(league, today - timedelta(days=1)) for side in sides(g)
    }
    return {
        "league": league,
        "injuries": injuries(league),
        "records": records,
        "played_yesterday": played_yesterday,
        "sources": [injuries_url(league), f"https://www.espn.com/{league.lower()}/scoreboard"],
    }
