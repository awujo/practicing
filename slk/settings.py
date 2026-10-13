"""Strategy settings stored in DB table `settings` (k, v as strings). One schema for slk/live.py (builds the
engine cfg) and the Mini App (validates + renders the Settings form via /api/settings/schema).

Dependency-free on purpose (stdlib only): the web app imports it without pandas. Defaults = Kevin's rules and
must match slk.story.DEFAULT / slk.entry.DEFAULT (tests/test_settings.py checks this).
"""
import re

PAIRS = ("EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCAD USDCHF EURGBP EURJPY EURAUD EURCAD EURCHF EURNZD "
         "GBPJPY GBPAUD GBPCAD GBPCHF GBPNZD AUDJPY AUDCAD AUDCHF AUDNZD NZDJPY NZDCAD NZDCHF CADJPY "
         "CADCHF CHFJPY").split()
STORY_KEYS = ("D", "W", "M")
TF_ORDER = ("H1", "H2", "H4", "D", "W", "M")
ORIGIN = {"D": "D", "W": "W", "M": "M"}
DEFAULT_LADDER = {"D": ("H4", "H2", "H1"), "W": ("D", "H4"), "M": ("W", "D")}
GROUPS = ("Markets", "Bias rules", "Entry rules", "Risk & trading", "Alerts")


def _s(name, type_, default, group, help_, **kw):
    return {"name": name, "type": type_, "default": default, "group": group, "help": help_, **kw}


