"""
Entry point -- wires a real MT5 connection into everything else in bot/.
This is the one file in bot/ that imports an MT5 client library directly;
everywhere else takes `mt5` as an injected dependency specifically so it
can be swapped for the test fake (see bot/tests/fake_mt5.py).

Two ways to get a real `mt5` object, chosen with --bridge:

  - "native" (default on Windows): `import MetaTrader5 as mt5` directly.
    Only works when this process itself is running as a Windows process
    with a local MT5 terminal -- i.e. actually on Windows, or run via
    Wine's own Python interpreter (not your system Python).

  - "mt5linux" (what an Ubuntu VPS needs): the official MetaTrader5
    package has no Linux wheels, so native Ubuntu Python can't import it
    directly even with the MT5 terminal running under Wine. The
    `mt5linux` package bridges this: a small proxy server runs inside
    Wine's Python (where the real MetaTrader5 package works), and this
    process connects to it over a local socket as a normal native Linux
    Python client. See bot/README.md's "Ubuntu VPS setup" section for how
    to actually get the Wine-side server running -- that half is NOT
    something this script does for you.

Not runnable in this sandbox either way (no MT5 terminal reachable) --
needs a machine with MT5 actually installed and logged in.

Usage (Ubuntu VPS via mt5linux, the expected path for this deployment):
    MT5_PHASE1_LOGIN=... MT5_PHASE1_PASSWORD=... MT5_PHASE1_SERVER=... \\
    python -m bot.run_live --account-type prop_firm --phase phase1 \\
        --instruments EURUSD,GBPUSD,USDJPY,XAUUSD \\
        --bridge mt5linux --bridge-host 127.0.0.1 --bridge-port 18812

MT5_SYMBOL_SUFFIX / --symbol-suffix defaults to "" (no suffix) -- set it
to whatever your broker's Market Watch actually shows (e.g. ".a", "m",
"_i") before running against a real account.

A suffix alone isn't always enough -- some symbols get renamed outright,
not just suffixed. MT5_SYMBOL_OVERRIDES / --symbol-overrides takes a JSON
object of {internal_name: broker_name} for exactly those cases, applied
on top of (and taking priority over) the suffix -- see config.SymbolMap.
METAQUOTES_DEMO_OVERRIDES below is the confirmed mapping for testing
against the MetaQuotes-Demo server specifically (NAS100 -> USTEC,
JP225 -> JPN225) -- it is NOT applied automatically, since a real prop
firm's broker will very likely need a different mapping. USOIL and
ETHUSD are NOT in it -- still unconfirmed on that server as of writing;
check Market Watch's Energy/Crypto categories before trading either.
"""

import argparse
import json
import logging
import os
import time

from .config import load_personal_profile, load_prop_firm_profile
from .audit_log import AuditLog
from .mt5_data import MT5Client
from .mt5_execution import MT5Execution
from . import signal_channel
from .orchestrator import LiveBot, STALE_ENTRY_CUTOFF_LIMIT
from .signal_channel import SignalChannel
from .shadow_book import ShadowBook
from .telegram_notify import attach_if_configured

POLL_SECONDS = 5  # how often run_once() checks for a new candle close -- cheap when nothing's happened

# Confirmed via the MT5 mobile app's Market Watch search on MetaQuotes-Demo
# (forex majors/crosses and metals were all plain, no suffix, no rename --
# only these two indices differed so far). Opt into this explicitly, e.g.:
#   --symbol-overrides '{"NAS100": "USTEC", "JP225": "JPN225"}'
# It is never applied automatically.
METAQUOTES_DEMO_OVERRIDES = {
    "NAS100": "USTEC",
    "JP225": "JPN225",
}


