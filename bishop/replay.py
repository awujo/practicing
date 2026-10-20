"""Strict acceptance checks for independently transcribed teaching examples.

This module compares engine observations, never manufactures them from expectations.
An incomplete example cannot pass. Source tolerances are explicit price units;
there is no global five-pip or multi-day relaxation.
"""
import argparse
import json
import math
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a timezone-aware ISO string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def _issues(ex):
    errors = []
    if ex.get("verification") == "verified" and ex.get("unresolved_reasons"):
        errors.append("verified example still has unresolved reasons")
    for key in ("id", "pair", "tf", "mode"):
        if not isinstance(ex.get(key), str) or not ex[key].strip():
            errors.append(f"missing {key}")
    if ex.get("verification") not in ("verified", "partial", "unresolved"):
        errors.append("invalid verification")
    if ex.get("kind") not in ("trade", "no_trade"):
        errors.append("invalid kind")
    if not isinstance(ex.get("evidence"), list) or not ex["evidence"]:
        errors.append("missing source evidence")
    elif any(not isinstance(e, dict) or not isinstance(e.get("path"), str) or not e["path"] for e in ex["evidence"]):
        errors.append("invalid source evidence")
    try:
        window = ex["time"]
        if _time(window["start"]) > _time(window["end"]):
            errors.append("inverted time window")
    except (KeyError, TypeError, ValueError):
        errors.append("missing or invalid time window")
    if ex.get("kind") == "trade":
        bias = ex.get("bias")
        if not isinstance(bias, dict) or bias.get("side") not in ("BUY", "SELL") or not isinstance(bias.get("tf"), str) or not bias["tf"]:
            errors.append("missing or invalid bias context")
        try:
            setup = ex["setup_time"]
            if _time(setup["start"]) > _time(setup["end"]):
                errors.append("inverted setup time window")
        except (KeyError, TypeError, ValueError):
            errors.append("missing or invalid setup time window")
        if ex.get("side") not in ("BUY", "SELL"):
            errors.append("invalid side")
        for key in ("entry", "stop", "target"):
            if not _number(ex.get(key)) or ex[key] <= 0:
                errors.append(f"missing or invalid {key}")
            tol = ex.get("tolerances")
            if not isinstance(tol, dict) or not _number(tol.get(key)) or tol[key] < 0:
                errors.append(f"missing or invalid {key} tolerance")
        if all(_number(ex.get(k)) for k in ("entry", "stop", "target")):
            ordered = ex["stop"] < ex["entry"] < ex["target"] if ex.get("side") == "BUY" else ex["target"] < ex["entry"] < ex["stop"]
            if not ordered:
                errors.append("invalid stop/entry/target ordering")
    return errors


def validate_examples(document):
    """Return structural errors; unresolved observations may lack trade fields."""
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        return ["expected schema_version 1"]
    examples = document.get("examples")
    if not isinstance(examples, list) or not examples:
        return ["examples must be a nonempty list"]
    errors, seen = [], set()
    for ex in examples:
        if not isinstance(ex, dict):
            errors.append("example must be an object")
            continue
        eid = ex.get("id")
        if not isinstance(eid, str) or not eid:
            errors.append("missing example id")
        elif eid in seen:
            errors.append(f"duplicate example id: {eid}")
        else:
            seen.add(eid)
        if ex.get("verification") not in ("verified", "partial", "unresolved"):
            errors.append(f"{eid}: invalid verification")
        if ex.get("verification") == "verified":
            errors.extend(f"{eid}: {e}" for e in _issues(ex))
    return errors


def check_example(example, candidates):
    """Check one source fixture against observations made by the engine."""
    result = {"id": example.get("id"), "status": "UNRESOLVED", "reasons": []}
    issues = _issues(example)
    if example.get("verification") != "verified" or issues:
        result["reasons"] = list(example.get("unresolved_reasons") or []) + issues
        if not result["reasons"]:
            result["reasons"] = ["source verification incomplete"]
        return result
    start, end = _time(example["time"]["start"]), _time(example["time"]["end"])
    matched, invalid = [], []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            invalid.append("candidate must be an object")
            continue
        dimensions = ("pair",) if example["kind"] == "no_trade" else ("pair", "tf", "mode")
        if any(candidate.get(k) != example[k] for k in dimensions):
            continue
        try:
            t = _time(candidate.get("time"))
        except ValueError:
            invalid.append("candidate has invalid time")
            continue
        if start <= t <= end:
            matched.append(candidate)
    result["status"] = "FAIL"
    if invalid:
        result["reasons"] = invalid
        return result
    if example["kind"] == "no_trade":
        # Absence of engine output is not proof the pair was evaluated.
        if any(c.get("status") in ("FILLED", "PENDING", "TRIGGERED", "APPROVED") for c in matched):
            result["reasons"] = ["engine traded or issued an actionable order inside a no-trade window"]
        elif any(c.get("status") == "NO_TRADE" and all(c.get(k) == example[k] for k in ("tf", "mode")) for c in matched):
            result["status"] = "PASS"
        else:
            result["reasons"] = ["no explicit no-trade observation in source window"]
        return result
    reasons = []
    for candidate in matched:
        mismatches = []
        if candidate.get("bias") != example["bias"]:
            mismatches.append("bias context differs")
        try:
            setup = _time(candidate.get("setup_time"))
            if not _time(example["setup_time"]["start"]) <= setup <= _time(example["setup_time"]["end"]):
                mismatches.append("setup time differs")
            if setup > _time(candidate["time"]):
                mismatches.append("setup was not available before fill")
        except ValueError:
            mismatches.append("invalid candidate setup time")
        for key in ("side",):
            if candidate.get(key) != example[key]:
                mismatches.append(f"{key} differs")
        if candidate.get("status") != "FILLED":
            mismatches.append("entry was not filled")
        for key in ("entry", "stop", "target"):
            actual = candidate.get(key)
            if not _number(actual):
                mismatches.append(f"invalid candidate {key}")
            elif abs(Decimal(str(actual)) - Decimal(str(example[key]))) > Decimal(str(example["tolerances"][key])):
                mismatches.append(f"{key} differs: expected {example[key]}, observed {actual}")
        if not mismatches:
            result["status"] = "PASS"
            return result
        reasons.append("; ".join(mismatches))
    result["reasons"] = reasons or ["no matching pair/timeframe/mode observation in source time window"]
    return result


def evaluate(document, candidates):
    errors = validate_examples(document)
    if not isinstance(candidates, list):
        errors.append("candidates must be a list of engine observations")
    if errors:
        return {"status": "FAIL", "errors": errors, "results": [], "counts": {"PASS": 0, "FAIL": 0, "UNRESOLVED": 0}}
    results = [check_example(ex, candidates) for ex in document["examples"]]
    counts = {s: sum(r["status"] == s for r in results) for s in ("PASS", "FAIL", "UNRESOLVED")}
    status = "FAIL" if counts["FAIL"] else "UNRESOLVED" if counts["UNRESOLVED"] else "PASS"
    return {"status": status, "results": results, "counts": counts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", default="tests/bishop_examples.json")
    parser.add_argument("--observations", required=True, help="JSON list exported by the engine")
    parser.add_argument("--out", default="reports/bishop_replay.json")
    args = parser.parse_args(argv)
    try:
        result = evaluate(json.loads(Path(args.examples).read_text()), json.loads(Path(args.observations).read_text()))
    except (OSError, ValueError, TypeError) as exc:
        result = {"status": "FAIL", "errors": [str(exc)]}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
