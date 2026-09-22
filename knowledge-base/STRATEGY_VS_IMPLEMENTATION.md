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

**(c) Two bias machines, one rule? CLOSED -- they are two rules.**
Audited 2026-09-22 (AUDIT_2026-09-22_PART2.md, C1). `BiasCascade` is
video-16's "do not flip while the lower timeframe still confirms the
old direction", a rule for ABANDONING a bias. `_aligned_timeframes` is
bias-1 t=390-405's "a breakout or break of structure on the next
timeframe lower", the positive evidence needed to ESTABLISH one, here
enforced at entry. Different operations, both taught. Requiring both is
correct and is not double-counting.

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

## The 4th man entry model — and what QMR actually is

**This supersedes the section below it, which was written from the
hand-written notes before the main-course transcripts existed and got
QMR wrong.** Sources here are the transcripts themselves:
`knowledge-base/videos/video-14/transcript.txt` (Entry Models 1) and
`knowledge-base/videos/plug-and-play/transcript.txt`.

### QMR is a shape, not a test count

> *"It could be a QMR key level, **which is an A-shaped key level that
> is overlapping inside of an imbalance**, or it could be an open close
> key level that could be overlapping inside of an imbalance."*
> (video-14 t=180-189)

Said twice more at t=89-98. I previously recorded QMR as "a level
tested and respected 2+ times before disrespect, preferred over others"
and filed it as a **ranking** factor the engine ignores. Both halves
were wrong: it is a **shape**, and the test-count idea is a different
criterion that belongs to the same setup (below), not a tie-breaker
between candidates.

### The setup, stated in full

plug-and-play t=791-955, which is the clearest statement of an entry
rule anywhere in either course:

> *"I love to play a key level ... that [was] disrespected, that is also
> overlapping inside of an imbalance ... It has [liquidity] resting
> above or below it ... A-shaped key levels [that were] disrespected, or
> V-shaped key levels [that were] disrespected, overlapping inside of an
> imbalance"*

and then the refinement he says he has data on:

> *"I don't just play key levels ... that A-shaped key level **must have
> sponsored some level of sales** ... price rejected from here, it gives
> to us some heavy momentum sales ... and after that, then that's where
> we get [it] disrespected to the other side."* (t=838-925)

So one rule with four conditions, in order:

1. An **A-shaped** (or V-shaped) key level
2. that **sponsored a move** — price rejected off it and it worked
3. that was then **disrespected** — price closed through it
4. and which **overlaps an imbalance**, with liquidity resting beyond it

That resolves video-17's "tested and respected before being
disrespected" as condition 2, not a separate ranking heuristic.

### The engine has every piece and composes none of them

| condition | primitive that exists |
|---|---|
| A/V shape | `detect_key_levels()` |
| sponsored a move | `count_tests_before_disrespect()` |
| disrespected | `is_disrespected()` |
| overlaps an imbalance | `overlaps_level()` |

All four are computed. `count_tests_before_disrespect` is recorded as
`qmr_test_count` and read by nothing. `overlaps_level(im,
key_level.price)` is what the engine labels **`plug_and_play`** — the
same name the course uses.

And there is a measured result sitting in `_nearest_imbalance_zone()`'s
docstring that deserves a second look. An A/B on 2026-09-02 required
the key level to overlap an imbalance and found it *"silently reduced
the whole rule to plug-and-play ... 80.2% of setups skipped"*. That was
recorded as a bug — the experiment measuring the wrong thing.

On this reading it may have been implementing the taught rule and
throwing away the answer. Skipping 80% of setups is what a
four-condition filter is supposed to do.

**Checked. The answer is in bot/OPERATIONS_LOG.md, and it points the
wrong way for the taught rule.** The log records that those 533
surviving trades were *"identical to their default versions"* -- same
entry, same stop -- so the run does contain a clean read on how the
imbalance-overlapping subset performed against the whole book:

| | all setups | plug-and-play only |
|---|---:|---:|
| trades | 2,697 | 533 |
| win rate | **51.7%** | **46.3%** |
| R/trade | **0.990** | **0.786** |

