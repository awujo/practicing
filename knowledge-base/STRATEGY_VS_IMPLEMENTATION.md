# What the videos teach vs what the engine does

Built from the extracted frames and their transcript index, 2026-09-19.
Every row cites where it came from so it can be checked rather than
trusted. Written for the operator to correct.

Sources are `bishop-*` frame folders; `t=` values are seconds into that
video and are burned into the frames themselves. Short names used
below: `part5` = entries-part5, `repeat` = repeating-system, `bias-1`
and `bias-2` = building-bias-1 / -2, `routine` = daily-routine,
`next` = what-next, `entries` = bias-entries, `bd2` / `bd3` =
trades-breakdown-2 / -3.

---

## The system in one paragraph

He states it as a checklist four separate times, in the same order
every time:

> *"On the four hour I want to see a breakout. I want to see single
> candle liquidity. I want to see that liquidity swept. Then a
> confirmation entry. Until all of this happened I wasn't even
> interested at all."* (routine t=975-990)

Same list at next t=225-240, entries t=135, repeat t=105-135. The last
of those adds the step that matters most and is easiest to drop:
after the liquidity is swept you *play the closest key level to it*,
and **you wait for a rejection from that key level** before the
confirmation entry.

Everything below is detail on one of those five steps.

---

## Confirmation entry triggers

He enumerates them on a drawing at next t=375-405 and again at part5
06:15 (*"one of four things or three things as the case may be"*).

| # | trigger | source | engine |
|---|---|---|---|
| 1 | **Breakout** in the intended direction | part5 t=390; repeat t=735; next t=390 | **missing** |
| 2 | **Sweep of liquidity + break of structure** | part5 t=405; next t=390; repeat t=1200 | **missing** |
| 3 | **Open-close disrespect** ("engulfing") | part5 t=480-555; next t=390 *"an engulfing, that's an engulfed open close key level"* | **wrong pattern** -- `is_engulfing()` is a classic candlestick engulfing |
| 4 | **4th man** | part5 t=600-675; next t=810 | **correct** |

He rates 1 and 2 highest: *"personally I would tell you these two... if
you have these two, [missing it] is a missed entry"* (part5 t=420).

### "Engulfing" is confirmed, and it is broader than I built it

Three independent statements, and they agree with the operator's own
wording exactly:

> *"You also have your engulfed open close key level. You want to see
> price close above this key level. And then you now want to see price
> come into this level and then buy to the upside."* (repeat t=195-210)

> *"On your lower timeframe you can use a breakout or a break of
> structure as your confirmation entry. You can also use an engulfing,
> that's an engulfed open close key level."* (next t=390)

> *"We engulfed this bearish open close key level at this particular
> point."* (repeat t=540)

`open_close_disrespect_entry()` implements this. **But bias-1
t=195-300 generalises it past open-close levels**, and I built the
narrow version:

> *"Let's say you have a candle close below this V-shaped key level.
> This key level will no longer be used for buys. Instead this key
> level is going to be used for [sells]... If price closes above your
> A-shaped key level, it is no longer going to be used for sales.
> Instead price is going to come here and then use this level for a
> buy. And the same idea still applies to your open-close key levels
> as well... This is what the key level should be used for **until
> they get disrespected**. The moment [price] can close above this
> guy -- remember, this was supposed to be used for sales -- that's
> when we now use it for a buy, **or you can call it an engulfing**."*

So the taught rule is: **any key level that price closes through flips
polarity, and the flipped level is then traded from the other side.**
V-shape, A-shape and open-close all qualify. `open_close_disrespect_entry`
covers one of the three.

### The 4th man is right, and is named

*"Price is going to come here and sweep out this guy, and then the high
should be standing"* (part5 t=615); *"the low of this candle is [swept]
and the high is still standing, giving you a V-shape key level"*
(part5 t=675). Attributed by name at next t=810:

