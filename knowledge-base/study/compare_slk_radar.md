# SLK Radar (Timothy's SLK bias bot) vs our SLK bot

Source: `knowledge-base/videos/kevin-devt-building-the-slk-bias-bot-...-rqp8f2/transcript.txt` (Whisper, 0-722 s,
cut off mid-sentence at 12:02) and all 19 contact sheets in `knowledge-base/frames/<same slug>/sheets/` (frames every
10 s, t=0-720). Every sheet was looked at; alert texts were also read from enlarged crops of sheet_002 (t=60) and
sheet_014 (t=550).
Citation format: `[mm:ss] sheet_NNN (speech | screen | both)`. Sheet NNN holds t = (NNN-1)*40 ... +30 s.
Speaker: "Timothy, creator of the SLK bias bot, SLK Radar" [00:00] sheet_001 (speech). The Telegram bot is named
**slkradar bot** (screen, sheet_002 onward).

Whisper garbles used below: "buts/boats" = bot, "condo/country" = candle, "for X.com / friends.com" = FOREX.com
(the TradingView chart feed shown is FOREXCOM), "slip/strip of liquidity" = sweep of liquidity, "Kelvin King /
going king" = Kevin King, "the for our" = the 4-hour.

---

## 1. What SLK Radar does (everything observed)

### 1.1 Delivery and setup
| # | Observation | Cite | From |
|---|---|---|---|
| 1 | Alerts arrive as Telegram messages from "slkradar bot" (user keeps it in a Telegram folder "radarr"). | [01:00] sheet_002 | screen |
| 2 | Bot commands (Telegram command menu): `/start` "Activate your account", `/alerts` "Open alert preferences", `/settings` "Open alert preferences", `/terms` "What the words in an alert mean". | [08:40-09:00] sheet_014 | screen |
| 3 | A web **portal** exists with features you can turn on/off; covered "in another video". | [00:20-00:34] sheet_001 | speech |
| 4 | Time zone of alert times is a portal setting ("change your time zone according to where you are"); his is WAT (UTC+1, Nigeria). | [05:41-05:57] sheet_009 | both (all alerts end "Sent ... WAT") |
| 5 | Data feed: he wants FOREX.com data ("stepping on the gas to get FOREX.com ... experienced some delays"); the prices in the alerts are currently from another feed (the word is garbled: "under prices"; could be "OANDA", not certain). He matches the alert price to a candle on his FOREX.com TradingView chart by hand. | [01:26-01:45], [03:25-03:45] sheet_003, sheet_006 | speech |
| 6 | Commercial product: "/start Activate your account"; walkthrough is "video 1", portal video to follow. | [00:20] sheet_001; [08:40] sheet_014 | both |

### 1.2 Pairs / timeframes seen
| # | Observation | Cite | From |
|---|---|---|---|
| 7 | Symbols in alerts: XAUUSD, EURNZD, AUDNZD, CADJPY, EU50 (index), AUDJPY, one JPY-like pair at 177.736 whose name is cut off. So gold and indices are covered, not only FX. | sheet_002, sheet_014 | screen |
| 8 | Every alert seen is **D1→H4** (daily rejection, H4 confirmation). No W→D or M→W alert is visible. | all chat frames | screen |
| 9 | "It checks on the higher time frame, the daily or weekly ..." — so a weekly origin may exist; not shown. | [02:10] sheet_004 | speech |

