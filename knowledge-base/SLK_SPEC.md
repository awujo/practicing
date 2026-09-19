# SLK, as taught

One specification, assembled from the primary sources rather than from
the existing engine. Written 2026-09-19 after the full transcript pass
over both courses and the operator's corrections.

**Why this file exists.** The engine was built from transcripts alone,
by something that had never seen a chart, and the operator's verdict on
the result was that it is not SLK. Patching it one flag at a time
against its own numbers cannot fix that, because the baseline is the
thing in question. So this describes the taught system on its own
terms. Building it, and comparing whole system against whole system, is
the next step.

Sources: `knowledge-base/videos/*/transcript.txt` and the contact sheets
in `knowledge-base/frames/`. Bishop videos are `bishop-*`; the 4th man
main course is `video-01`..`video-18` plus `plug-and-play`. A `t=` is
seconds into that video, and since 2026-09-19 it identifies the frame
it is drawn on (see `extract_at_times()` for the bug that made that
untrue before).

**Division of labour**, in the operator's words: *"4th man videos are
more like the theory and teaching, while Bishop has implemented that
into a system."* So 4th man is authority on what a thing IS, Bishop on
how it is traded. Where they differ on practice, Bishop wins.

---

## 1. Bias

Three conditions, stated identically for both construction methods and
composable — *"you can build bias with both key levels and liquidity at
the same time"* (bias-2 t=1425).

**With key levels** (bias-1 t=390-405):
1. rejection off a higher-timeframe key level
2. candle closure
3. a breakout or break of structure on the next timeframe lower

**With liquidity** (bias-2 t=30-75):
1. a sweep of liquidity on a higher timeframe
2. candle closure
3. a breakout or break of structure on the next timeframe lower

### The breakout validates; it is not a level to trade back to

> *"Price doesn't necessarily have to come to your breakout or your
> break of structure level. **The aim of this is to validate your
> direction.**"* (bias-1 t=1140-1165; also t=1620, next t=720)

### The caveat: rejection instead of breakout pushes condition 3 down

> *"When you do not see a breakout on your daily timeframe, and instead
> you see one or two daily candles reject off that same particular
> zone ... you can then say, okay, daily is rejecting this weekly key
> level ... But then you absolutely [must] see your sweep and break or
> your breakout **on the next timeframe lower**."* (bias-1 t=780-855)

Condition 3 is never waived. It descends. Bishop refuses the trade when
it never appears (BTC, bias-1 t=1770-1785).

### Cascade, and when the weekly may be dropped

A lower-timeframe breakout that contradicts a higher timeframe is
ignored (bias-1 t=1260-1290, routine t=735-765). But when weekly and
daily persistently disagree, the weekly may be set aside:

> *"Weekly [is] saying bullish, [and] daily is now saying bearish. In
> that case those two timeframes are not in alignment, so [I] go to the
> four hours ... **I can leave the weekly, I use my daily and my four
> hours**, [and] I probably just target a good liquidity."* (routine
> t=390-435)

Confirmed as deliberate at next t=465: *"I built it from the daily
alone."* The **reduced target** is what makes it safe.

---

## 2. Liquidity

### IRL and ERL are a cycle

> *"Price moves from internal liquidity to external liquidity and back
> again. So it's a cycle."* (bias-2 t=210-225)

Bearish: the high above is internal, the low below external. Bullish:
mirrored (bias-2 t=240-300). ERL is always the direction being traded
toward.

### Single-candle and structural liquidity are one pool

Said twice, in two videos:

> *"Most times, your single candle liquidity on your daily is going to
> be a structural liquidity [on the lower timeframe]."* (bias-2 t=1140)

> *"This single candle on your daily timeframe -- on your four hour
> timeframe it's presented as a kind of [V] structure."* (bd2 t=825)

They are the same points at two zoom levels, not competing definitions.
Checked on the line chart every time: *"Look at your line charts. Your
line chart is your friend."* (bias-1 t=1050).

Not always the nearest candle: *"it's not always going to be the
immediate single candle that price uses as liquidity"* (repeat t=960,
also t=285, t=1215).

A third form is named but not elaborated: **trendline liquidity**,
*"all of these daily lows"* (bd2 t=1125).

### The breakout candle's own extremes are liquidity

Flagged twice (bias-2 t=795-885, t=1635-1665). Price routinely sweeps
the breakout candle's high or low and continues, taking out stops
placed naively behind it.

---

## 3. Key levels

Four shapes (bias-1 t=60-180):

