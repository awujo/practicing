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
from .orchestrator import LiveBot
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
                             max_entry_drift_fraction=1.0)
    audit_log = AuditLog(args.audit_db)
    instruments = tuple(s.strip().upper() for s in args.instruments.split(","))

    bot = LiveBot(profile=profile, mt5_client=mt5_client, mt5_exec=mt5_exec,
                   audit_log=audit_log, instruments=instruments, entry_style=args.style,
                   entry_order_type=args.entry_order_type,
                   min_departure_r=args.min_departure_r,
                   stop_anchor=args.stop_anchor)

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


if __name__ == "__main__":
    main()