### 1.3 The logic as he explains it
| # | Rule | Cite | From |
|---|---|---|---|
| 10 | **Trend** = direction of the **last break of structure** on the higher TF (daily or weekly). He finds it on the **line chart** ("so it's not confusing"). EURNZD: last break was to the downside → bearish. | [02:10-03:20] sheet_004-006 (line chart shown at t=140, 180, 190) | both |
| 11 | **Rejection** on the HTF at a key level: EURNZD "rejected at the open and close" level 2.00219 (an Open-Close KL). Daily chart shows the Thu 8 Oct candle wicking into the line and closing below; red vertical line at the rejection candle. | [01:20-01:30] sheet_003; [03:20-04:50] sheet_006-008 | both |
| 12 | Uses TradingView **Bar Replay** to show the chart as of the rejection day (replay date 8/10/2026). | [02:40-04:20] sheet_005-007 | screen |
| 13 | **External breakout** = on the lower TF (H4) take the candle that **tapped** the daily rejection price, find the **last V-shape key level formed before this tap** ("or the last support as you might know it"); an H4 **close below it** = bias confirmation. | [09:35-10:20] sheet_015-016 | both (H4 line drawn at the V at 1.99943, t=460-480 sheet_012-013; "Daily KL" label on the H4 chart, t=590-620 sheet_015-016) |
| 14 | **Internal breakout** = any other breakout (close below a lesser low) that does not close below that last V before the tap. "External breakouts are way more high probability, which is why I only trade them." | [10:17-10:32] sheet_016 | speech |
| 15 | Same H4 candle (Fri 9 Oct 02:00) produced both an **internal** alert (BO @ 2.00002) and an **external** alert (BO @ 1.99943) for EURNZD, one minute apart. | [01:00] sheet_002 | screen |
| 16 | **Trend aligned** = the rejection agrees with the trend from rule 10 ("trend aligned with D1 ... the rejection was in line with the daily trend"). | [06:06-06:22] sheet_010; [10:45-11:10] sheet_017 | both |
| 17 | **Next Day Rule**: the HTF rejection and the LTF external breakout happen on **two different days** (rejection Thursday, breakout Friday "or even days after"). Same-day rejection + breakout = lower probability; "even worse" when price also comes back into the breakout area the same day. He attributes the rule to Kevin King ("during his studies he noticed ..."). | [06:30-08:05] sheet_010-013 | speech; alert line "✅ Next Day Rule" (screen) |
| 18 | Alert timing: alert is sent at the **close of the H4 breakout candle** (H4 opened Fri 02:00 WAT, closed 06:00, alert "Sent 9 Oct, 6:00 AM WAT"). No wait for the daily close. | [05:20-05:40] sheet_009 | both |
| 19 | Candle times in alerts are **candle open times**; the daily candle that opens Wed 22:00 WAT is Thursday's candle (17:00 New York close). He spends ~2 minutes explaining this confusion. | [03:50-05:00] sheet_006-008 | both (later alert format adds "All times shown are candle open times.") |
| 20 | Not an entry: every alert ends "⚠ Not an entry signal. Bias only — wait for your entry model." He entered manually with his own entry model after the H4 external breakout and took profit early. | [08:10-08:30] sheet_013 | both |
| 21 | Alert text was made clearer over the weekend ("I've added more clarity to the text"). | [06:38-06:50] sheet_011 | both (old vs new format below) |

