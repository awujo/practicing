"""Reproduce the frozen one-pair engineering study, not teacher acceptance.

Run from repository root: python -m reports.reproduce_initial_study
No downloads, broker/DB calls, parameter search or source-fixture modifications.
"""
import json
from pathlib import Path
import time

from bishop.coverage import load_csv
from bishop.engine import run
from bishop.execution import Costs
from bishop.replay import evaluate

DATA = "data/examples/EURGBP_pdf_p08_icmarkets_bid_H1.csv.gz"
AS_OF = "2026-07-24T00:00Z"


def main():
    frame, digest = load_csv(DATA, as_of=AS_OF)
    rows = []
    for tf in ("H1", "H2"):
        for level in ("exact_junction", "close_reference"):
            for stop in ("structural_wick", "fixed_pips"):
                start = time.perf_counter()
                result = run(frame, pair="EURGBP", as_of=AS_OF, history_start="2026-06-01T00:00Z",
                             scan_start="2026-06-01T00:00Z", origin_tf="D", entry_tf=tf,
                             level_mode=level, stop_profile=stop, costs=Costs(1., .2, .5), pending_hours=24)
                rows.append({"entry_tf": tf, "level_mode": level, "stop_profile": stop,
                             "seconds": round(time.perf_counter() - start, 3), **result["summary"]})
                if (tf, level, stop) == ("H1", "close_reference", "structural_wick"):
                    save(result, digest, "eur_gbp_supported_routes")
    result = run(frame, pair="EURGBP", as_of=AS_OF, history_start="2026-06-01T00:00Z",
                 scan_start="2026-07-22T00:00Z", origin_tf="D", entry_tf="H2",
                 level_mode="close_reference", stop_profile="structural_wick", costs=Costs(1., .2, .5), pending_hours=24)
    result["teacher_acceptance"] = evaluate(json.loads(Path("tests/bishop_examples.json").read_text()), result["observations"])
    save(result, digest, "eur_gbp_source_window")
    Path("reports/initial_policy_comparison.json").write_text(json.dumps({
        "scope": "Predeclared one-pair engineering comparison; not teacher matches, selected operating rules, or portfolio returns",
        "engine_sha256": result["engine_sha256"], "input_sha256": digest, "runtime": result["runtime"], "rows": rows}, indent=2) + "\n")
    print(json.dumps({"comparison": rows, "source_window": result["summary"],
                      "teacher_acceptance": result["teacher_acceptance"]["status"]}, indent=2))


def save(result, digest, name):
    result["input"] = {"path": DATA, "sha256": digest,
                       "declared_source": "IC Markets cTrader BID public export at7bccddd; alternate to FOREXCOM teaching charts"}
    Path(f"reports/{name}.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    Path(f"reports/{name}_observations.json").write_text(json.dumps(result["observations"], indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