> *"...this particular style of confirmation entry, whereby the high of
> the candle was swept and then the low was still standing, **as
> introduced by fourth man**."*

That is `fourth_man_confirmation_level()` exactly: `curr.low <
prev.low`, `curr.close > prev.low`, `curr.high < prev.high`, returning
a V-shape. Still the only thing in the entry path confirmed correct.

### The rejection is mandatory

> *"My system says wait for a rejection. Even if my single candle is
> here, I'm going to wait for price to actually reject... until you see
> that rejection, there is no trade for you."* (repeat t=915-930)

The engine agrees -- a candidate needs a touch plus a trigger at the
key level.

But the key level does not have to be the exact nearest one. bd2 t=570:
*"[I expected] price to use this key level. But instead it [went to a
level below]. And that's not a problem for me, because I just want to
see a rejection after that."* And entries t=435: *"price likes using
the closest key levels"* -- a tendency, not a rule.

---

## Liquidity

Not one thing (repeat t=270-345):

> *"I prefer to use single candle liquidity. You need to know that it's
> NOT ALL THE TIME your form of liquidity is going to be a single
> candle... a series, not always the immediate candle... Sometimes it's
> also going to be like STRUCTURAL liquidity... this is another form of
> liquidity right here."*

Repeated at repeat t=960 and t=1215.

### The two forms are the same thing at different resolutions

This is the sentence that settles the `single_candle` vs `swing`
argument, and he says it twice in two different videos:

> *"Most times, your single candle liquidity on your daily is going to
> be a structural liquidity [on the lower timeframe]."* (bias-2 t=1140)

> *"This single candle on your daily timeframe -- on your four hour
> timeframe it's presented as a kind of [V] structure. If you can
> observe it."* (bd2 t=825)

And he checks it visually every time: *"Look at your line charts. Your
line chart is your friend."* (bias-1 t=1050; also repeat t=330, t=1170,
entries t=120).

So single-candle and structural are not competing definitions to A/B
against each other. They are one pool seen at two zoom levels, which
is what `liquidity_mode="both"` unions. The parked `single_candle`
mode REPLACED structural rather than joining it -- that is very likely
why it measured worse, and the `both` A/B is the real test.

### A third form, not implemented

*"Trend line liquidity on the daily timeframe, all of these daily
lows"* (bd2 t=1125). Noted, not built.

### IRL and ERL

> *"The logic on liquidity is that price moves from internal liquidity
> to external liquidity and back again. So it's a cycle."* (bias-2
> t=210-225)

Definition depends on the trend (bias-2 t=240-300): bearish -- the high
above is internal, the low below is external. Bullish -- the low below
is internal, the high above is external. So ERL is always *the
direction you are trading toward*, which is what the engine assumes.

Corollary he flags twice, which the engine does not model: **the
breakout candle's own high and low are liquidity** (bias-2 t=795-885,
t=1635-1665). Price routinely sweeps the breakout candle's extreme and
continues, taking out stops placed naively behind it.

---

## Targets

**The target is the liquidity. The R:R falls out of it.** This is now
the best-evidenced rule in the whole set -- seven statements, no
contradiction:

| source | words |
|---|---|
| entries t=330 | *"Once the external liquidity is taken, expect a reversal. So **the target should always be external liquidity**."* |
| bd2 t=615-645 | *"There was no logical reason for you holding all the way [past] this liquidity, because this is an external liquidity. Price tends to reverse. So after external liquidity is taken, expect a reversal."* |
| bias-2 t=900-930 | *"**Your first exit for your sale should be here**, because price can get in here, react from this key level and then continue buying and may never get into this point."* |
| bias-2 t=1665 | *"It makes sense if you were targeting any sell, at least this liquidity should have been your target."* |
| bias-2 t=1500 | a swept **weekly high** named as the first target |
| repeat t=975 | *"this was meant to be my first target"* |
| bd2 t=375 | *"it makes sense to look for confirmation entry to be in this particular external liquidity first"* |

