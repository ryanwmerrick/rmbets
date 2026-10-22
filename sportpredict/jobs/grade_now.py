"""Results job: grade any games that have finished. Uses ESPN only, no odds credits.

    python -m sportpredict.jobs.grade_now

In GitHub Actions it sets the step output `changed=true` when a game was graded,
so the dashboard is only republished when something actually changed.
"""
import os

from .. import db, grade


def main() -> None:
    conn = db.connect()
    with db.run_log(conn, "grade") as state:
        result = grade.run(conn)
        state["notes"] = result
        print(f"grading: {result}")
    changed = result["games_completed"] > 0
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == "__main__":
    main()
