import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

load_dotenv()


def connect() -> psycopg.Connection:
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=30, prepare_threshold=None)
    conn.execute("set search_path = sportpredict, public")
    return conn


@contextmanager
def run_log(conn: psycopg.Connection, job: str):
    """Record a `runs` row; mark it failed (and re-raise) on any exception."""
    run_id = conn.execute("insert into runs (job) values (%s) returning id", (job,)).fetchone()["id"]
    conn.commit()
    state = {"credits_used": None, "credits_remaining": None, "notes": {}}
    try:
        yield state
    except BaseException as e:
        conn.rollback()
        conn.execute(
            "update runs set finished_at = now(), status = 'failed', error = %s, "
            "credits_used = %s, credits_remaining = %s, notes = %s where id = %s",
            (f"{type(e).__name__}: {e}"[:2000], state["credits_used"], state["credits_remaining"],
             Jsonb(state["notes"]), run_id),
        )
        conn.commit()
        raise
    conn.execute(
        "update runs set finished_at = now(), status = 'ok', credits_used = %s, "
        "credits_remaining = %s, notes = %s where id = %s",
        (state["credits_used"], state["credits_remaining"], Jsonb(state["notes"]), run_id),
    )
    conn.commit()
