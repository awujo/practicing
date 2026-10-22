"""Export enabled cTrader account symbols; no candles, orders or alias guesses."""
import json
from datetime import datetime, timezone
from pathlib import Path
from ctrader.client import CTraderClient
from ctrader import tokens
from slk.instruments import norm


def main():
    with CTraderClient(settings=tokens.default_settings()) as client:
        symbols = client.get_symbols()
    rows = [{"key": norm(name), "name": name, "symbol_id": info["symbol_id"],
             "digits": info["digits"], "pip_position": info["pip_position"]}
            for name, info in sorted(symbols.items())]
    if not rows:
        raise RuntimeError("Broker returned no enabled symbols; previous catalogue preserved")
    path = Path("data/broker_symbols.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"provider": "IC Markets cTrader", "environment": "demo",
                               "updated_at": datetime.now(timezone.utc).isoformat(),
                               "symbols": rows}, indent=2) + "\n")
    print(f"Exported {len(rows)} enabled broker symbols")


if __name__ == "__main__":
    main()