| shape | used for | formed by |
|---|---|---|
| **V-shape** | buys | a swing low |
| **A-shape** | sells | a swing high |
| **bullish open-close** | buys | two consecutive candles whose open/close meet |
| **bearish open-close** | sells | as above, to the downside |

### Polarity flips on a close through

> *"This is what the key level should be used for **until they get
> disrespected**. The moment [price] can close above this guy --
> remember, this was supposed to be used for sales -- that's when we now
> use it for a buy, **or you can call it an engulfing**."* (bias-1
> t=195-300)

Applies to **all four shapes**, not just open-close.

### QMR = Quasimodo

The operator supplied the pattern directly. Bullish: `L -> H -> LL
(below L) -> HH (above H) -> return to the LEFT SHOULDER LEVEL, which
is the price of the original L -> buy`. Bearish is mirrored: `H -> L ->
HH -> LL -> return to the original H -> sell`.

So a QMR key level is the left shoulder, and it is an A-shape or a
V-shape. 4th man states it as such:

> *"a QMR key level, **which is an A-shaped key level that is
> overlapping inside of an imbalance**"* (video-14 t=180-189)

---

## 4. The setup

plug-and-play t=791-955, the clearest entry statement in either course.
An A-shaped or V-shaped key level that:

1. **sponsored a move** — *"that A-shaped key level must have sponsored
   some level of sales ... price rejected from here, it gives to us some
   heavy momentum sales"* — i.e. it previously worked
2. was then **disrespected** — price closed through it
3. **overlaps an imbalance**
4. has **liquidity resting beyond it**

Video 17's "tested and respected before being disrespected" is
condition 1, not a separate ranking rule.

### Origin and continuation

Operator's clarification, which supersedes my earlier reading:

> *"Origin of a trade is when we enter the trade at the right point
> we're meant to enter it. Continuations are mostly plug and play. When
> we miss the first move, price can [run] up to our intended direction
> and [leave an] imbalance, so we want price to come and take out the
> liquidity, [re]balancing the old imbalance, at a specific key level.
> That is where the plug and play comes in."*

So:

- **origin** — the first entry, taken at the point it was meant to be taken
- **continuation** — the second chance after missing the first move:
  price has run, leaving an imbalance behind; wait for it to return,
  take the liquidity, rebalance that imbalance at a key level

4th man claims *"this continuation set up has over like a 70 to 80% win
rate"* (video-14 t=296-301, repeated t=361-366) and that the
retracement after an impulsive break of the ERL is **shallow**, not deep
(t=324-330).

**The engine's `plug_and_play` label is the continuation entry.** Same
concept, same word.

---

## 5. The confirmation entry

**Precondition, on H4:** internal range liquidity taken, and price has
played the QMR key level.

**Then drop one timeframe:** *"I will always recommend one hour or 30
minutes"* (video-14 t≈460). Bishop descends further when needed — H1 ->
45m -> 30m -> 15m until a confirmation appears (repeat t=1185-1200, and
four more videos).

Three variants, and 4th man is explicit that it *"is not going to be
more than these three things"*. All quotes video-14, bearish case;
mirror for bullish.

### 5.1 Engulf, then direct mitigation

> *"price is going to engulf and after price engulfs, price is going to
> play a direct mitigation of that particular A shape key level ... and
> price will continue to move into our anticipated direction"*

The engulfing move itself creates a new A-shape on the line chart.
Entry is the **return** to it, not the engulfing candle.

### 5.2 Engulf, plus a broken open-close

> *"price is going to create for us two consecutive up candles that is
> going to create for us an open close key level ... price will not just
> engulf, price is going to break below the ... open close key levels
> that was created by these two consecutive up candles ... Come back to
> this open close key level that was broken and price will continue to
> drop."*

This is exactly `open_close_disrespect_entry()` as built — two same-
direction candles form the level, a later candle closes through it,
price returns to it, and that return is the entry.

**Stop:** *"just going to be a little bit above this particular high."*

### 5.3 Engulf, then the next candle is inducement

> *"After price engulfs, the next one hour or 30 minutes candle is going
> to trade very close to the V shape or the A shape key level. But it's
> not going to tap into it, which means that this next ... candle is
> going to serve as our internal range liquidity. So ... we want to see
> price attack that liquidity, play out from this particular key level
> and price will continue to move to the downside."*

The near-miss candle becomes the liquidity. Price sweeps it, then plays
the key level. This is the 4th-man pattern in its general form.

