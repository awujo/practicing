"""Position sizing and idempotency helpers (pure functions, no network).

cTrader volumes are in *cents of units*: volume 100 = 1 unit, 100000 = 1000 units (0.01 lot on FX),
lotSize for FX is 10_000_000 (= 100 000 units). minVolume / stepVolume / maxVolume use the same unit.
"""
import math
import re


def pip_size(pip_position):
    return 10.0 ** -pip_position


def pip_value_per_lot(pip_position, lot_size, quote_to_account=1.0):
    """Account-currency value of 1 pip on 1 lot.

    quote_to_account: price of 1 unit of the quote currency in account currency
    (1.0 when the quote currency is the account currency, e.g. EURUSD on a USD account;
    1/price when the base is the account currency, e.g. USDJPY on a USD account).
    """
    units_per_lot = lot_size / 100.0
    return pip_size(pip_position) * units_per_lot * quote_to_account


def volume_for_risk(balance, risk_pct, stop_pips, pip_value_lot, lot_size, min_volume, step_volume,
                    max_volume=None, max_lots=None):
    """Protocol volume (cents of units) risking `risk_pct`% of `balance` with a `stop_pips` stop.

    Rounded DOWN to step_volume, never above max_volume / max_lots. Returns 0 when the risk budget
    is smaller than the symbol's minimum volume (caller must then skip the trade).
    """
    if balance <= 0 or risk_pct <= 0 or stop_pips <= 0 or pip_value_lot <= 0:
        return 0
    risk_money = balance * risk_pct / 100.0
    lots = risk_money / (stop_pips * pip_value_lot)
    vol = lots * lot_size
    caps = [c for c in (max_volume, (max_lots * lot_size) if max_lots else None) if c]
    if caps:
        vol = min(vol, min(caps))
    step = step_volume or 1
    vol = int(math.floor(vol / step + 1e-9) * step)
    if vol < (min_volume or 0):
        return 0
    return vol


def volume_to_lots(volume, lot_size):
    return volume / lot_size


def client_order_id(entry_id, prefix="slk"):
    """Deterministic client order id for an `entries` row: same entry -> same id -> no duplicate order."""
    s = str(entry_id).strip()
    if not s:
        raise ValueError("entry_id required")
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", s)
    return f"{prefix}-e{s}"[:50]


def round_price(price, digits):
    return round(float(price), int(digits))


def relative_points(entry, level, digits):
    """Distance |entry-level| in the protocol's 1/100000 price unit, rounded to the symbol precision
    (cTrader requires relative SL/TP to be a multiple of 10^(5-digits))."""
    unit = 10 ** max(0, 5 - int(digits))
    raw = abs(float(entry) - float(level)) * 100000
    return int(round(raw / unit)) * unit
