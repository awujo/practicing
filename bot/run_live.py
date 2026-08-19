"""
Entry point -- wires the real `MetaTrader5` package into everything else
in bot/. This is the one file in bot/ that imports MetaTrader5 directly;
everywhere else takes it as an injected dependency specifically so it can
be swapped for the test fake (see bot/tests/fake_mt5.py).

Not runnable in this sandbox (no MT5 terminal reachable, and the
MetaTrader5 package itself needs a running terminal to connect to) --
this needs to run on the machine that actually has MT5 installed and
logged in (a Windows VPS, or Linux via Wine per the earlier discussion).

Usage:
    MT5_PHASE1_LOGIN=... MT5_PHASE1_PASSWORD=... MT5_PHASE1_SERVER=... \\
    MT5_SYMBOL_SUFFIX=.a \\
    python -m bot.run_live --account-type prop_firm --phase phase1 \\
        --instruments EURUSD,GBPUSD,USDJPY,XAUUSD

MT5_SYMBOL_SUFFIX defaults to "" (no suffix) -- set it to whatever your
broker's Market Watch actually shows (e.g. ".a", "m", "_i") before
running against a real account. Check by opening MT5's Market Watch and
comparing what's listed there against the plain internal names in
backtest/data_pipeline/instruments.py.
"""

import argparse
import logging
import time

from .config import load_personal_profile, load_prop_firm_profile
from .audit_log import AuditLog
from .mt5_data import MT5Client
from .mt5_execution import MT5Execution
from .orchestrator import LiveBot

POLL_SECONDS = 5  # how often run_once() checks for a new candle close -- cheap when nothing's happened


def main():
    parser = argparse.ArgumentParser(description="Run the live SLK trading bot against MT5.")
    parser.add_argument("--account-type", choices=("prop_firm", "personal"), required=True)
    parser.add_argument("--phase", choices=("phase1", "phase2", "funded"),
                         help="required when --account-type=prop_firm")
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,GBPUSD,XAUUSD")
    parser.add_argument("--style", choices=("aggressive", "conservative"), default="conservative")
    parser.add_argument("--symbol-suffix", default="", help="broker's Market Watch suffix, e.g. .a")
    parser.add_argument("--audit-db", default="bot_audit_log.db")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("bot.run_live")

    if args.account_type == "prop_firm":
        if not args.phase:
            parser.error("--phase is required for --account-type=prop_firm")
        profile = load_prop_firm_profile(args.phase)
    else:
        profile = load_personal_profile()

    import MetaTrader5 as mt5  # imported here, not at module scope -- see module docstring

    creds = profile.active_credentials
    mt5_client = MT5Client(mt5, login=creds.login, password=creds.password,
                            server=creds.server, symbol_suffix=args.symbol_suffix)
    mt5_client.connect()
    logger.info("connected to MT5 (%s @ %s)", creds.login, creds.server)

    mt5_exec = MT5Execution(mt5, symbol_suffix=args.symbol_suffix)
    audit_log = AuditLog(args.audit_db)
    instruments = tuple(s.strip().upper() for s in args.instruments.split(","))

    bot = LiveBot(profile=profile, mt5_client=mt5_client, mt5_exec=mt5_exec,
                   audit_log=audit_log, instruments=instruments, entry_style=args.style)

    logger.info("starting live loop: %s, instruments=%s", args.account_type, instruments)
    try:
        while True:
            bot.run_once()
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        mt5_client.disconnect()
        audit_log.close()


if __name__ == "__main__":
    main()
