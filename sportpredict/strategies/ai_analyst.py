"""AI analyst: Gemini adjusts the market's fair probability using real ESPN facts.

The model never sees or writes a price. It returns a home-win probability,
which code clamps to within AI_MAX_SHIFT of the market, then code does the EV
math against real prices. Every game's probability is stored, bet or not.
"""
import os
import time
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from .. import config
from ..espn import team_key
from ..fair import best_prices, ev, fair_lines
from . import decision

NAME = "ai_analyst"


class Factor(BaseModel):
    factor: str = Field(description="One concrete fact from the input and how it affects the game")
    source: Literal["espn_injuries", "espn_records", "espn_schedule", "market"]


class AIView(BaseModel):
    home_win_prob: float = Field(description="Probability the home team wins, 0 to 1")
    confidence: Literal["low", "medium", "high"]
    factors: list[Factor]
    summary: str = Field(description="One or two sentences explaining the adjustment")


PROMPT = """You are a careful sports analyst estimating one {league} game: {away} (away) at {home} (home), starting {start}.

The betting market's fair, vig-free probability that {home} wins is {p_home:.1%}. Betting markets are usually accurate, so start from that number. Move away from it only for concrete facts below that the market may not fully reflect, such as a key player ruled out very recently, or a back-to-back. If nothing stands out, return the market probability unchanged. Your answer must stay between {lo:.1%} and {hi:.1%}.

Use ONLY the facts below. You have no other information about today, so do not rely on memory of rosters or recent results.

{home} record: {home_record}. Played yesterday: {home_b2b}.
{home} injury report:
{home_injuries}

{away} record: {away_record}. Played yesterday: {away_b2b}.
{away} injury report:
{away_injuries}

Return home_win_prob, your confidence, the factors you used (each with its source), and a short summary."""


def _fmt_injuries(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines[:15]) or "- none listed"


class AIAnalyst:
    def __init__(self):
        self.client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_SECONDS * 1000),
        )
        self.calls = 0
        self.failures = 0
        self.skipped = 0
        self.models_used: dict[str, int] = {}
        self._started = time.monotonic()
        self._last_call = 0.0

    def _ask(self, prompt: str) -> tuple[AIView, str, str]:
        """Try each model in turn; busy (429/5xx), timed-out or unparseable answers move on."""
        last_error = None
        for round_ in range(config.GEMINI_MAX_ROUNDS):
            for model in config.GEMINI_MODELS:
                wait = config.GEMINI_SECONDS_BETWEEN_CALLS - (time.monotonic() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                self._last_call = time.monotonic()
                try:
                    r = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=AIView,
                        ),
                    )
                    if isinstance(r.parsed, AIView):
                        return r.parsed, r.text, model
                    last_error = ValueError(f"{model}: unparseable response: {(r.text or '')[:200]}")
                except errors.APIError as e:
                    if e.code not in (408, 429) and (e.code or 0) < 500:
                        raise
                    last_error = e
                except Exception as e:  # timeouts and connection errors
                    last_error = e
            time.sleep(20 * (round_ + 1))
        raise last_error

    def out_of_time(self) -> bool:
        return time.monotonic() - self._started > config.AI_TIME_BUDGET_SECONDS

    def decide(self, game: dict, rows: list[dict], ctx: dict) -> list[dict]:
        fair = fair_lines(rows)
        best = best_prices(rows)
        home_key, away_key = ("h2h", game["home"], None), ("h2h", game["away"], None)
        if home_key not in fair or away_key not in fair:
            return []
        p_home, source = fair[home_key]
        lo, hi = max(0.01, p_home - config.AI_MAX_SHIFT), min(0.99, p_home + config.AI_MAX_SHIFT)

        hk, ak = team_key(game["home"]), team_key(game["away"])
        prompt = PROMPT.format(
            league=ctx["league"], home=game["home"], away=game["away"],
            start=game["commence_time"].strftime("%Y-%m-%d %H:%M UTC"),
            p_home=p_home, lo=lo, hi=hi,
            home_record=ctx["records"].get(hk) or "unknown", away_record=ctx["records"].get(ak) or "unknown",
            home_b2b="yes" if hk in ctx["played_yesterday"] else "no",
            away_b2b="yes" if ak in ctx["played_yesterday"] else "no",
            home_injuries=_fmt_injuries(ctx["injuries"].get(hk, [])),
            away_injuries=_fmt_injuries(ctx["injuries"].get(ak, [])),
        )

        if self.out_of_time():
            self.skipped += 1
            return []
        self.calls += 1
        try:
            view, raw, model = self._ask(prompt)
        except Exception as e:  # recorded by the job; too many failures fail the run
            self.failures += 1
            print(f"  [ai_analyst] {game['away']} @ {game['home']}: {type(e).__name__}: {str(e)[:200]}")
            return []
        self.models_used[model] = self.models_used.get(model, 0) + 1

        q_home = min(hi, max(lo, float(view.home_win_prob)))
        details = {
            "factors": [f.model_dump() for f in view.factors],
            "summary": view.summary,
            "confidence": view.confidence,
            "raw_prob": view.home_win_prob,
            "sources": ctx["sources"],
        }
        extra = {"model": model, "prompt": prompt, "raw_response": raw, "details": details}

        sides = [(home_key, q_home, p_home), (away_key, 1 - q_home, fair[away_key][0])]
        priced = [(ev(q, float(best[k]["price_decimal"])), k, q, fp) for k, q, fp in sides if k in best]
        top = max(priced, key=lambda s: s[0]) if priced else None

        out = []
        for k, q, fp in sides:
            bet_here = top is not None and top[1] == k and top[0] >= config.AI_EV_MIN
            out.append(decision(NAME, k, round(q, 5), fp, source,
                                best[k] if bet_here else None, round(top[0], 5) if bet_here else None, **extra))
        return out