### 1.4 Alert format (verbatim from screen)
Old format (Fri 9 Oct), sheet_002 t=60 (crop):
```
🚨 SELL · EURNZD · D1→H4
External breakout confirmed

Rejected at OC-shape @ 2.00219.

External BO @ 1.99943 · Fri 9 Oct, 02:00
Rejected on Wed 7 Oct, 22:00
Trend aligned with D1
✅ Next Day Rule

⚠ Not an entry signal. Bias only — wait for your entry model.
Sent 9 Oct, 6:00 AM WAT
```
Internal version: header "Internal breakout confirmed", line "Internal BO @ 2.00002 · Fri 9 Oct, 02:00", **no
Next Day Rule line** (EURNZD, AUDNZD BUY "Rejected at OC-shape @ 1.24082 / Internal BO @ 1.24232 · Fri 9 Oct, 06:00 /
Rejected on Tue 6 Oct, 22:00", CADJPY SELL "OC-shape @ 111.24600 / Internal BO @ 110.94200 · Fri 9 Oct, 10:00").

New format (Tue 13 Oct), sheet_014 t=550 (crop):
```
🚨 SELL · AUDJPY · D1→H4
External breakout confirmed

Rejected at Open-Close KL @ 110.54200.

External BO @ 110.30200 · Mon 12 Oct, 22:00
Rejected on Sun 11 Oct, 22:00
Trend aligned with D1
✅ Next Day Rule · breakout after the rejection candle closed

All times shown are candle open times.

⚠ Not an entry signal. Bias only — wait for your entry model.
Sent 13 Oct, 2:00 AM WAT
```
Another new-format alert (pair cut off) also has "Key level 177.73600 · formed 1 Oct 2026". Level kinds named:
"OC-shape" / "Open-Close KL", "V-shape KL" (XAUUSD BUY internal @ 4155.37), "A-shape KL" (EU50, partly hidden).
No target, no invalidation, no point-B wording, no "tapped / waiting" alert and no "target hit / invalidated" alert
appear anywhere in the video.

### 1.5 Alert preferences (`/alerts`), sheet_014-018
Panel text: "Alert preferences / ✅ External BO confirmations: On / ✅ Internal BO confirmations: On / Trend aligned
rejections: Required / Trend aligned sweeps: Unrequired / ⚠ Internal BOs are lower probability than External BOs.
Turning them on may lower your win rate with the bot." Four inline buttons toggle: `External: ON|OFF`,
`Internal: ON|OFF`, `Trend aligned rejections: Required|Unrequired`, `Trend aligned sweeps: Required|Unrequired`.
| Setting | Meaning (speech) | Cite |
|---|---|---|
| External BO confirmations | on/off | [10:30-10:40] sheet_016-017 |
| Internal BO confirmations | "nice to have"; on for him only because as developer he wants to see all alerts; he does not trade them | [08:43-09:00] sheet_014; [10:30] |
| Trend aligned rejections | Required = only rejections in the direction of the HTF last-BOS trend; Unrequired = also counter-trend | [10:45-11:16] sheet_017-018 |
| Trend aligned sweeps | same idea for "sweep of liquidity" starts | [11:17-11:32] sheet_018 |
| **Default** | "The setting you most likely get on default is internal ... off, required and required" → External ON, Internal OFF, both Required (frames t=700-710 show exactly that). "Way more probability when you leave them at default." | [11:36-11:50] sheet_018 (both) |

He toggled the buttons live: t=630-650 rejections Unrequired; t=670-680 Required; t=690 Unrequired; t=700-710
Internal OFF, rejections Required, sweeps Required [sheet_016-018, screen].

---

## 2. Comparison

Kevin notes cited: `notes_storyline.md` (NS), `notes_structure.md` (NM), `notes_liquidity_levels.md` (NL),
`notes_entry.md` (NE), `frames_G.md` (FG). Ours: `STRATEGY.md` (§), `slk/settings.py`, `slk/story.py`, `slk/live.py`.

| Topic | SLK Radar | Ours (file/rule) | Verdict | Closer to Kevin |
|---|---|---|---|---|
| Story ladder | Only D1→H4 seen; speech says HTF "daily or weekly" | D→H4, W→D, M→W (`STORIES`, setting `stories`) | WE HAVE, THEY DON'T (W/M unclear for them) | Ours: Kevin starts M/W/D by calendar [NS §1, T sl@468] |
| Trend definition | Direction of the **last break of structure** on HTF (line chart) | HH+HL / LH+LL of close-line structural swings; a close beyond the last opposite swing flips; else **range = no bias** (`structure.trend`, §1) | DIFFERENT (detail) | Both use line chart [NM §1]. Kevin: range → stay away [NM §3]; first break flips [NM §2]. Ours has the range state, theirs is not shown → ours closer |
| Trend filter on rejections | Toggle Required / Unrequired (default Required) | `trend_filter` on (one switch for KL taps and sweeps) | SAME by default; THEY HAVE a counter-trend option | Kevin: "never against trend" [NL §1.7, T liq3@712-723; kl3@985-1160] → Required (both) |
| Trend filter on sweeps | Separate toggle (default Required) | Same `trend_filter` applies to `sweep_start` | DIFFERENT (granularity) | Kevin: sweeps of PDH/PDL valid bias builders, still with trend [NL §1.8, §1.5 counter-trend example] → required, no separate switch needed |
| HTF filter / M-W conflict | Not shown | `htf_filter`, `mw_conflict_filter` | WE HAVE, THEY DON'T (as far as visible) | Ours [NS §2, T cw@1236-1312] |
| Key-level kinds | OC-shape/Open-Close KL, V-shape KL, A-shape KL | A, V, OC on bodies/closes (§1) | SAME | Both [NL §2] |
| Level "formed" date in alert | "Key level X · formed 1 Oct 2026" | Not in alert | THEY HAVE, WE DON'T | neutral (display) |
| Most recent fresh level | Not mentioned | `most_recent_level` (#26) | UNCLEAR for them | Ours [NS §1, T pt2@897-1000] |
| Tap-reject-close | "Rejected at ... KL", "Rejected on <D candle open>" | Wick in + close back, judged at close (§2 step 3) | SAME | Both |
| Point B | Last V-shape KL formed before the H4 candle that tapped the daily level | Last close-line V/A turn (`b_pivot`=1) before the first touching H4 (`_point_b`) | SAME | Both [NS §1 "last V before price first tapped", FG correction 1] |
| External break | H4 close beyond that V = "External breakout confirmed" | H4 body close beyond B (`_break_search`) | SAME | Both |
| Internal breaks | Optional **"Internal breakout confirmed"** bias alerts (default off, warning shown) | Never confirm bias; used only for entries (story.py comment, §2 step 5) | THEY HAVE, WE DON'T | **Ours.** Kevin: internal breaks "are not used to confirm the bias" [NS §1, T pt2@2085-2178, pt3@1144-1260] |
| Daily close after H4 breakout | Alert at H4 close; no daily-close check seen | `same_bar_close`: the D candle holding the breakout must close beyond B; CONFIRMED only then (`conf_index`) | DIFFERENT | **Ours.** Kevin: "allowing the day to close is very important ... if we can't close the daily [beyond] this breakout level ... cancel" [T qns-pt2@1860-1930; NE line 54; FG (5)] |
| Same-day re-entry into breakout level | Speech: "even worse" if price comes back to the breakout area same day; no filter seen | Only the D close is checked, not a same-day touch back | PARTLY DIFFERENT (neither filters the touch) | Kevin: "the day that gave us this breakout ... should not trade back into the breakout zone"; "no longer high probability" [T qns-pt2@1946-2030] |
| **Next Day Rule** (breakout after the rejection candle closed) | Shown on external alerts: "✅ Next Day Rule · breakout after the rejection candle closed" | **Not checked.** `_break_search` scans from the first touching H4 *inside* the tap day, so an H4 break on the rejection day itself confirms | THEY HAVE, WE DON'T | **Theirs.** Kevin: best breakout = "you go to four hours **after the close of this day**, you just see a clean breakout" [T story-line-pt3@1358-1401]; "wait for the candle to close" is the standard [NS §1]; trades come "the next day ... not that particular day" [T qns-pt2@1946-1962] |
| Waiting days tap→breakout | "Friday or even days after" allowed | `max_wait` = 5 D bars, `max_retaps` 3 | SAME idea; we have explicit limits | Ours [T pt3@1331-1350 "fifth day ... also valid"; qns-pt2@2076-2150] |
| Sweep start | "Trend aligned sweeps" setting exists, no sweep alert seen | `sweep_start` (prev D/W/M high/low) | SAME (probably) | Both [NS §1 alt origin] |
| Target / invalidation | Not in alerts | Target (next KL incl. HTF, ERL), invalidation, `flip_end`, TARGET_HIT/INVALIDATED alerts | WE HAVE, THEY DON'T | Ours: "direction, target and entry" [NS §1, T sl@374] |
| TAPPED (waiting) alert | Not seen | `alert_tapped` | WE HAVE, THEY DON'T | neutral (Kevin: no breakout = no trade; ours says NO_TRADE until breakout) |
| Exceptions (overlap, alignment, CADJPY, flip) | Not mentioned | `overlap_rule`, `alignment_start`, `cadjpy_exception`, `flip_end` | WE HAVE, THEY DON'T | Ours (Kevin uses them in class, §2) |
| Entry | None; "wait for your entry model" | Continuation + QMR entry alerts (§3, `entry.py`) | WE HAVE, THEY DON'T | Ours (Kevin teaches entry models [NE]) |
| "Not an entry" disclaimer | Every alert | CONFIRMED: "bias confirmed. Not an entry: wait for an entry alert" | SAME | — |
| Times in alerts | Candle **open** times, user time zone (portal), footnote "All times shown are candle open times." | Tap = D candle **open** time (`o_start`), Confirmed = H4 **end** time (`c_end`), always UTC (`fmt_time`) | DIFFERENT | display only. Ours mixes open and close times without saying so; same confusion he spent 2 min on |
| Daily candle clock | Daily opens 22:00 WAT = 17:00 New York; H4 at 22/02/06/10/14/18 WAT | 17:00 New York close; H4 bins shifted the same way (`candles._key`) | SAME | §5 #4 |
| Data feed | Some feed now, FOREX.com planned; charts on TradingView FOREXCOM | Dukascopy H1 (`slk/data.py`) | DIFFERENT | Kevin charts on TradingView (feed not specified) — UNCLEAR |
| Symbols | FX + XAUUSD + EU50 index | 28 FX pairs (`settings.PAIRS`) | THEY HAVE, WE DON'T | Kevin also uses XAUUSD and German 40 [NS §3; FG] |
| Settings UI | Telegram inline buttons + web portal; `/terms` glossary | Mini App settings (`settings.SCHEMA`), no in-chat glossary | DIFFERENT; glossary THEY HAVE | neutral |
| Status / heartbeat | Not shown | `status_updates`, daily summary | WE HAVE, THEY DON'T | neutral |

---

## 3. Worth adopting (ranked)

1. **Next Day Rule check (rule + alert line).** Kevin grounds it: the clean breakout is found by going to H4 "after
   the close of this day" [T story-line-pt3@1358-1401], and he wants the trade "the next day, not that particular
   day" [T qns-pt2@1946-1962]. Today `story._break_search` accepts an H4 close below B inside the rejection day.
   Proposal: setting `next_day_rule` (Bias rules) with choices `flag` (default: compute and show
   "✅ Next Day Rule: breakout after the D rejection candle closed" / "⚠ same-day breakout") and `require` (only H4
   candles that open after the origin candle's close may break B). Backtest both: hit rate of same-day vs next-day
   breakouts. Store `next_day` on the story row so the Mini App can filter.
2. **Breakout time + breakout price in the alert, and unambiguous times.** Add `breakout_time` (H4 candle) to the
   story row and the alert ("External break: H4 close below point B 1.99943, H4 candle Fri 9 Oct 02:00-06:00").
   Label the origin candle by its **trading day** ("D candle Thu 8 Oct"), not its open timestamp, and say whether a
   time is open or close. Add a `display_tz` setting (Alerts group; default UTC, e.g. Africa/Lagos, Europe/London).
   Their bot shows how much confusion the bare open time causes [03:50-05:00].
3. **Two-step confirmation message (keep Kevin's daily close).** Their alert comes at the H4 close; ours only at the
   D close (correct per Kevin). Optional event `BREAKOUT` (new `alert_breakout` toggle, default off): "H4 broke
   point B — wait for the daily close beyond it (Kevin: cancel if it does not)". CONFIRMED stays at the D close. If
   price closes back above the breakout level that day, send "cancelled (same-day close back)".
4. **Same-day touch-back flag.** Kevin: the breakout day "should not trade back into the breakout zone"; if it does,
   "no longer high probability" [T qns-pt2@1700-1730, 2015-2030]. Our `same_bar_close` only checks the close.
   Proposal: flag (not filter by default) when a later H4 on the breakout day wicks back to B; backtest as a filter.
5. **Alert wording borrowed from theirs:** first line `SELL · EURNZD · D1→H4` compact header; "Key level 2.00219 ·
   formed 1 Oct" (level birth date); "Trend aligned with D1" (and the W trend from `htf_filter`). Keep our target,
   invalidation and point B lines, which they lack.
6. **`/terms` glossary command** in the Telegram bot (KL, A/V/OC, tap, point B, external vs internal break, next day
   rule, TAPPED/CONFIRMED/TARGET_HIT/INVALIDATED/ENDED_FLIP). Cheap, reduces support questions.
7. **Optional symbols XAUUSD / index (DE40).** Kevin trades them [NS §3]. Needs pip size per symbol (`story.pip`
   only knows JPY vs other) and a Dukascopy symbol map. Low priority.

### Do NOT copy (contradicts Kevin)
- **Internal BO "confirmed" bias alerts.** Kevin: breakouts after the tap are internal, used for entries, never to
  confirm direction [T pt2@2085-2178, pt3@1144-1260]. Their own panel warns they lower the win rate and their creator
  does not trade them. Our design (internal breaks only inside entry models) is right; do not add a bias alert for them.
- **"Trend aligned rejections / sweeps: Unrequired".** Counter-trend stories go against "never sell in a bullish
  market" [T liq3@712-723] and "only levels that agree with the trend" [T kl3@985-1160]. We already let a power
  user switch `trend_filter` off; no need for two separate switches.
- **Confirming on the H4 close without the daily close.** Kevin cancels the idea if the day does not close beyond the
  breakout level [T qns-pt2@1905-1930]. Keep `same_bar_close` on.
- **Trend = last BOS only.** If their trend has no range state, it would produce biases in ranges; Kevin says stay out
  of ranges [NM §3]. Keep our range → NO_TRADE.
- The rule he credits to Kevin is real in substance (next-day breakout is cleaner), but Kevin calls multi-day waits
  "also valid" and the single-rejection-then-clean-breakout case "the best" [T pt3@1331-1401]; it is a quality
  flag, not a hard filter. Hence default `flag`, not `require`, until the backtest says otherwise.

---

## 4. Unclear / could not read
- Transcript ends mid-sentence at 12:02 ("I think we can"); frame t=720 (sheet_019) is just the EURNZD daily chart.
  Anything said after that is missing.
- Whether a rejection that **fails** the Next Day Rule is suppressed or shown with another mark: only ✅ cases were
  seen; internal alerts never show the line, even the EURNZD internal alert on the same H4 candle as the ✅
  external one and the XAUUSD internal one (rejection = Monday D candle, breakout Tuesday).
- Whether "Trend aligned with D1" can read "against D1" when the setting is Unrequired: no such alert was shown.
- Whether weekly (W→D) or monthly stories exist: speech says "daily or weekly", only D1→H4 alerts are on screen.
- How they detect the trend in detail (last BOS on closes or on wicks; any range state): only the spoken summary.
- What a "sweep" start is exactly (previous day high/low?): only the setting name "Trend aligned sweeps" and the
  garbled "slip/strip of liquidity" [11:17-11:32]. No sweep alert appears.
- Data feed word at [01:30] ("under prices") is garbled; it might be "OANDA", not confirmed.
- [04:30] "If you check for ... among the free plan" — garbled, meaning unknown.
- Partly hidden alerts: the top alert at t=550-710 (key level 177.73600, pair name scrolled off) and the bottom
  EU50 BUY alert at t=60-400 (only "External breakout confirmed" and a partly covered "A-shape KL @ 6102.1..." line
  are visible under the message box).
- Chart legend shows an indicator "CISD CISD CISD 10 1 Solid 5 Small Default Dotted" on his TradingView chart
  (sheet_001 onward); it is never discussed, so its role is unknown.
- Point B drawing: the H4 line at 1.99943 (t=460-480) and "Daily KL" label (t=590-620) are readable; the exact
  candles forming the V and the daily OC level cannot be verified from the frames (small candles, no labels).
- The portal (web settings) is never shown.