def resolve_history_window_years(config: dict, instruments: tuple) -> dict:
    """Turns the two-tier structure in a --history-windows-config file
    into the flat {instrument: window} dict LiveBot actually wants.

    config: {"default": window | None, "instruments": {name: window | None}}.
    `window` is {"D": years, "W": years, "H4": years, "H1": years}.

    For each instrument actually being run: an explicit entry in
    "instruments" wins outright, INCLUDING an explicit null -- that's
    "confirmed NOT safe to cap" (e.g. GBPNZD, which never converged even
    at a 15-year search ceiling; see OPERATIONS_LOG.md 2026-09-13),
    deliberately different from "no data yet," and must stay uncapped
    even if a "default" is configured. An instrument with no entry at
    all falls back to "default" if one is set. Either way, "uncapped"
    means the instrument is simply absent from the returned dict --
    matches run_backtest()'s own None-means-unbounded convention for
    max_history_years, no separate sentinel needed.

    Why a default is worth having at all: a flat window loses bit-exact
    convergence for the trades right at its own boundary, but that is a
    fundamentally different risk than an instrument openly returning
    ZERO trades or fabricating extra ones -- see OPERATIONS_LOG.md
    2026-09-13's full 25-instrument run, where every instrument except
    GBPNZD scored 90-100% at a flat 2y/1y window under these settings.
    Leaving those instruments fully uncapped over that difference throws
    away a real, already-measured speedup for no corresponding safety
    gain, which is the whole point of this mechanism existing."""
    default_window = config.get("default")
    overrides = config.get("instruments", {})
    resolved = {}
    for instrument in instruments:
        if instrument in overrides:
            window = overrides[instrument]
            if window is not None:
                resolved[instrument] = window
            # else: explicit null -- deliberately excluded, stays uncapped
        elif default_window is not None:
            resolved[instrument] = default_window
        # else: no override and no default configured -- stays uncapped
    return resolved


def _connect_mt5(bridge: str, bridge_host: str, bridge_port: int):
    """Returns an object exposing the same method/attribute surface as
    the real `MetaTrader5` module -- either the module itself (native) or
    an mt5linux proxy instance (bridge). Both are handed to MT5Client/
    MT5Execution unchanged; neither of those classes knows or cares which
    one they got, by design."""
    if bridge == "native":
        import MetaTrader5 as mt5
        return mt5
    if bridge == "mt5linux":
        # NOT verified from this development environment -- mt5linux's
        # exact constructor signature/behavior needs confirming against
        # your actual Wine-side server once it's running.
        from mt5linux import MetaTrader5
        return MetaTrader5(host=bridge_host, port=bridge_port)
    raise ValueError(f"unknown --bridge {bridge!r}")


