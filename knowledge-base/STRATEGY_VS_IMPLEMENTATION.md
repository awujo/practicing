# What the videos teach vs what the engine does

Built from the extracted frames and their transcript index, 2026-09-19.
Every row cites where it came from so it can be checked rather than
trusted. Written for the operator to correct.

Sources are `bishop-*` frame folders; `t=` values are seconds into that
video and are burned into the frames themselves.

---

## Confirmation entry triggers

He enumerates four (`entries-part5` 06:15: *"one of four things or three
things as the case may be"*).

| # | trigger | source | engine |
|---|---|---|---|
| 1 | **Breakout** in the intended direction | part5 t=390 *"you want price to give you a breakout"*; repeating-system t=735 *"we had what we want, a breakout that aligned"* | **missing** |
| 2 | **Sweep of liquidity + break of structure** | part5 t=405 | **missing** |
| 3 | **Open-close disrespect** (he calls this "engulfing") | part5 t=480-555; repeating-system t=750 *"an engulfed open close on the four hour"* | **wrong pattern** -- `is_engulfing()` is a classic candlestick engulfing |
| 4 | **4th man** | part5 t=600-675 | **correct** |

He rates 1 and 2 highest: *"personally I would tell you these two... if
you have these two, [missing it] is a missed entry"* (t=420).

### The 4th man is right

*"Price is going to come here and sweep out this guy, and then the high
should be standing"* (t=615); *"the low of this candle is [swept] and
the high is still standing, giving you a V-shape key level"* (t=675).

That is `fourth_man_confirmation_level()` exactly: `curr.low < prev.low`,
`curr.close > prev.low`, `curr.high < prev.high`, returning a V-shape.
The only thing in the entry path confirmed correct so far.

### The rejection is mandatory

*"My system says wait for a rejection. Even if my single candle is here,
I'm going to wait for price to actually reject... until you see that
rejection, there is no trade for you."* (repeating-system t=915-930)

The engine agrees -- a candidate needs a touch plus a trigger at the key
level.

---

## Liquidity

Not one thing (repeating-system t=270-345):

> *"I prefer to use single candle liquidity. You need to know that it's
> NOT ALL THE TIME your form of liquidity is going to be a single
> candle... a series, not always the immediate candle... Sometimes it's
> also going to be like STRUCTURAL liquidity... this is another form of
> liquidity right here."*

Repeated at t=960: *"it's not always going to be the immediate single
candle that price uses as liquidity."*

The engine implements the structural form only. The parked
`single_candle` mode implemented the other form only, REPLACING
structural rather than joining it -- likely why it measured worse.
`liquidity_mode="both"` now unions them and is awaiting an A/B.

---

## Targets

**The target is the liquidity. The R:R falls out of it.**

| frame | pair / TF | entry | stop | target | R:R |
|---|---|---|---|---|---|
| breakdown-3 t=1080 | USDJPY 3h | 160.391 | 160.323 | 160.725 | 4.9 |
| breakdown-3 t=870 | NZDCHF 2h | 0.46442 | 0.46328 | 0.46752 | 2.72 |

t=870 prints it on the chart: *"Risk/reward ratio: 2.72"*. Stated again
in words at part5 t=630 (*"buy way to our external liquidity"*) and
repeating-system t=720.

*"First target"* (repeating-system t=975, 1395; building-bias-2 t=1500,
where a swept **weekly high** is the target) means the NEAREST liquidity,
with more beyond -- not a partial exit. No partial/scale-out language
appears anywhere in the nine transcripts.

**Engine:** `target = min(3R, ERL)`. Right when the ERL is nearer than
3R -- it reproduces the 2.72R trade. Wrong when it is further: on the
USDJPY trade it takes 3R and leaves 1.9R behind. 3R should be the
fallback when no ERL qualifies, not a ceiling.

---

## Stops

*"Normally we put it in the wick of the engulfing candle, that [is] the
safest invalidation zone"* (operator, confirming the frames).

Both worked trades show the risk zone's lower edge just under the wick
of the candle preceding the entry -- not at a round number, not at the
open-close level.

**Engine:** stops are keyed per trigger; `engulfing_stop_loss` uses the
more extreme of TWO candles' wicks, which belongs to the
classic-engulfing reading being replaced.

---

## Entry timeframe

**Engine: H1 only.** The worked trades are on **3h** (t=1080) and **2h**
(t=870), and part5 t=345-360 lists *"your H3, your H2... H1, M30, M45,
even M15, even M5, it just depends on you."*

repeating-system t=750 also shows a confirmation taken *"on the four
hour... directly"*, so the entry timeframe is not even always below H4.

---

## Bias

Two statements that need reconciling with the engine, not one.

**(a) A timeframe's bias is the direction of its most recent breakout.**
*"My weekly is bullish. My daily -- the recent breakout was still to the
upside. At no point was there a bearish breakout. So we are still
[bullish]"* (repeating-system t=405).

The engine's `_aligned_timeframes()` does exactly this: most recent
confirmation on that timeframe, within a lookback.

**(b) A flip needs a higher-timeframe rejection plus a lower-timeframe
break.** *"This was that weekly rejection. I can see daily now later
confirmed it by breaking structure to the downside"* (repeating-system
t=570); *"after this sweep, your daily confirmed... gave you a breakout
to the downside"* (building-bias-2 t=885).

The engine's `BiasCascade.check_flip()` does this, with a third
condition.

**Open question:** the engine runs BOTH -- `bias_at()` from the flip
machine and `_aligned_timeframes()` from most-recent-breakout -- and an
entry must satisfy both. Whether that is two readings of one rule
(double-counted) or two genuine gates has not been established.

**Lower timeframe opposing a higher one is internal liquidity, not a
reversal.** *"We are still bearish on the weekly. For daily, switch to
bullish. It's possible to take out internal liquidity"* (building-bias-2
t=1110). The engine's strict Weekly > Daily > H4 priority matches.

---

## A checkable claim

`breakdown-3 t=750`, NZDCHF **4h**, June 2026: a 1px line at **0.46312**
anchored to a candle low around 4-5 June, swept around 10-11 June, which
he calls single candle liquidity.

Run `_find_liquidity_setups` on NZDCHF H4 for that week and see whether
0.46312 is armed. First specific taught level that can be checked
against the implementation instead of argued about.

---

## Status

Read: 6 of 42 contact sheets, 3 full-resolution frames, and targeted
index passages across all nine videos. Not yet read: most of
building-bias-1 and -2, daily-routine, what-next, bias-entries, and the
remainder of both breakdowns.
