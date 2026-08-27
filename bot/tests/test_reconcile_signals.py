"""
The two failure modes that matter here are opposite and equally bad: a
false alarm trains you to ignore it, and a false all-clear is the exact
blindness the script exists to remove. Both directions are tested.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from .. import reconcile_signals as rs


def T(hour, minute=0, day=26):
    return datetime(2026, 8, day, hour, minute, tzinfo=timezone.utc)


def signal(instrument, style, when, direction="bullish", trigger="engulfing"):
    return {"instrument": instrument, "style": style, "entry_time": when.isoformat(),
            "direction": direction, "entry_price": 1.1, "stop_loss": 1.09,
            "primary_target": 1.13, "trigger_type": trigger, "entry_pattern": "direct_mitigation"}


def feed(signals, since=None, errored=None):
    return {"generated_at": T(22).isoformat(), "since": (since or T(12)).isoformat(),
            "instruments": ["EURCAD", "USDCHF"], "styles": ["conservative", "aggressive"],
            "signals": signals, "errored": errored or []}


@pytest.fixture
def repo(tmp_path):
    """A checkout with both audit databases, schema-shaped like the real
    ones (see bot/audit_log.py)."""
    for name in rs.AUDIT_DBS.values():
        conn = sqlite3.connect(tmp_path / name)
        conn.execute("CREATE TABLE decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "timestamp TEXT, instrument TEXT, event_type TEXT, decision TEXT, "
                     "reason TEXT, trade_id TEXT)")
        conn.commit()
        conn.close()
    return tmp_path


def log_entry(repo, style, instrument, when, decision="allow", reason="placed"):
    conn = sqlite3.connect(repo / rs.AUDIT_DBS[style])
    conn.execute("INSERT INTO decisions (timestamp, instrument, event_type, decision, reason, trade_id) "
                 "VALUES (?, ?, 'entry_attempt', ?, ?, '1')",
                 (when.isoformat(), instrument, decision, reason))
    conn.commit()
    conn.close()


def _fresh(f, now=None):
    """Feeds in these tests are hand-built with old timestamps, so pass a
    `now` close to them wherever staleness isn't what's under test."""
    return now or (rs._parse_time(f["generated_at"]) + timedelta(minutes=5))


def run(repo, f, window_hours=2):
    return rs.reconcile(f, str(repo), timedelta(hours=window_hours))


def test_a_signal_the_bot_logged_promptly_is_seen(repo):
    log_entry(repo, "conservative", "EURCAD", T(17, 4))
    results, _ = run(repo, feed([signal("EURCAD", "conservative", T(17))]))
    assert [r["state"] for r in results] == ["SEEN"]


def test_a_signal_no_bot_logged_is_missing(repo):
    results, _ = run(repo, feed([signal("USDCHF", "conservative", T(17))]))
    assert [r["state"] for r in results] == ["MISSING"]


def test_a_signal_logged_hours_late_is_late_not_seen(repo):
    # The real 2026-08-26 case: Dukascopy's EURCAD signal was on the
    # 17:00 candle and the bot's audit row landed at 20:01. Counting that
    # as SEEN would hide precisely the lag problem the storyline gate and
    # cache work were built to fix.
    log_entry(repo, "conservative", "EURCAD", T(20, 1))
    results, _ = run(repo, feed([signal("EURCAD", "conservative", T(17))]), window_hours=4)
    assert results[0]["state"] == "LATE"
    assert results[0]["lag"] == timedelta(hours=3, minutes=1)


def test_a_declined_signal_still_counts_as_seen(repo):
    # The bot saw it and the risk manager said no. That is a healthy
    # outcome for THIS check -- whether the decline was correct is a
    # different question. Treating a decline as a miss would fire alarms
    # every time the daily drawdown gate did its job.
    log_entry(repo, "conservative", "EURCAD", T(17, 10),
              decision="decline_daily_drawdown", reason="daily loss limit reached")
    results, _ = run(repo, feed([signal("EURCAD", "conservative", T(17))]))
    assert results[0]["state"] == "SEEN"
    assert results[0]["row"]["decision"] == "decline_daily_drawdown"


def test_the_other_styles_row_cannot_satisfy_a_signal(repo):
    # Confirmed live on 2026-08-26: conservative logged EURCAD and
    # aggressive logged nothing at all. If either database could answer
    # for the other, that asymmetry -- the actual finding -- disappears.
    log_entry(repo, "conservative", "EURCAD", T(17, 5))
    results, _ = run(repo, feed([signal("EURCAD", "conservative", T(17)),
                                  signal("EURCAD", "aggressive", T(17))]))
    assert [r["state"] for r in results] == ["SEEN", "MISSING"]


def test_one_row_cannot_match_two_signals_on_the_same_instrument(repo):
    # Two setups on the same pair inside the window, one audit row. The
    # second must come out MISSING rather than both claiming the row and
    # reporting a clean sweep.
    log_entry(repo, "conservative", "EURCAD", T(17, 5))
    results, _ = run(repo, feed([signal("EURCAD", "conservative", T(17)),
                                  signal("EURCAD", "conservative", T(18))]))
    assert sorted(r["state"] for r in results) == ["MISSING", "SEEN"]


def test_a_row_is_matched_to_the_nearest_signal_not_the_first(repo):
    log_entry(repo, "conservative", "EURCAD", T(18, 5))
    results, _ = run(repo, feed([signal("EURCAD", "conservative", T(16)),
                                  signal("EURCAD", "conservative", T(18))]))
    states = {r["signal"]["entry_time"]: r["state"] for r in results}
    assert states[T(18).isoformat()] == "SEEN"
    assert states[T(16).isoformat()] == "MISSING"


def test_no_signals_published_is_a_clean_result_not_an_alarm(repo):
    # 2026-08-27: Dukascopy produced nothing, so both empty databases are
    # CORRECT. Reporting that as a problem is the false alarm that makes
    # the whole check get ignored.
    f = feed([])
    results, unmatched = run(repo, f)
    report, needs_attention = rs.render(f, results, unmatched, now=_fresh(f))
    assert needs_attention is False
    assert "CORRECT outcome" in report


def test_an_audit_row_with_no_published_signal_is_surfaced(repo):
    log_entry(repo, "aggressive", "GBPJPY", T(19))
    results, unmatched = run(repo, feed([]))
    assert len(unmatched) == 1
    assert unmatched[0]["instrument"] == "GBPJPY"


def test_a_missing_database_is_not_an_error(repo):
    # A bot that has never logged anything is normal on a fresh deploy.
    (repo / rs.AUDIT_DBS["aggressive"]).unlink()
    results, _ = run(repo, feed([signal("EURCAD", "aggressive", T(17))]))
    assert [r["state"] for r in results] == ["MISSING"]


def test_upstream_errors_are_reported_rather_than_read_as_all_clear(repo):
    # An instrument that errored upstream was never actually checked.
    # Silently folding it into "no signals found" would report a clean
    # bill of health for something nobody looked at.
    f = feed([], errored=[{"instrument": "XAUUSD", "style": "conservative", "error": "boom"}])
    results, unmatched = run(repo, f)
    report, _ = rs.render(f, results, unmatched)
    assert "cannot speak for them" in report
    assert "XAUUSD" in report


def test_needs_attention_drives_the_exit_code(repo):
    f = feed([signal("USDCHF", "conservative", T(17))])
    results, unmatched = run(repo, f)
    _, needs_attention = rs.render(f, results, unmatched)
    assert needs_attention is True


def test_rows_before_the_window_are_still_available_to_match(repo, tmp_path):
    # A signal at the very start of the window can legitimately be
    # answered by a row logged slightly before it. Querying the database
    # from `since` alone would drop that row and cry MISSING.
    log_entry(repo, "conservative", "EURCAD", T(11, 30))
    results, _ = run(repo, feed([signal("EURCAD", "conservative", T(12))], since=T(12)))
    assert results[0]["state"] == "SEEN"


def test_end_to_end_via_a_local_feed_file(repo, tmp_path, capsys):
    path = tmp_path / "feed.json"
    path.write_text(json.dumps(feed([signal("EURCAD", "conservative", T(17))])))
    log_entry(repo, "conservative", "EURCAD", T(17, 3))
    code = rs.main.__wrapped__ if hasattr(rs.main, "__wrapped__") else rs.main
    import sys
    argv = sys.argv
    # These fixtures carry fixed August timestamps, so the staleness check
    # would (correctly) fire on them; widened here because this test is
    # about the end-to-end path, not feed freshness.
    sys.argv = ["reconcile_signals", "--repo", str(repo), "--feed-path", str(path),
                "--max-feed-age-hours", "1000000"]
    try:
        assert code() == 0
    finally:
        sys.argv = argv
    assert "[SEEN" in capsys.readouterr().out


def test_an_unpublished_feed_branch_says_so_instead_of_relaying_git(tmp_path, monkeypatch):
    # The first-run state. git's own "couldn't find remote ref" reads like
    # a misconfigured remote and sends you looking in the wrong place; the
    # branch simply hasn't been published to yet.
    import subprocess

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, 128, stdout="", stderr="fatal: couldn't find remote ref signal-feed\n")

    monkeypatch.setattr(rs.subprocess, "run", fake_run)
    with pytest.raises(rs.FeedNotPublished) as exc:
        rs.fetch_feed(str(tmp_path), "signal-feed", "recent-signals.json")
    assert "does not exist yet" in str(exc.value)
    assert "Hourly signal check" in str(exc.value)


def test_a_broken_feed_is_never_reported_as_a_quiet_healthy_hour(tmp_path, monkeypatch):
    # The dangerous confusion: "couldn't read the feed" must not come out
    # looking like "checked, found nothing". A pipeline that silently
    # stopped publishing would otherwise read as permanent good news.
    import subprocess

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: unable to access\n")

    monkeypatch.setattr(rs.subprocess, "run", fake_run)
    with pytest.raises(rs.FeedUnavailable):
        rs.fetch_feed(str(tmp_path), "signal-feed", "recent-signals.json")


def test_the_feed_is_read_from_fetch_head_not_a_remote_tracking_ref(tmp_path, monkeypatch):
    # Regression guard. The live checkout fetches a single branch
    # (`+refs/heads/main:refs/remotes/origin/main`), so fetching
    # signal-feed populates FETCH_HEAD and never creates
    # refs/remotes/origin/signal-feed. Reading `origin/<branch>` works in
    # a full clone and fails on the one machine this actually runs on --
    # the worst kind of bug to reintroduce while tidying.
    import subprocess

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"signals": []}', stderr="")

    monkeypatch.setattr(rs.subprocess, "run", fake_run)
    rs.fetch_feed(str(tmp_path), "signal-feed", "recent-signals.json")
    show = next(c for c in calls if "show" in c)
    assert "FETCH_HEAD:recent-signals.json" in show
    assert not any("origin/signal-feed:" in part for part in show)


def test_a_feed_that_stopped_being_republished_is_an_alarm(repo):
    # The failure this whole script exists to prevent, one level up: if
    # the publishing workflow dies, generated_at freezes and every later
    # run reports "0 signals -- all clear" against a window that stopped
    # moving. Silence would then mean "broken" and look identical to
    # "healthy".
    f = feed([])
    results, unmatched = run(repo, f)
    stale_now = rs._parse_time(f["generated_at"]) + timedelta(hours=5)
    report, needs_attention = rs.render(f, results, unmatched, now=stale_now)
    assert needs_attention is True
    assert "STALE FEED" in report
    assert "5.0h ago" in report


def test_a_recently_published_empty_feed_is_still_clean(repo):
    # The other side: staleness must not turn every quiet hour into an
    # alarm, or the check gets ignored for the opposite reason.
    f = feed([])
    results, unmatched = run(repo, f)
    report, needs_attention = rs.render(f, results, unmatched, now=_fresh(f))
    assert needs_attention is False
    assert "STALE FEED" not in report


def test_staleness_is_reported_even_when_every_signal_was_seen(repo):
    # A stale feed's signals were all matched hours ago. That is not a
    # current all-clear, and must not be presented as one.
    log_entry(repo, "conservative", "EURCAD", T(17, 5))
    f = feed([signal("EURCAD", "conservative", T(17))])
    results, unmatched = run(repo, f)
    assert results[0]["state"] == "SEEN"
    stale_now = rs._parse_time(f["generated_at"]) + timedelta(hours=9)
    report, needs_attention = rs.render(f, results, unmatched, now=stale_now)
    assert needs_attention is True
    assert "STALE FEED" in report