> *"As it is in the origin of a trade, so it is in this particular
> continuation."*

### Bishop's four triggers map onto these

Bishop enumerates breakout, sweep+break, engulfing (= engulfed
open-close key level), and 4th man (next t=375-405, part5 06:15). He
rates the first two highest: *"if you have these two, [missing it] is a
missed entry"* (part5 t=420).

`5.2` is his "engulfing". `5.3` is his 4th man. His breakout and
sweep+break are not among 4th man's three, and are the two the engine
does not implement at all.

### The rejection is mandatory

> *"My system says wait for a rejection. Even if my single candle is
> here, I'm going to wait for price to actually reject ... until you see
> that rejection, there is no trade for you."* (repeat t=915-930)

But the level need not be the exact nearest one (bd2 t=570).

---

## 6. Stops

**Operator's instruction, explicit:** *"I'm not using a kind of fixed
range of stop loss like [4th man]. For my stop loss placement, go to
what Bishop is doing ... We are placing it at invalidation zones —
setup invalidation zones."*

So 4th man's *"10 to 11 pips is enough"* (video-14 t=349-354) is
recorded as his practice and **is not the rule here**.

Bishop's placement:
- confirmation entry: in the wick of the confirming candle — *"the
  safest invalidation zone"* (operator); next t=435 *"stop loss just
  above this high"*; next t=930
- 4th man variant: above the high that was swept
- open-close variant: *"a little bit above this particular high"*
  (video-14, 5.2 above)
- direct entry, no confirmation: wider — *"your stop loss should
  actually cover this key level to be safe"* (next t=285-300)

The principle behind all of them: the stop sits where the **setup is
invalidated**, which is beyond the structure that defines it.

---

## 7. Targets

**The target is the external liquidity.** Seven statements, no
counter-evidence:

| source | words |
|---|---|
| entries t=330 | *"the target should always be external liquidity"* |
| bd2 t=615-645 | *"no logical reason for you holding all the way [past] this liquidity ... after external liquidity is taken, expect a reversal"* |
| bias-2 t=900-930 | *"your first exit for your sale should be here"* |
| bias-2 t=1665 | *"at least this liquidity should have been your target"* |
| bias-2 t=1500 | a swept weekly high named as first target |
| repeat t=975 | *"this was meant to be my first target"* |
| bd2 t=375 | *"look for confirmation entry to be in this particular external liquidity first"* |

It is a **floor and a ceiling**: run to the first ERL, and do not hold
through it.

R multiples are outputs, never targets — 2.72R, 3.4R, 3.6R, 4R, 4.9R,
5R, 5.6R, 5.9R, 6R, *"almost 7R"* across the worked trades.

Two measured examples, read off full-resolution frames:

| frame | pair / TF | entry | stop | target | R:R |
|---|---|---|---|---|---|
| bd3 t=1080 | USDJPY 3h | 160.391 | 160.323 | 160.725 | 4.9 |
| bd3 t=870 | NZDCHF 2h | 0.46442 | 0.46328 | 0.46752 | 2.72 |

---

## 8. What the engine does differently

| # | taught | engine |
|---|---|---|
| 1 | target IS the ERL | `min(3R, ERL)` — truncates every trade above 3R |
| 2 | "engulfing" = engulfed open-close key level | `is_engulfing()`, a candlestick engulfing |
| 3 | disrespect applies to all four shapes | open-close only (and not wired in) |
| 4 | breakout + sweep/break confirmations, rated highest | absent |
| 5 | confirmation on H1/45m/30m/15m | H1 only |
| 6 | setup = 4 conditions incl. imbalance overlap | primitives all exist, none composed |
| 7 | origin vs continuation are different trades | `origin_kind="any"` |
| 8 | daily-only bias with reduced target | absent |
| 9 | stop at the setup's invalidation zone | per-trigger, and #2's is built on the wrong pattern |

---

## 9. Open, and honestly

- The only measurement of condition 3 (imbalance overlap) says it
  **underperforms** — 46.3% win vs 51.7%, 0.786 R/trade vs 0.990, on
  2026-09-02. That run predates the look-ahead fix and both columns are
  inflated, so it settles nothing, but it is not encouraging and should
  not be hidden.
- Tighter stops measured badly on the same broken engine: median 9.4 ->
  7.7 pips but win rate 51.7% -> 38.0%.
- Nothing in this document has been measured on the fixed engine.
- Bishop's breakout and sweep+break confirmations are described but not
  yet specified here precisely enough to build. They need the frames.