def main():
    parser = argparse.ArgumentParser(description="Run the live SLK trading bot against MT5.")
    parser.add_argument("--account-type", choices=("prop_firm", "personal"), required=True)
    parser.add_argument("--phase", choices=("phase1", "phase2", "funded"),
                         help="required when --account-type=prop_firm")
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,GBPUSD,XAUUSD")
    parser.add_argument("--style", choices=("aggressive", "conservative"), default="conservative")
    parser.add_argument("--stop-anchor", default="trigger_wick",
                         choices=("trigger_wick", "trigger_only", "trigger_skip", "structural"),
                         help="where the stop is anchored. 'trigger_wick' (default) is the "
                              "long-standing per-trigger behavior. 'structural' anchors to the "
                              "setup's own reaction-leg extreme -- the invalidation point the "
                              "confirmation actually created.")
    parser.add_argument("--notify-only", action="store_true",
                        help="Watch and report, place nothing. The storyline "
                             "gate and the signal search run exactly as they "
                             "would when trading, so what reaches Telegram is "
                             "what would have been traded -- only the order is "
                             "withheld. Bias and storyline transitions and "
                             "confirmations go to the signal channel "
                             "(SLK_SIGNAL_TOKEN / SLK_SIGNAL_CHAT); the ordinary "
                             "log channel is untouched.")
    parser.add_argument("--entry-order-type", choices=("market", "limit"), default="market",
                         help="'market' (default) sends at whatever price exists when the order "
                              "goes out. 'limit' rests the order AT the computed entry level, so "
                              "a late send fills at the price the stop was sized for or not at "
                              "all -- see setup_validity.py for the live audit that motivated it.")
    parser.add_argument("--min-departure-r", type=float, default=0.0,
                         help="only meaningful with --entry-order-type limit. Require price to "
                              "travel this many multiples of the stop distance AWAY from entry, "
                              "in the trade's favour, before the order is actually rested -- "
                              "otherwise it fills almost immediately at the level it just formed "
                              "at, which is a market order wearing a limit's label, not the "
                              "retest Bishop's own broker screenshots show. 0.0 (default) rests "
                              "immediately, matching every behavior before 2026-09-11. Backtested "
                              "at 1.0: 738R -> 991R, win rate 42.0%% -> 50.6%% -- see "
                              "check_setup()'s docstring in setup_validity.py.")
    parser.add_argument("--origin-kind", default="sweep_break", choices=("sweep_break", "any"),
                         help="how the first Daily/Weekly bias is bootstrapped -- see "
                              "run_backtest()'s own docstring in backtest/engine/runner.py. "
                              "'sweep_break' (default) matches every behavior before 2026-09-13. "
                              "'any' also accepts a plain breakout, matching bias.py's own "
                              "confirmation rule ('both are valid') -- confirmed via full-history "
                              "A/B not to hurt performance (see OPERATIONS_LOG.md, 2026-09-13) and "
                              "required for the --history-windows-config values below, which were "
                              "measured under this setting.")
    parser.add_argument("--close-based-sweep-break", action="store_true",
                         help="read the level a sweep+break must close beyond off the swing "
                              "candle's CLOSE instead of its wick -- see StructureTracker's own "
                              "close_based_break docstring. Off by default (wick, unchanged). "
                              "Required for the --history-windows-config values below, which were "
                              "measured with this on.")
    parser.add_argument("--require-flip-confirmation", action="store_true",
                         help="bias-flip state machine, condition (c) hardened: do NOT flip "
                              "the bias when the lower timeframe's confirmation window is "
                              "EMPTY. An empty window satisfies 'no further continuation in "
                              "the old direction' literally, so without this a live bias can "
                              "flip on no evidence at all -- the tail of the data is exactly "
                              "where live runs (see AUDIT_2026-09-22_PART2.md). Off by "
                              "default; every recorded number reproduces. Wired to BOTH "
                              "run_backtest() and the storyline gate.")
    parser.add_argument("--require-flip-touch", action="store_true",
                         help="bias-flip state machine, condition (a) enforced inside "
                              "check_flip(): require the rejection candle to have actually "
                              "TRADED INTO the key level before testing the flip, not just "
                              "closed through it. replay_bias()'s own scan already filters "
                              "this way, so this cannot change any result -- it protects "
                              "hand-built and future call sites from silently skipping "
                              "condition (a). Off by default (unchanged behavior).")
    parser.add_argument("--history-windows-config", default=None,
                         help="path to a JSON file mapping instrument -> {\"D\":years,\"W\":years,"
                              "\"H4\":years,\"H1\":years} trailing-history caps, passed through to "
                              "run_backtest()'s max_history_years per instrument. An instrument "
                              "missing from the file runs on full, uncapped history. See "
                              "bot/history_windows.json and its own values ONLY confirmed safe "
                              "under --origin-kind any --close-based-sweep-break -- do not use "
                              "this file with different settings than the ones it was measured "
                              "under. Not set by default (every instrument uncapped, unchanged "
                              "behavior).")
    parser.add_argument("--symbol-suffix", default=os.environ.get("MT5_SYMBOL_SUFFIX", ""),
                         help="broker's Market Watch suffix, e.g. .a")
    parser.add_argument("--symbol-overrides", default=os.environ.get("MT5_SYMBOL_OVERRIDES", "{}"),
                         help='JSON {internal_name: broker_name} for symbols that are renamed outright, '
                              'not just suffixed, e.g. \'{"NAS100": "USTEC"}\'')
    parser.add_argument("--bridge", choices=("native", "mt5linux"), default="mt5linux",
                         help="'mt5linux' for an Ubuntu/Wine VPS (default), 'native' when this process "
                              "itself runs as a Windows process with MT5 installed locally")
    parser.add_argument("--bridge-host", default="127.0.0.1", help="mt5linux server host")
    parser.add_argument("--bridge-port", type=int, default=18812, help="mt5linux server port")
    parser.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH"),
                         help="Windows path to a specific terminal64.exe, e.g. 'C:\\\\MT5-Aggressive\\\\terminal64.exe'. "
                              "Required when more than one MT5 install/account shares a single Wine prefix/bridge -- "
                              "without it, mt5.initialize() falls back to whatever terminal MT5 finds by default, "
                              "which silently connects to the WRONG account rather than failing loudly. Not needed "
                              "when only one terminal is installed.")
    parser.add_argument("--shadow-departure-r", default="",
                         help="comma-separated min_departure_r values to PAPER-TRADE alongside "
                              "the real --min-departure-r above, on the exact same signals this "
                              "bot already produces -- NEVER sent to MT5, no order is ever placed, "
                              "cancelled or closed for these. e.g. '0.0' tracks what would have "
                              "happened if the order rested immediately, side by side with "
                              "whatever --min-departure-r actually does. Each value gets its own "
                              "'<audit-db-stem>_shadow_<value>.db' (same schema as --audit-db, "
                              "directly comparable) and logs through the same Telegram channel, "
                              "tagged [SHADOW:<value>] so it can never be mistaken for a real "
                              "trade. See shadow_book.py.")
    parser.add_argument("--audit-db", default="bot_audit_log.db")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--telegram-level", default="WARNING", choices=("INFO", "WARNING", "ERROR"),
                         help="Minimum level forwarded to Telegram when TELEGRAM_BOT_TOKEN/"
                              "TELEGRAM_CHAT_ID are set (see telegram_notify.py). WARNING (default) "
                              "covers reconnect issues, health halts and errors without every entry/"
                              "exit; INFO also includes every entry, exit, decline and phase "
                              "transition -- the closest thing to \"everything,\" and noisier.")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("bot.run_live")

    # Opt-in: no-op unless TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are
    # both set (see telegram_notify.py's module docstring for why
    # WARNING is the default level and what it does and doesn't cover).
    telegram_handler = attach_if_configured(level=getattr(logging, args.telegram_level))
    if telegram_handler is not None:
        logger.info("Telegram notifications enabled")

    if args.account_type == "prop_firm":
        if not args.phase:
            parser.error("--phase is required for --account-type=prop_firm")
        profile = load_prop_firm_profile(args.phase)
    else:
        profile = load_personal_profile()

    try:
        symbol_overrides = json.loads(args.symbol_overrides)
    except json.JSONDecodeError as exc:
        parser.error(f"--symbol-overrides is not valid JSON: {exc}")

    history_windows_raw = None
    if args.history_windows_config:
        try:
            with open(args.history_windows_config) as f:
                history_windows_raw = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"--history-windows-config could not be read: {exc}")

    mt5 = _connect_mt5(args.bridge, args.bridge_host, args.bridge_port)

    creds = profile.active_credentials
    mt5_client = MT5Client(mt5, login=creds.login, password=creds.password, server=creds.server,
                            symbol_suffix=args.symbol_suffix, symbol_overrides=symbol_overrides,
                            terminal_path=args.terminal_path)
    mt5_client.connect()
    logger.info("connected to MT5 (%s @ %s)", creds.login, creds.server)

    # max_entry_drift_fraction=1.0: decline a signal once the market has
    # travelled a FULL stop distance away from the entry price this
    # trade's stop was sized against -- see MT5Execution.__init__'s
    # comment for the 2026-09-01 CHFJPY fill that motivated it (filled
    # ~2x its own stop distance away, giving an inverted risk:reward the
    # strategy never intended).
    #
    # 1.0 rather than a tighter tuned number on purpose. It is the one
    # non-arbitrary line available: past a full stop distance the setup
    # is invalidated on its own terms, so declining needs no calibration
    # to justify. A tighter value (0.25 was tried first) allows only ~2.5
    # pips of drift on a 10-pip SLK stop, which ordinary latency between
    # candle close and order send -- run_backtest takes tens of seconds
    # per instrument, across 25 of them -- would exceed routinely,
    # declining good trades in bulk. Blocking the catastrophic case while
    # almost never firing otherwise is the right trade for a stretch
    # nobody is watching; erring tight would quietly stop the bot
    # trading and look identical to it simply not finding setups.
    #
    # FAIL-CLOSED: if the live bid/ask can't be read the trade is
    # declined, logged as decline_sizing_price_unavailable. If that
    # reason starts appearing for EVERY instrument right after a deploy,
    # this broker/bridge isn't exposing prices the way expected -- pass
    # max_entry_drift_fraction=None here to turn the guard back off
    # rather than letting the bot sit idle.
    mt5_exec = MT5Execution(mt5, symbol_suffix=args.symbol_suffix, symbol_overrides=symbol_overrides,
                             max_entry_drift_fraction=1.0,
                             expected_login=creds.login)
    audit_log = AuditLog(args.audit_db)
    instruments = tuple(s.strip().upper() for s in args.instruments.split(","))

    history_window_years = {}
    if history_windows_raw is not None:
        history_window_years = resolve_history_window_years(history_windows_raw, instruments)
        logger.info("history window caps: %d of %d instrument(s) capped from %s (rest uncapped)",
                    len(history_window_years), len(instruments), args.history_windows_config)

    db_stem = os.path.splitext(args.audit_db)[0]
    shadow_books = []
    for raw in args.shadow_departure_r.split(","):
        raw = raw.strip()
        if not raw:
            continue
        shadow_books.append(ShadowBook(
            name=raw, min_departure_r=float(raw),
            audit_log=AuditLog(f"{db_stem}_shadow_{raw}.db"),
            stale_cutoff=STALE_ENTRY_CUTOFF_LIMIT,
        ))
        logger.info("shadow variant enabled: min_departure_r=%s -> %s_shadow_%s.db "
                    "(paper only, never reaches MT5)", raw, db_stem, raw)

    signals = SignalChannel.from_env(label=args.style)
    if signals is None:
        logger.info("no signal channel configured (%s / %s unset) -- "
                     "bias notifications are off",
                     signal_channel.TOKEN_VAR, signal_channel.CHAT_VAR)
    else:
        logger.info("signal channel on: bias, storyline and confirmations")
    if args.notify_only:
        logger.info("NOTIFY-ONLY: no orders will be placed")

    bot = LiveBot(profile=profile, mt5_client=mt5_client, mt5_exec=mt5_exec,
                   audit_log=audit_log, instruments=instruments, entry_style=args.style,
                   notify_only=args.notify_only, signals=signals,
                   entry_order_type=args.entry_order_type,
                   min_departure_r=args.min_departure_r,
                   stop_anchor=args.stop_anchor,
                   origin_kind=args.origin_kind,
                   close_based_sweep_break=args.close_based_sweep_break,
                   history_window_years=history_window_years,
                   shadow_books=tuple(shadow_books))

    logger.info("starting live loop: %s, instruments=%s", args.account_type, instruments)
    try:
        while True:
            bot.run_once()
            if telegram_handler is not None:
                # Guarantees a batch queued during a burst still goes out
                # promptly once things quiet down, rather than waiting on
                # some future record to naturally trigger the next send
                # -- see TelegramHandler's docstring. Cheap: a no-op when
                # nothing is pending.
                telegram_handler.flush()
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        mt5_client.disconnect()
        audit_log.close()
        for book in shadow_books:
            book.audit_log.close()


if __name__ == "__main__":
    main()