The subset that satisfies the course's headline condition performed
*worse* than the average of everything, on both measures.

**But do not conclude from this yet.** That run is dated 2026-09-02,
sixteen days before the look-ahead bug was removed. 0.990 R/trade
against today's 0.32 is the signature of the broken engine. Both
columns are inflated by an engine that could see a week past its own
entry, and there is no reason to assume the inflation is uniform across
a subset selected by imbalance overlap.

So: the only measurement we have says the taught filter underperforms,
and the measurement is not trustworthy. It needs re-running on the
fixed engine before it means anything. Until then this is an open
question with one discouraging and unreliable data point, which is
different from both "unmeasured" and "disproved".

### Origin vs continuation

video-14 t=263-366 splits the model in two, and the engine already has
an `origin_kind` flag:

- **origin** — the first setup: IRL taken, then play from the key level
  that overlaps an imbalance
- **continuation** — price breaks the external liquidity (a V-shaped key
  level) with an impulsive move; expect a *shallow* retracement, a new
  IRL forming close to that disrespected level and overlapping an
  imbalance; play from there

> *"this continuation set up has over like a 70 to 80% win rate"*
> (t=296-301, repeated t=361-366)

Stops and targets, same passage: *"10 to 11 pips is enough. 1 to 3, 1
to 4, you are done"* (t=349-354).

The live bots run `origin_kind="any"`, which does not distinguish them.

---

## Where the two courses disagree: which key level

**SUPERSEDED by the section above.** Kept because the disagreement it
describes is real, but its QMR definition came from the hand-written
notes and is wrong -- QMR is an A-shaped key level overlapping an
imbalance, not "a level tested 2+ times". Read the section above first.

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
7. **Re-run the plug-and-play filter on the fixed engine.** The
   2026-09-02 numbers say the imbalance-overlapping subset did WORSE
   than the whole book (46.3% vs 51.7% win, 0.786 vs 0.990 R/trade) --
   but that run predates the look-ahead fix and both columns are
   inflated. It is the one taught rule with a measurement against it,
   which makes re-measuring it the highest-information run available.
8. **Compose the four-condition setup** (A/V shape, sponsored a move,
   disrespected, overlapping an imbalance). Every primitive exists;
   nothing joins them. Note that item 7 tests only ONE of the four
   conditions -- a rule can fail on one leg and work whole, so a bad
   result there does not close this.

---

## A checkable claim

`bd3 t=750`, NZDCHF **4h**, June 2026: a 1px line at **0.46312**
anchored to a candle low around 4-5 June, swept around 10-11 June,
which he calls single candle liquidity.

Run `_find_liquidity_setups` on NZDCHF H4 for that week and see whether
0.46312 is armed. First specific taught level that can be checked
against the implementation instead of argued about.

---

## Which citations here are trustworthy

A timestamp bug was found on 2026-09-19 (see `extract_at_times()` in
knowledge-base/tools/extract_frames.py). Contact sheets burned a
COMPUTED `n*interval` label rather than the time they were seeked to,
so a sheet tile's number does not reliably identify its frame. Full
resolution frames were always fetched with an explicit `-ss` and are
unaffected.

That splits this document cleanly:

**Sound.** Everything citing transcript text -- which is nearly all of
it. `index.md`'s caption column is computed from the cue file's own
`[start-end]` stamps and never went through the frame pipeline.

**Sound.** The numeric trade data in "Targets" (`bd3 t=1080` USDJPY,
`bd3 t=870` NZDCHF) and the NZDCHF `0.46312` claim at `bd3 t=750`.
All three were read off full-resolution PNGs, which still exist in
`knowledge-base/frames/bishop-trades-breakdown-3/` at those exact
filenames and can be re-opened and re-checked.

**Not sound.** Anything read off a contact-sheet tile. One claim of
that kind was made and has been retracted: that two frames in
`bishop-repeating-system` showed position tools with entry, stop and
target. Pulled at full resolution, they show horizontal levels and no
position tool.

The sheets need regenerating on the fixed path before they are used for
anything more than navigation.

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
