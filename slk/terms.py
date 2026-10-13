"""/terms: short glossary of the words in our Telegram alerts (stdlib only; the Mini App web service answers the
command through its Telegram webhook, webapp/app.py)."""

TERMS = """SLK alert words

SELL · EURUSD · D1→H4 = direction · pair · origin TF → confirm TF (D1→H4 daily story, W1→D1 weekly, MN1→W1 monthly).
Key level (KL) = thin line where two candles turn, on body/close prices:
 • A-shape = peak (sell level) • V-shape = valley (buy level)
 • open-close (OC) = two same-colour candles, line at close 1 / open 2 • flipped = a broken level, opposite role.
Formed = the candle at whose close the level existed.
Tap / rejection candle = origin candle wicks into a fresh KL and closes back. Its trading day follows the 17:00 New York close (the D candle opening Wed 17:00 NY is Thursday's).
Sweep start = wick beyond the previous day/week high or low, close back inside (no KL).
Point B = last lower-TF V (sell) / A (buy) made before price first tapped the level.
External break = lower-TF BODY close beyond point B → confirms the bias. Internal breaks (after the tap) are for entries only.
Next Day Rule ✅ = the breakout came after the rejection candle closed. ⚠ same-day breakout = inside the rejection candle (lower probability).
Retrace ⚠ = later on the breakout day price closed back beyond B (flag only, not invalidated).
Early breakout = H4 broke B but the day has not closed yet: NOT confirmed (optional alert).
Trend aligned with W1/D1 = those TFs' trends agree with the direction.
Target = next opposite key level (same or higher TF) or swing liquidity (ERL). Invalid = origin close back through the level.
Rules: standard, sweep_start, flip, alignment (W→D→H4 breaks), cadjpy (no H4 breakout), +overlap (TP at the next KL).

Statuses:
 • TAPPED = level rejected, waiting for the breakout (NO_TRADE until then)
 • CONFIRMED = bias confirmed (not an entry)
 • TARGET_HIT • INVALIDATED • ENDED_FLIP (an opposite level on the way rejected + broke) • CANCELLED (no outcome in time)
 • NO_TRADE = filtered, e.g. M/W conflict.
Entries: Continuation (model A: 2-candle line, 3rd candle rejects, later breakout, limit on the retest) and QMR (Quasimodo Reversal). Bias alerts are never entry signals.
Times: your display_tz setting; each time says candle open or close."""


def is_terms(text):
    """True for '/terms' and '/terms@SomeBot' (optionally with arguments)."""
    head = str(text or "").strip().split(maxsplit=1)[0] if str(text or "").strip() else ""
    return head.split("@", 1)[0].lower() == "/terms"