Two things follow.

**It is a floor, not a ceiling.** The R multiples he reads off finished
trades are 3.4R (next t=300), 3.6R (next t=345), 4R and 5R (bd2 t=330),
5.6R (routine t=2205), 5.9R (bd2 t=420), 6R and *"almost 7R"* (bd2
t=1170). None of these is a target he set; each is what the distance to
liquidity happened to be worth.

**It is also a stop.** bd2 t=615 explicitly rules out holding through
the first ERL for a bigger number.

**Engine:** `target = min(3R, ERL)`. Right when the ERL is nearer than
3R -- it reproduces the 2.72R trade in the table below. Wrong when it
is further, which on this evidence is most of the time: every trade he
walks through at 4R and up is one our engine would have closed at 3R.
**3R should be the fallback when no ERL qualifies, not a ceiling.**
The `capped` column in the backtest output counts exactly these.

| frame | pair / TF | entry | stop | target | R:R |
|---|---|---|---|---|---|
| bd3 t=1080 | USDJPY 3h | 160.391 | 160.323 | 160.725 | 4.9 |
| bd3 t=870 | NZDCHF 2h | 0.46442 | 0.46328 | 0.46752 | 2.72 |

t=870 prints it on the chart: *"Risk/reward ratio: 2.72"*.

---

## Stops

*"Normally we put it in the wick of the engulfing candle, that [is] the
safest invalidation zone"* (operator, confirming the frames). The
videos agree and add the non-confirmation case:

- confirmation entry: next t=435 *"stop loss just above this high"*;
  next t=930 *"stop loss would have been just a little bit around this
  level"*
- direct entry (no confirmation): next t=285-300 *"logically your stop
  loss should actually cover this key level to be safe"* -- i.e. behind
  the whole level, wider, and he quotes 3.4R on that basis

Both worked trades show the risk zone's lower edge just under the wick
of the candle preceding the entry -- not at a round number, not at the
open-close level.

**Engine:** stops are keyed per trigger; `engulfing_stop_loss` uses the
more extreme of TWO candles' wicks, which belongs to the
classic-engulfing reading being replaced.

---

## Entry timeframe

**Engine: H1 only.** This is wrong in both directions.

**Downward.** He descends a ladder until a confirmation appears:

> *"There was no exact confirmation on the one hour. 45 minutes either.
> Only 30 minutes... [I] actually went as low as the 15 minutes,
> whereby he now gave a sweep and break to the upside."* (repeat
> t=1185-1200)

Same descent at repeat t=1245, repeat t=1455-1470, bd2 t=1035-1050
(*"45 minutes... about 30 minutes... on almost all of my preferred
lower timeframes"*), routine t=2145-2175, next t=510 (2h). His own
entries land on 15m (repeat t=525), 30m (bd2 t=1170), 2h, 3h.

**Upward.** repeat t=750: a confirmation taken *"on the four hour...
directly"*; next t=420 *"there are people that actually trade four
hour rejects four hour"*.

An H1-only engine therefore misses every setup whose confirmation
prints below H1 -- and by his own commentary that is a large fraction
of them, because he reaches for 30m and 15m constantly.

He also notes the fractal repeat: *"if you see this on the four hour,
on your two hour timeframe you're going to see this engulfing. If you
see it on the one hour, on the 30 minutes [likewise]"* (repeat t=225).

One more, relevant to `close_based_sweep_break`: *"personally, I don't
exactly wait for the candle to close, but that is personal"* (entries
t=630). He flags it as a personal deviation, not the rule.

---

## Bias

### The three conditions

Stated identically for both construction methods:

**With key levels** (bias-1 t=390-405): *"1. rejection [off a key
level], 2. candle closure, 3. a breakout or break of structure on the
lower timeframe."*

