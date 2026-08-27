"""
Does what the strategy found actually reach the live account?

The question this exists to answer
----------------------------------
Two independent things can go wrong on the live bots, and from the
outside they look identical -- an empty audit database:

1. The strategy genuinely found no setup. Nothing is wrong.
2. The strategy DID find a setup and the live bot never saw it, or saw
   it hours late, because of an MT5 data/clock/lag problem.

Telling those apart by hand means reading the hourly GitHub Actions
summary in one window and querying two SQLite files in another, and it
is exactly the check nobody keeps doing. Measured on 2026-08-26, the
Dukascopy reference produced 5 signals; the conservative bot logged one
of its two (three hours late) and the aggressive bot logged none of its
three. That is the kind of thing this should surface within the hour,
not on the next manual audit.

Why the signal list arrives as a file
-------------------------------------
The reference signals are computed by `check_recent_signals.py` in
GitHub Actions, NOT here. Recomputing them on the VPS would mean a
278MB data download plus a 25-instrument x 2-style backtest sweep on
the same 2 oversubscribed vCPUs the live bots are already struggling
for -- the exact mistake documented in bot/README.md's VPS section.
Instead the workflow publishes a few-KB JSON to the `signal-feed`
branch, and this script reads it via the git remote the VPS checkout
already has working credentials for. No API token, no large download,
no strategy computation on the box.

What counts as "matched"
------------------------
A signal is matched when the corresponding audit database has an
`entry_attempt` row for the same instrument whose timestamp falls
within MATCH_WINDOW of the signal's entry time. Deliberately generous
(default 2h): the point is to distinguish "reached the bot at all"
from "never arrived", and a late row is reported as LATE with its lag
rather than being counted as a miss -- lateness and absence have
different causes and different fixes.

The decision column is not part of matching. A signal that reached the
bot and was declined by the risk manager is a SUCCESS for this check --
the bot saw it. Whether declining was right is a separate question this
script deliberately does not have an opinion about.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone


class FeedUnavailable(Exception):
    """The feed could not be read. Deliberately distinct from "read it and
    found no signals": one means the check did not run, the other means it
    ran and the answer was clean. Conflating them would let a broken
    pipeline masquerade as a healthy quiet hour."""


class FeedNotPublished(FeedUnavailable):
    """Nothing has ever published the feed branch -- the expected state
    before the first workflow run, and worth its own message."""


DEFAULT_REPO = "/srv/slk-bot/mt5data/trading"
DEFAULT_BRANCH = "signal-feed"
DEFAULT_FEED_FILE = "recent-signals.json"
MATCH_WINDOW = timedelta(hours=2)

# Where each style's audit database lives, relative to the repo root.
# Both bots write into the bind-mounted checkout (see
# bot/OPERATIONS_LOG.md's topology section), so these resolve on the
# host and inside the container alike.
AUDIT_DBS = {"conservative": "conservative_audit.db", "aggressive": "aggressive_audit.db"}


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fetch_feed(repo: str, branch: str, feed_file: str) -> dict:
    """The published signal list, read out of the git remote rather than
    the working tree -- so this never disturbs the checkout the live bots
    are importing their code from. `git show` reads the fetched object
    directly; nothing is checked out."""
    # Read back through FETCH_HEAD, NOT `origin/<branch>`. The live
    # checkout's refspec is `+refs/heads/main:refs/remotes/origin/main`
    # -- single-branch -- so fetching any other branch populates
    # FETCH_HEAD and never creates a remote-tracking ref for it.
    # `git show origin/signal-feed:...` therefore fails with "unknown
    # revision" on exactly the machine this runs on, while working fine
    # in a clone that happens to fetch all branches. FETCH_HEAD is
    # written by the fetch immediately above, so it is unambiguous.
    fetch = subprocess.run(["git", "-C", repo, "fetch", "--quiet", "origin", branch],
                           capture_output=True, text=True)
    if fetch.returncode != 0:
        stderr = fetch.stderr or ""
        if "couldn't find remote ref" in stderr or "not found" in stderr:
            # The ordinary first-run state, not a fault: the branch only
            # exists once hourly-signal-check.yml has published to it.
            # Saying so beats relaying git's wording, which reads like a
            # misconfiguration and sends you looking in the wrong place.
            raise FeedNotPublished(
                f"the '{branch}' branch does not exist yet -- nothing has published to it.\n"
                "It is created by the 'Hourly signal check' workflow, which runs after every\n"
                "fetch-data run, or on demand from the Actions tab. Once one has finished,\n"
                "re-run this."
            )
        raise FeedUnavailable(f"git fetch {branch} failed: {stderr.strip() or fetch.returncode}")

    show = subprocess.run(["git", "-C", repo, "show", f"FETCH_HEAD:{feed_file}"],
                          capture_output=True, text=True)
    if show.returncode != 0:
        raise FeedUnavailable(
            f"'{feed_file}' is not present on {branch}: {show.stderr.strip()}")
    return json.loads(show.stdout)


def audit_rows(db_path: str, since: datetime) -> list[dict]:
    """Every entry_attempt at or after `since`. Returns [] for a database
    that doesn't exist yet -- a bot that has never logged anything is a
    normal state on a fresh deployment, not an error to crash on."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT timestamp, instrument, event_type, decision, reason, trade_id "
            "FROM decisions WHERE event_type = 'entry_attempt' AND timestamp >= ? "
            "ORDER BY timestamp",
            (since.isoformat(),),
        )
        return [dict(r) for r in cur]
    finally:
        conn.close()