# type: bool ("on"/"off"), int, float, choice (one of choices), multi (subset of choices, CSV),
# pairs (CSV of symbols, `choices` = suggestions), ladder ("D=H4,H2,H1;W=D,H4;M=W,D")
SCHEMA = [
    _s("pairs", "pairs", "", "Markets", "Pairs the bot watches. Empty = all 28.", choices=PAIRS),
    _s("stories", "multi", "D,W,M", "Markets", "Story timeframes: Monthly, Weekly, Daily.",
       choices=["M", "W", "D"]),
    _s("trend_filter", "bool", "on", "Bias rules", "Only levels that agree with the origin-TF trend."),
    _s("htf_filter", "bool", "on", "Bias rules", "Never trade against the higher-TF trend."),
    _s("mw_conflict_filter", "bool", "on", "Bias rules", "M and W disagree -> Daily stories are NO_TRADE."),
    _s("max_wait", "int", "5", "Bias rules", "Origin bars from tap to breakout before the story is dropped.",
       min=1, max=20),
    _s("max_retaps", "int", "3", "Bias rules", "More re-taps before the breakout = messy level, skip.",
       min=0, max=10),
    _s("tap_tol_pips", "float", "1", "Bias rules", "A wick this close to the line (pips) counts as a tap.",
       min=0, max=5),
    _s("use_oc", "bool", "on", "Bias rules", "Draw levels on open/close (line chart), not wicks."),
    _s("most_recent_level", "bool", "on", "Bias rules",
       "Only the most recent fresh key level (formed before the tap) can start a story; an older level tapped "
       "while a newer fresh one exists is ignored (Kevin: 'mark the most recent one, remove everything else', "
       "story-line-pt2@897-1000)."),
    _s("flip_end", "bool", "on", "Bias rules",
       "Story ends early (ENDED_FLIP) when, on the way to the target, price taps an opposite daily key level, "
       "rejects it with a close the other way AND H4 breaks that level's point B the other way; the opposite "
       "story may then start (story-line-pt2@1779-1832)."),
    _s("htf_targets", "bool", "on", "Bias rules",
       "Target = next opposite fresh key level of the same OR a higher timeframe (W/M for a daily story), or the "
       "swing liquidity (ERL), whichever comes first (story-line@648, class-wrok@480-620). Off = origin TF only."),
    _s("overlap_rule", "bool", "on", "Bias rules",
       "Exception (a) overlap: the daily level is also a fresh weekly level rejected by a CLOSED weekly candle "
       "-> 'daily reject daily', take profit at the next key level instead of swinging (all-in-1@1424-1620). "
       "Kevin uses it in class: on."),
    _s("overlap_tol_pips", "float", "3", "Bias rules",
       "Overlap: two timeframes' levels within this many pips are 'the same spot' (our choice; Kevin: must be "
       "exactly the same spot).", min=0, max=20),
    _s("alignment_start", "bool", "on", "Bias rules",
       "Exception (b) alignment/continuation: weekly close beyond the last weekly swing, then a daily close beyond "
       "the last daily swing and an H4 break the same way = daily continuation story. Without that alignment no "
       "continuation story (weekly-recap@151-282, 626-670, 2098-2160). Kevin uses it: on."),
    _s("cadjpy_exception", "bool", "on", "Bias rules",
       "Exception (c) CADJPY: weekly trend in the story direction + the daily already flipped that way (a daily "
       "close through an opposite key level in the last max_wait days) + the daily candle sweeps the previous day "
       "low (high) into a daily open-close level and closes back -> daily bias confirmed at that close WITHOUT an "
       "H4 breakout, target the previous high (low) (cadjpy-bd@400-995). Kevin uses it: on. Off = H4 breakout "
       "always required."),
    _s("entry_tfs", "ladder", "D=H4,H2,H1;W=D,H4;M=W,D", "Entry rules",
       "Entry timeframes per story, tried in this order (lower than the story TF)."),
    _s("continuation_entries", "bool", "on", "Entry rules",
       "Entry alerts on/off (all entry models), taken only after the story is confirmed. "
       "External break = confirms direction (bias). Internal break = continuation entries only."),
    _s("entry_models", "multi", "continuation,qmr", "Entry rules",
       "Entry models. continuation = 2 candles make an A/V line, the 3rd rejects it with a wick, a later "
       "candle breaks out, entry on the retest. qmr = Quasimodo Reversal: shoulder, head sweeps beyond it, "
       "neck broken; wait for price back in the shoulder/neck zone, a 1H breakout, then the retest. "
       "A pending QMR is not replaced by a newer continuation level.",
       choices=["continuation", "qmr"]),
    _s("breakout_max_bars", "int", "0", "Entry rules",
       "Continuation: the breakout may be the 4th candle or ANY later one (Kevin sets no limit). "
       "0 = no limit (default). Set a number to only accept a breakout within that many candles after the "
       "rejection candle (1 = 4th candle only). A close back through the line before it cancels the level.",
       min=0, max=100),
    _s("skip_first_retracement", "bool", "on", "Entry rules",
       "Ignore patterns formed before the top of the first retracement after the breakout."),
    _s("max_stop_pips", "float", "20", "Entry rules", "Wider stop = the pattern does not qualify.",
       min=5, max=50),
    _s("tp1_rr", "float", "1.5", "Entry rules", "Minimum reward:risk for TP1.", min=0.5, max=5),
    _s("avoid_pairs", "pairs", "AUDNZD,NZDCHF", "Entry rules", "No entries on these pairs (wide spread).",
       choices=PAIRS),
    _s("kill_switch", "choice", "off", "Risk & trading", "On = no new orders are placed.", choices=["off", "on"]),
    _s("auto_trade", "choice", "off", "Risk & trading",
       "off = alerts only, confirm = you approve each entry, auto = bot places orders.",
       choices=["off", "confirm", "auto"]),
    _s("risk_pct", "float", "0.5", "Risk & trading", "Account % risked per trade.", min=0.1, max=2),
    _s("alert_tapped", "bool", "on", "Alerts", "Telegram when a level is tapped (waiting for breakout)."),
    _s("alert_confirmed", "bool", "on", "Alerts", "Telegram when a story is confirmed."),
    _s("alert_ended", "bool", "on", "Alerts", "Telegram when a story hits target or is invalidated."),
    _s("alert_entry", "bool", "on", "Alerts", "Telegram on new / triggered entries."),
    _s("daily_summary", "bool", "on", "Alerts", "Daily bias summary after the 17:00 New York close."),
    _s("status_updates", "choice", "every_4h", "Alerts",
       "'Bot alive' message: time, pairs checked, active biases, pending entries, start delay, run time, errors. "
       "each_run = every hourly run, every_4h = at most every 4 hours (errors are always reported), off = never. "
       "A failed run is always reported by the workflow.",
       choices=["each_run", "every_4h", "off"]),
]
BY_NAME = {s["name"]: s for s in SCHEMA}
DEFAULTS = {s["name"]: s["default"] for s in SCHEMA}
TRUE, FALSE = ("on", "true", "1", "yes"), ("off", "false", "0", "no")


def _csv(v):
    if isinstance(v, (list, tuple)):
        v = ",".join(map(str, v))
    return [x.strip().upper() for x in re.split(r"[,\s;]+", str(v)) if x.strip()]


def _ladder(v):
    """'D=H4,H2,H1;W=D,H4' (or dict) -> {story: [tfs]}; raises ValueError."""
    if isinstance(v, dict):
        items = v.items()
    else:
        items = []
        for part in str(v).split(";"):
            if part.strip():
                if "=" not in part and ":" not in part:
                    raise ValueError(f"'{part.strip()}' must look like D=H4,H2,H1")
                k, _, tfs = part.replace(":", "=", 1).partition("=")
                items.append((k, tfs))
    out = {}
    for k, tfs in items:
        k = str(k).strip().upper()
        if k not in STORY_KEYS:
            raise ValueError(f"unknown story '{k}'")
        tl = list(dict.fromkeys(_csv(tfs)))
        if not tl:
            raise ValueError(f"story {k} needs at least one entry TF")
        for tf in tl:
            if tf not in TF_ORDER or TF_ORDER.index(tf) >= TF_ORDER.index(ORIGIN[k]):
                raise ValueError(f"{tf} is not a TF below {k}")
        out[k] = tl
    return {k: out.get(k, list(DEFAULT_LADDER[k])) for k in STORY_KEYS}