**With liquidity** (bias-2 t=30-75): *"1. a sweep of liquidity on a
higher timeframe, 2. candle closure, 3. a breakout or break of
structure on the next timeframe lower."*

And they compose: *"you can build bias with both key levels and
liquidity at the same time"* (bias-2 t=1425, t=1545, t=1980).

The engine's `BiasCascade.check_flip()` has three conditions. Whether
they are *these* three is worth checking directly.

### The breakout is validation, not a level to trade back to

Said three times, and it is a live risk for any implementation that
arms a zone at the breakout:

> *"Price doesn't necessarily have to come to your breakout or your
> break of structure level. **The aim of this is to validate your
> direction.** Price can even just continue buying from there. So price
> must not necessarily come to your breakout level."* (bias-1
> t=1140-1165)

Also bias-1 t=1620, next t=720.

### The caveat: no breakout, but repeated rejection

The single most implementation-relevant passage in bias-1 (t=780-855):

> *"When you do not see a breakout on your daily timeframe, and instead
> you see one or two daily candles reject off that same particular
> zone -- in such a case you can then say, okay, daily is rejecting
> this weekly key level. It's still the same idea. But then you
> absolutely [must] see your sweep and break or your breakout **on the
> next timeframe lower**."*

So condition 3 is not optional; it *descends a timeframe* when the
daily gives rejection instead of breakout. He runs this path live on
XAUUSD at bias-1 t=1875-1890 and on EURUSD at t=1305-1335.

Contrast BTC at bias-1 t=1770-1785, where he refuses the trade:
*"There was no reason to have engaged a buy, because the criteria is:
we saw rejection and closure, we said [we] want to see a breakout or a
break of structure. That did not happen."*

### Where the engine and the videos disagree

**(a) Misaligned lower-timeframe breakouts are ignored.** *"This
bullish breakout here was not in alignment with what the weekly was
telling us, which meant that we should have actually ignored this
particular guy."* (bias-1 t=1260-1290). Also routine t=735-765,
next t=240-255. The engine's strict Weekly > Daily > H4 priority
matches this.

**(b) But the weekly can be dropped.** routine t=390-435, which the
engine has no equivalent for:

> *"I go back to the weekly. Weekly [is] saying bullish, [and] daily is
> now saying bearish. In that case now, those two timeframes are not in
> alignment, so [I] go to the four hours... **I can leave the weekly,
> I use my daily and my four hours**, [and] I probably just target a
> good liquidity."*

Confirmed as a deliberate choice at next t=465: *"it was kind of like a
reversal trade that I was willing to take, because **I built it from
the daily alone**."*

Reading (a) and (b) together: when the weekly disagrees with the daily,
he may either defer to the weekly (XAUUSD, bias-1 t=1875) or demote to
a Daily+H4 trade **with the target cut back to the nearest liquidity**
(routine t=420). The reduced target is what makes the demotion safe.
The engine only ever does the first, so it declines a class of trades
he takes. This is the clearest unimplemented rule found so far, and it
is not a small one.

**(c) Two bias machines, one rule?** The engine runs both `bias_at()`
(flip machine) and `_aligned_timeframes()` (most-recent-breakout) and
requires both. The videos describe one rule with two construction
methods, not two gates. Whether ours is double-counting is still open.

**Lower timeframe opposing a higher one is internal liquidity, not a
reversal.** *"We are still bearish on the weekly. For daily, switch to
bullish. It's possible to take out internal liquidity"* (bias-2
t=1110). Also bias-1 t=1680-1710: *"you're going to have buys even in a
sell environment... daily always retraces."*

---

## Operating notes (not engine behaviour, but they set expectations)

- He trades **all** pairs and calls it a mistake: *"trading multiple
  pairs is not the best thing to do... your risk exposure is going to
  be [larger], [and] you might have missed setups"* (routine t=30-120).
- He scans the full list in 15-30 minutes each morning by 7am, flags
  what is live, and re-checks before sleeping (routine t=240-315).