def reconcile(feed: dict, repo: str, window: timedelta):
    """Pair each published signal with the audit row that answered it.

    Rows are consumed as they're matched so two signals on the same
    instrument in the same window can't both claim the same row --
    otherwise a single late entry would mask a genuine miss right
    beside it."""
    since = _parse_time(feed["since"])
    rows = {style: audit_rows(os.path.join(repo, name), since - window)
            for style, name in AUDIT_DBS.items()}
    used = {style: set() for style in AUDIT_DBS}

    results = []
    for sig in feed["signals"]:
        style, entry = sig["style"], _parse_time(sig["entry_time"])
        best = None
        for idx, row in enumerate(rows.get(style, [])):
            if idx in used[style] or row["instrument"] != sig["instrument"]:
                continue
            lag = _parse_time(row["timestamp"]) - entry
            if abs(lag) <= window and (best is None or abs(lag) < abs(best[1])):
                best = (idx, lag, row)
        if best is None:
            results.append({"signal": sig, "state": "MISSING", "lag": None, "row": None})
        else:
            idx, lag, row = best
            used[style].add(idx)
            late = lag > timedelta(minutes=90)
            results.append({"signal": sig, "state": "LATE" if late else "SEEN",
                            "lag": lag, "row": row})

    # Audit rows with no published signal near them. Not necessarily
    # wrong -- the feed is a rolling window and MT5's candles are not
    # bit-identical to Dukascopy's -- but a persistent pattern here means
    # the bot is trading on something the reference doesn't see.
    unmatched = [row for style in AUDIT_DBS
                 for idx, row in enumerate(rows.get(style, [])) if idx not in used[style]]
    return results, unmatched


def render(feed: dict, results: list, unmatched: list) -> tuple[str, bool]:
    """Returns (report, needs_attention). `needs_attention` drives the
    exit code so cron can stay quiet on a clean run."""
    out = [f"Signal reconciliation -- feed generated {feed['generated_at']}",
           f"window: since {feed['since']}  ({len(feed['signals'])} published signal(s))"]
    if feed.get("errored"):
        out.append(f"NOTE: {len(feed['errored'])} instrument/style combo(s) errored upstream -- "
                   "this check cannot speak for them:")
        for e in feed["errored"][:10]:
            out.append(f"    {e['instrument']} ({e['style']}): {e['error']}")

    missing = [r for r in results if r["state"] == "MISSING"]
    late = [r for r in results if r["state"] == "LATE"]
    seen = [r for r in results if r["state"] == "SEEN"]

    if not results:
        out.append("\nNo signals published in this window -- nothing for the bots to have caught.")
        out.append("An empty audit database is the CORRECT outcome here, not a symptom.")
    else:
        out.append("")
        for r in results:
            s, lag = r["signal"], r["lag"]
            line = (f"  [{r['state']:7}] {s['entry_time']}  {s['instrument']:7} "
                    f"{s['style']:12} {s['direction']:7} {s['trigger_type']}")
            if lag is not None:
                mins = lag.total_seconds() / 60
                line += f"   (bot logged it {mins:+.0f} min later: {r['row']['decision']})"
            out.append(line)
        out.append(f"\n  seen: {len(seen)}   late: {len(late)}   missing: {len(missing)}")

    if unmatched:
        out.append(f"\n{len(unmatched)} audit row(s) with no published signal nearby:")
        for row in unmatched[:10]:
            out.append(f"    {row['timestamp']}  {row['instrument']:7} {row['decision']}  {row['reason']}")

    needs_attention = bool(missing or late)
    if needs_attention:
        out.append("\n>>> Signals the strategy found did not reach the live bots on time.")
        out.append(">>> Check the bots are alive and current: "
                   "docker exec -u abc mt5 pgrep -fa 'bot.run_live'")
    return "\n".join(out), needs_attention


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=DEFAULT_REPO,
                         help=f"Live checkout holding the audit DBs (default: {DEFAULT_REPO})")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--feed-file", default=DEFAULT_FEED_FILE)
    parser.add_argument("--feed-path", default=None,
                         help="Read the feed from a local file instead of the git remote. For testing.")
    parser.add_argument("--window-hours", type=float, default=MATCH_WINDOW.total_seconds() / 3600)
    parser.add_argument("--quiet-when-clean", action="store_true",
                         help="Print nothing when every signal was seen on time. For cron, so a "
                              "healthy hour generates no mail and an unhealthy one does.")
    args = parser.parse_args()

    try:
        feed = (json.load(open(args.feed_path)) if args.feed_path
                else fetch_feed(args.repo, args.branch, args.feed_file))
    except FeedNotPublished as exc:
        print(exc, file=sys.stderr)
        return 3
    except (FeedUnavailable, OSError, json.JSONDecodeError) as exc:
        print(f"could not read the signal feed: {exc}", file=sys.stderr)
        return 2

    results, unmatched = reconcile(feed, args.repo, timedelta(hours=args.window_hours))
    report, needs_attention = render(feed, results, unmatched)
    if needs_attention or not args.quiet_when_clean:
        print(report)
    return 1 if needs_attention else 0


if __name__ == "__main__":
    sys.exit(main())