def clean(name, value):
    """Validated canonical string for one setting; raises ValueError (message names the key)."""
    s = BY_NAME.get(name)
    if s is None:
        raise ValueError(f"unknown setting '{name}'")
    t = s["type"]
    try:
        if t == "bool":
            v = str(value).strip().lower() if not isinstance(value, bool) else ("on" if value else "off")
            if v in TRUE:
                return "on"
            if v in FALSE:
                return "off"
            raise ValueError("must be on/off")
        if t in ("int", "float"):
            if isinstance(value, bool):
                raise ValueError("must be a number")
            x = float(str(value).strip())
            if x != x or (t == "int" and x != int(x)):
                raise ValueError(f"must be {'a whole number' if t == 'int' else 'a number'}")
            if x < s["min"] or x > s["max"]:
                raise ValueError(f"must be between {s['min']:g} and {s['max']:g}")
            return str(int(x)) if t == "int" else f"{x:g}"
        if t == "choice":
            v = str(value).strip().lower()
            if v not in s["choices"]:
                raise ValueError("must be one of " + "/".join(s["choices"]))
            return v
        if t == "multi":
            canon = {x.upper(): x for x in s["choices"]}  # choices keep their own case (D / qmr)
            v = _csv(value)
            bad = [x for x in v if x not in canon]
            if bad:
                raise ValueError("must be from " + ",".join(s["choices"]))
            v = [canon[x] for x in v]
            if not v:
                raise ValueError("pick at least one")
            if name == "stories":  # canonical order D,W,M (as before); none = nothing to watch
                return ",".join(x for x in ("D", "W", "M") if x in v)
            return ",".join(x for x in s["choices"] if x in v)
        if t == "pairs":
            v = _csv(value)
            bad = [x for x in v if not re.fullmatch(r"[A-Z0-9]{3,12}", x)]
            if bad:
                raise ValueError("bad pairs: " + ", ".join(bad))
            return ",".join(dict.fromkeys(v))
        if t == "ladder":
            lad = _ladder(value)
            return ";".join(f"{k}={','.join(lad[k])}" for k in STORY_KEYS)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name}: {e}") from None
    raise ValueError(f"{name}: unknown type {t}")


def clean_all(changes):
    """dict of raw values -> dict of canonical strings. Raises ValueError on the first bad key."""
    if not isinstance(changes, dict):
        raise ValueError("settings must be an object")
    return {k: clean(k, v) for k, v in changes.items() if v is not None}


def parse(name, text):
    """Stored string -> typed value. A bad or missing stored value falls back to the default."""
    s = BY_NAME[name]
    try:
        v = s["default"] if text is None or (str(text) == "" and s["type"] != "pairs") else clean(name, text)
    except ValueError:
        v = s["default"]
    t = s["type"]
    if t == "bool":
        return v == "on"
    if t == "int":
        return int(v)
    if t == "float":
        return float(v)
    if t == "multi":
        return [x for x in v.split(",") if x]
    if t == "pairs":
        return _csv(v)
    if t == "ladder":
        return _ladder(v)
    return v


def load(stored=None):
    """{name: typed value} for every schema key, from a dict of stored strings (missing -> default)."""
    stored = stored or {}
    return {s["name"]: parse(s["name"], stored.get(s["name"])) for s in SCHEMA}


def as_strings(stored=None):
    """{name: string} for every schema key (stored if valid, else default) - what the Mini App shows."""
    stored = stored or {}
    out = {}
    for s in SCHEMA:
        v = stored.get(s["name"])
        try:
            out[s["name"]] = s["default"] if v is None or (v == "" and s["type"] != "pairs") else clean(s["name"], v)
        except ValueError:
            out[s["name"]] = s["default"]
    return out


def story_cfg(vals):
    """Overrides of slk.story.DEFAULT from load() output."""
    return {k: vals[k] for k in ("trend_filter", "htf_filter", "mw_conflict_filter", "max_wait",
                                 "max_retaps", "tap_tol_pips", "use_oc", "most_recent_level", "flip_end",
                                 "htf_targets", "overlap_rule", "overlap_tol_pips", "alignment_start",
                                 "cadjpy_exception")}


def entry_cfg(vals):
    """Overrides of slk.entry.DEFAULT from load() output."""
    return {"entry_tfs": {k: tuple(v) for k, v in vals["entry_tfs"].items()},
            "max_stop_pips": vals["max_stop_pips"], "tp1_min_rr": vals["tp1_rr"],
            "avoid_pairs": list(vals["avoid_pairs"]), "skip_first": vals["skip_first_retracement"],
            "entry_models": list(vals["entry_models"]), "breakout_max_bars": vals["breakout_max_bars"]}


def schema_json():
    return {"groups": list(GROUPS), "settings": [dict(s, choices=list(s["choices"])) if "choices" in s else dict(s)
                                                  for s in SCHEMA]}