- Missed setups are normal and stated as such repeatedly (routine
  t=1005 *"this guy was a miss"*, bd2 t=165, t=1050).
- Losses inside a correct bias are expected: *"it's possible you might
  have taken a loss at this particular zone. But it doesn't mean your
  bias was wrong."* (repeat t=1305)

---

## Where the two courses disagree: which key level

Found while extending the frame pipeline to the 4th man course, so this
row is sourced from the main-course notes rather than from frames. It is
the one place the two teachers appear to give different rules, which
makes it worth stating rather than quietly picking a side.

**4th man (video-17) ranks candidates by test history.** A level tested
and respected 2+ times before it was finally disrespected beats both a
level broken on its first test and a further untested "extreme" one --
quoted at ~80%. This is what "QMR key level" means; videos 7 through 13
use the term without defining it and the notes had it flagged unresolved
until video-17.

**Bishop reacts in order and does not rank.** *"Price likes using the
closest key levels"* (entries t=435) -- but a tendency, not a selector,
and when price skipped the nearest one he was untroubled: *"instead it
[went to a level below]. And that's not a problem for me, because I just
want to see a rejection after that."* (bd2 t=570)

**Engine: Bishop's reading, deliberately.** `ranking.py` implements the
4-factor score including QMR test-count, and `runner.py` disconnected it
on purpose -- nearest-to-extreme order, take the first candidate that
actually reacts, extreme as last resort, *"we don't predict, we react."*
`count_tests_before_disrespect()` still runs and its result is still
recorded on every trade as `qmr_test_count`, but nothing consumes it and
`ranking_score` stays at 0.0.

So the QMR data is being collected and thrown away. That is the cheap
thing to check first, and it can be checked on trades we already have
rather than by changing the strategy: **does `qmr_test_count` correlate
with outcome in the existing backtest output?** If levels with 2+ prior
tests win materially more often, 4th man's ranking is worth wiring back
in. If it does not, the disconnection was right and this stops being an
open question.

Not attempted yet. Listed below as item 7 because it is a measurement,
not a change.

---

## What to change, in order of expected effect

1. **Target = ERL with 3R fallback**, not `min(3R, ERL)`. Seven
   citations, no counter-evidence, and the `capped` column says it
   bites often.
2. **Entry triggers**: replace `is_engulfing` with the four taught
   triggers, generalising the disrespect trigger to V-shape and
   A-shape levels as well as open-close.
3. **Entry timeframe ladder** H1 -> 45m -> 30m -> 15m. Large scope,
   large expected effect, needs LTF data we may not have cached.
4. **`liquidity_mode="both"`** -- run the A/B, but the videos already
   say the two forms are one pool.
5. **Daily-only bias with a reduced target**, when weekly and daily
   disagree.
6. **Stop = the disrespecting candle's wick** for the disrespect
   trigger.
7. **Measure whether `qmr_test_count` predicts outcome** in the trades
   the backtest already produces. Costs one query, not a strategy
   change, and settles whether 4th man's key-level ranking should be
   reconnected (see the section above).

---

## A checkable claim

`bd3 t=750`, NZDCHF **4h**, June 2026: a 1px line at **0.46312**
anchored to a candle low around 4-5 June, swept around 10-11 June,
which he calls single candle liquidity.

Run `_find_liquidity_setups` on NZDCHF H4 for that week and see whether
0.46312 is armed. First specific taught level that can be checked
against the implementation instead of argued about.

---

## Status

Bishop: transcript index read in full for all nine videos (1,058 rows, ~4h of
material). Contact sheets read: 7 of 42, plus 3 full-resolution frames.

The transcripts turned out to carry nearly all the rules, because he
narrates what he draws. The frames are still needed for anything
geometric -- which candle, which wick, how far -- and that is what the
two worked trades in the Targets table came from. Remaining sheet
reading should be aimed at specific open questions rather than swept
end to end.
