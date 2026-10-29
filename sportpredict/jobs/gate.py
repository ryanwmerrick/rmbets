"""Wait until a job's target time, so GitHub's late-starting schedules still run on time.

    python -m sportpredict.jobs.gate daily
    python -m sportpredict.jobs.gate snapshot

GitHub starts scheduled workflows anywhere from minutes to ~6 hours late. Each job
is therefore scheduled many times overnight; whichever attempt starts first sleeps
here until the target time (up to MAX_WAIT), then lets the job run. Attempts that
start too early exit, and attempts that start after the job is done skip it.

Sets the GitHub step output `go=true` when the job should run now.
"""
import os
import sys
import time
from datetime import datetime, time as clock, timedelta
from zoneinfo import ZoneInfo

from .. import db

ET = ZoneInfo("America/New_York")
MAX_WAIT = timedelta(hours=5)  # GitHub jobs are capped at 6 hours

# Target times (ET) per job; Sundays add a noon snapshot before the 1pm NFL games
TARGETS = {
    "daily": lambda day: [clock(8, 30)],
    "snapshot": lambda day: ([clock(12, 30)] if day.weekday() == 6 else []) + [clock(16, 45)],
}
# How late a target may still be run, and how far back a previous run counts as "done"
LATE_OK = {"daily": timedelta(hours=12), "snapshot": timedelta(hours=3)}
DONE_SINCE = {"daily": lambda target: target.replace(hour=0, minute=0),
              "snapshot": lambda target: target - timedelta(hours=3)}


def decide(job: str, now: datetime, done_since) -> tuple[bool, float]:
    """Return (go, seconds_to_wait) for the next target that isn't done yet."""
    for t in TARGETS[job](now.date()):
        target = datetime.combine(now.date(), t, ET)
        if done_since(DONE_SINCE[job](target)):
            continue
        if now > target + LATE_OK[job]:
            continue
        wait = (target - now).total_seconds()
        if wait > MAX_WAIT.total_seconds():
            return False, 0  # too early; a later attempt will handle it
        return True, max(0.0, wait)
    return False, 0


def main() -> None:
    job = sys.argv[1]
    conn = db.connect()
    done = lambda since: conn.execute(  # noqa: E731
        "select 1 from runs where job = %s and status = 'ok' and started_at >= %s limit 1", (job, since)
    ).fetchone() is not None
    go, wait = decide(job, datetime.now(ET), done)
    conn.close()  # don't hold a database connection while sleeping
    if go and wait:
        print(f"[gate] {job}: waiting {wait / 60:.0f} min until the target time")
        time.sleep(wait)
    print(f"[gate] {job}: {'run now' if go else 'nothing to do now'}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"go={'true' if go else 'false'}\n")


if __name__ == "__main__":
    main()
