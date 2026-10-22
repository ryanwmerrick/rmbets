-- sportPredictLLM v2 schema (Neon Postgres).
-- Everything lives in the `sportpredict` schema; v1's `public.pick` table is
-- left untouched.

create schema if not exists sportpredict;
set search_path = sportpredict;

create table if not exists games (
  id            text primary key,            -- The Odds API event id
  league        text not null,               -- NBA | NHL
  home          text not null,
  away          text not null,
  commence_time timestamptz not null,
  home_score    int,
  away_score    int,
  completed     boolean not null default false,
  updated_at    timestamptz not null default now()
);

create table if not exists odds_snapshots (
  id             bigserial primary key,
  game_id        text not null references games(id),
  captured_at    timestamptz not null default now(),
  kind           text not null check (kind in ('morning', 'evening')),
  book           text not null,
  market         text not null check (market in ('h2h', 'spreads', 'totals')),
  outcome        text not null,              -- team name, or Over / Under
  point          numeric,                    -- spread or total line
  price_american int not null,
  price_decimal  numeric not null
);
create index if not exists odds_snapshots_game_kind on odds_snapshots (game_id, kind);

-- One row per strategy x game x market outcome the strategy has an opinion on,
-- whether or not it bets. ai_analyst stores its probability for every game here.
create table if not exists predictions (
  id               bigserial primary key,
  created_at       timestamptz not null default now(),
  strategy         text not null,
  strategy_version text not null,
  game_id          text not null references games(id),
  market           text not null,
  outcome          text not null,
  point            numeric,
  prob             numeric not null,         -- strategy's win probability
  fair_prob        numeric,                  -- market's de-vigged probability
  fair_source      text,                     -- pinnacle | consensus
  model            text,                     -- LLM model id, ai_analyst only
  prompt           text,
  raw_response     text,
  details          jsonb,                    -- factors, sources, context
  unique (strategy, strategy_version, game_id, market, outcome)
);

create table if not exists bets (
  id               bigserial primary key,
  prediction_id    bigint references predictions(id),
  created_at       timestamptz not null default now(),
  strategy         text not null,
  strategy_version text not null,
  game_id          text not null references games(id),
  market           text not null,
  outcome          text not null,
  point            numeric,
  book             text not null,
  price_american   int not null,
  price_decimal    numeric not null,
  ev               numeric,                  -- expected value at bet time, e.g. 0.031
  stake_units      numeric not null default 1,
  close_fair_prob  numeric,                  -- fair prob at the evening snapshot
  clv              numeric,                  -- price_decimal * close_fair_prob - 1
  result           text not null default 'pending'
                   check (result in ('pending', 'win', 'loss', 'push', 'void')),
  profit_units     numeric,
  graded_at        timestamptz,
  unique (strategy, strategy_version, game_id, market)
);
create index if not exists bets_result on bets (result);

create table if not exists runs (
  id                bigserial primary key,
  job               text not null,
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  status            text not null default 'running' check (status in ('running', 'ok', 'failed')),
  credits_used      int,
  credits_remaining int,
  notes             jsonb,
  error             text
);

drop view if exists v1_picks;


-- Dashboard views (exported to JSON by the jobs).

create or replace view v_portfolio_summary as
select strategy,
       strategy_version,
       count(*) filter (where result in ('win', 'loss'))                 as decided,
       count(*) filter (where result = 'win')                            as wins,
       count(*) filter (where result = 'loss')                           as losses,
       count(*) filter (where result in ('push', 'void'))                as pushes,
       count(*) filter (where result = 'pending')                        as pending,
       round(coalesce(sum(profit_units), 0), 2)                          as units,
       round(sum(profit_units) / nullif(count(*) filter (where result <> 'pending'), 0), 4) as roi,
       round(avg(clv), 4)                                                as avg_clv,
       count(clv)                                                        as clv_bets
from bets
group by strategy, strategy_version;

create or replace view v_daily_units as
select b.strategy,
       (g.commence_time at time zone 'America/New_York')::date as day,
       round(sum(b.profit_units), 2)                           as units,
       round(sum(sum(b.profit_units)) over (partition by b.strategy
             order by (g.commence_time at time zone 'America/New_York')::date), 2) as cumulative_units
from bets b
join games g on g.id = b.game_id
where b.result <> 'pending'
group by b.strategy, day;

create or replace view v_bets_detail as
select b.id, b.strategy, b.strategy_version, g.league,
       g.away || ' @ ' || g.home as matchup,
       g.commence_time, b.market, b.outcome, b.point, b.book,
       b.price_american, round(b.ev, 4) as ev, round(b.clv, 4) as clv,
       b.result, b.profit_units,
       g.away_score, g.home_score,
       p.details -> 'factors' as factors
from bets b
join games g on g.id = b.game_id
left join predictions p on p.id = b.prediction_id;

-- AI vs market accuracy on every completed game the AI scored (bet or not).
create or replace view v_ai_vs_market as
select p.strategy_version,
       count(*)                                                      as games,
       round(avg(power(p.prob - o.won, 2)), 4)                       as ai_brier,
       round(avg(power(p.fair_prob - o.won, 2)), 4)                  as market_brier
from predictions p
join games g on g.id = p.game_id and g.completed
cross join lateral (
  select case when (p.outcome = g.home and g.home_score > g.away_score)
               or (p.outcome = g.away and g.away_score > g.home_score)
              then 1.0 else 0.0 end as won
) o
where p.strategy = 'ai_analyst' and p.market = 'h2h' and p.outcome = g.home and p.fair_prob is not null
group by p.strategy_version;

create or replace view v_runs_recent as
select job, started_at, finished_at, status, credits_used, credits_remaining, error
from runs
order by started_at desc
limit 30;

