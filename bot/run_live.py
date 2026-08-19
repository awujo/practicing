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
"""

import argparse
import logging
import os
import time

from .config import load_personal_profile, load_prop_firm_profile
from .audit_log import AuditLog
from .mt5_data import MT5Client
from .mt5_execution import MT5Execution
from .orchestrator import LiveBot

POLL_SECONDS = 5  # how often run_once() checks for a new candle close -- cheap when nothing's happened


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
    parser.add_argument("--symbol-suffix", default=os.environ.get("MT5_SYMBOL_SUFFIX", ""),
                         help="broker's Market Watch suffix, e.g. .a")
    parser.add_argument("--bridge", choices=("native", "mt5linux"), default="mt5linux",
                         help="'mt5linux' for an Ubuntu/Wine VPS (default), 'native' when this process "
                              "itself runs as a Windows process with MT5 installed locally")
    parser.add_argument("--bridge-host", default="127.0.0.1", help="mt5linux server host")
    parser.add_argument("--bridge-port", type=int, default=18812, help="mt5linux server port")
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

    mt5 = _connect_mt5(args.bridge, args.bridge_host, args.bridge_port)

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
