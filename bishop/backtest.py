"""Offline frozen-candle supported-route replay; no live settings or broker calls."""
import argparse
import json
from pathlib import Path

from .coverage import load_csv
from .engine import run
from .execution import Costs
from .replay import evaluate
from .universe import PAIRS


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True)
    p.add_argument("--source", required=True, help="actual candle-feed provenance, never guessed from filename")
    p.add_argument("--pair", required=True, choices=PAIRS)
    p.add_argument("--as-of", required=True)
    p.add_argument("--history-start", required=True)
    p.add_argument("--scan-start", required=True)
    p.add_argument("--origin-tf", choices=("D", "W", "M", "H4"), required=True)
    p.add_argument("--entry-tf", choices=("H1", "H2", "H4"), required=True)
    p.add_argument("--level-mode", choices=("exact_junction", "close_reference"), required=True)
    p.add_argument("--stop-profile", choices=("structural_wick", "fixed_pips"), required=True)
    p.add_argument("--spread-pips", type=float, required=True)
    p.add_argument("--stop-slippage-pips", type=float, required=True)
    p.add_argument("--commission-pips", type=float, required=True)
    p.add_argument("--pending-hours", type=int, required=True)
    p.add_argument("--buffer-pips", type=float, default=0.5)
    p.add_argument("--fixed-stop-pips", type=float, default=11.0)
    p.add_argument("--examples", help="optional source fixtures; unresolved/mismatched cases return failure")
    p.add_argument("--out", default="reports/engine_run.json")
    a = p.parse_args(argv)
    try:
        if not a.source.strip():
            raise ValueError("actual source provenance required")
        frame, digest = load_csv(a.data, as_of=a.as_of)
        result = run(frame, pair=a.pair, as_of=a.as_of, history_start=a.history_start, scan_start=a.scan_start,
                     origin_tf=a.origin_tf, entry_tf=a.entry_tf, level_mode=a.level_mode, stop_profile=a.stop_profile,
                     costs=Costs(a.spread_pips, a.stop_slippage_pips, a.commission_pips), pending_hours=a.pending_hours,
                     buffer_pips=a.buffer_pips, fixed_stop_pips=a.fixed_stop_pips)
        result["input"] = {"path": a.data, "sha256": digest, "declared_source": a.source}
        if a.examples:
            result["teacher_acceptance"] = evaluate(json.loads(Path(a.examples).read_text()), result["observations"])
    except (ValueError, TypeError, KeyError, OSError) as exc:
        result = {"status": "ERROR", "errors": [str(exc)]}
    target = Path(a.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    observations_path = target.with_name(target.stem + "_observations.json")
    observations_path.write_text(json.dumps(result.get("observations", []), indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("stories", "setups", "observations")}, indent=2))
    if result["status"] != "COMPUTED_SUPPORTED_ROUTES":
        return 1
    return 0 if not a.examples or result["teacher_acceptance"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
