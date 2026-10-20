# Plug-and-play source verification (2026-10-20)

Source: `knowledge-base/videos/bishop-this-plug-and-play-forex-system-changed-how-i-trade-result-focused/transcript.txt` (new run). Citations below are seconds in that file, not the old `plug-and-play/` transcript. Frame root: `knowledge-base/frames/bishop-this-plug-and-play-forex-system-changed-how-i-trade-result-focused/sheets/`.

Coverage: read the new transcript's technical sections (508–1379, 1452–1638, 1654–3050); opened sheets 014, 026, 028, 032, 034, 035, 039, 040, 041, 044, 045, 049, 051. This is a targeted visual verification, not a claim to have examined every sheet. Intro/discipline portions do not specify an additional price detector. Transcription is noisy: “God/gets respected” often means “got disrespected”; “impossible” is often “impulsive”; “equity” often means “liquidity.” No silent substitution should decide a replay expectation.

## Bias rules confirmed

| Rule | Source | Implementation consequence / remaining choice |
|---|---|---|
| Bishop starts with W, requires D alignment, then observes current H4 and waits for its close if necessary. | T547–601 | Closed candles only for confirmation; W/D/H4 hierarchy. Numerical alignment detector must come from structural definitions in the other videos. |
| Bearish W start can be a key-level rejection with close below, or prior-W high sweep with close below that high. | T618–650, T696–738 | Distinct event types: level-rejection and liquidity-sweep. Bullish mirror is consistent with Gold low-sweep example T1907–1925. |
| D confirmation is sweep plus structure break, OR breakout in the bias direction. | T744–756 | Do not require both alternatives. No engulfing replacement is stated in this particular definition. |
| Fallback when neither D confirmation appears: observe the SAME W level on D; D revisits/rejects at least twice and closes below; descend to H4 and require one of the missing confirmation alternatives there. | T1482–1504, T1538–1564, T1603–1629; F026 (1500–1545), F028 (1620) | This is a conditional alternate route. It is not permission to ignore lower-TF confirmation entirely. Count of D rejection candles is at least two; wick/body equality, consecutive-vs-separated rejection count, and a maximum waiting window are not defined. |

Caution on the previous-week sweep target: T646–663 is badly garbled, but the logic of a bearish high sweep leaves the opposite low as the directional draw; do not assert that the already-swept high is the sell target. The bullish Gold discussion explicitly calls the unswept previous daily high the draw (T1907–1943).

## Entry rules confirmed

1. A bullish preferred continuation level is an A-shape that previously sponsored sales, then is disrespected upward with a body close, and overlaps an imbalance (T841–879, T907–983, Gold T1847–1883). Mirror the direction for a bearish V-shape. “Sponsored sales” means an observable prior reaction, but **no pip distance, minimum candle count, or minimum impulse ratio is stated**.
2. There must be a reason to expect liquidity to be taken near that level, rather than an arbitrary midpoint order: NAS example explicitly rejects assuming every imbalance retraces to 50% (T1674–1686); it asks which key level inside the imbalance caused previous reactions (T1722–1806).
3. First liquidity form: the candle following the bullish breakout sits inside the breakout candle. Its low becomes internal range liquidity; anticipate its sweep into the disrespected key level/imbalance, then continuation toward external liquidity (T1000–1051). The entire containment test and tie handling need an explicit implementation definition; the speech says “resting inside,” not a numeric tolerance.
4. Alternate liquidity form: price sweeps the breakout candle's high, reverses/retraces, and the resulting candle provides internal liquidity. The candle that took ERL can itself serve as IRL; after its low is taken, its high becomes the new external draw (T1114–1248). This is not a rule that every swept high implies a full bearish structural reversal.
5. Bishop's normal search begins H4 → H3 → H2, selecting a clear setup and setting a limit, then leaving the screen (T1271–1299). This is an order of inspection, not evidence for scanning the smallest timeframe first or optimizing timeframes for retrospective profit.
6. Gold illustrates a missed H3 limit, followed by an M30 body-close break of an A-level and market execution at the same level (T1999–2057; F034–035). Therefore a universal H2-only execution rule would miss an accepted example. T2049–2053 literally says this M30 level “does not sponsor any sale”; whether that is a Whisper error or an explicit exception needs audio/dense-frame resolution before treating prior sponsorship as a universal hard filter. The safe source conclusion is a strong preference plus this unresolved example, not invented certainty.
7. USDCHF M30 is an **untaken illustration**, not an actual trade: “I didn't take it” (T2550–2554). Conditional on a previously built W/D buy bias, he shows A-level prior sales, upward body-close disrespect, imbalance overlap, and nearby liquidity, then says set limits/stops and leave (T2592–2684; F044–045).
8. EURJPY W/D context and H4 confirmation lead to checking H2/H3/H1. The selected H3 level overlaps an H1 imbalance and has prior buy reactions before bearish disrespect (T2213–2457; F039–041). The chart title resolves garbled “ULJPY” as EURJPY.

## Terminology correction

The old supplementary notes call this a “conservation sector/setup.” New transcript T791–819 alternates “conservation setups,” “continuation second,” and clearly “continuation setup.” The drawings in F014 show a familiar liquidity/key-level/imbalance continuation, with no written novel name. **Do not implement a separate pattern named conservation sector based on this noisy wording.** Keep descriptive structural conditions; preserve the transcription uncertainty in citations.

## Stops and targets: what this video does not establish

- No numeric stop size or stop-placement formula is given in the new technical transcript. T427–442 says “simple stop” without a price, and T2655–2659 says “set your limits, set your [stops].” Neither establishes 10–11 pips or a zone-edge formula.
- ERL and the still-standing opposite candle extreme provide directional targets (T1024–1030, T1244–1248, Gold T1913–1943, closing T3038–3046). Exact partial sizing, fixed RR, risk percentage, session cutoff, slippage, and holding period are not specified here.
- He explicitly mentions limits activating at night (T1293–1299). Therefore the draft's universal “never hold/trigger overnight” wording must be qualified by source/style; this video cannot support an unconditional overnight ban.

## Chart-example evidence ledger

These are candidates for extraction, **not fully specified executable trade fixtures**. Do not count them as all-fields matches while exact order time/stop/target are unknown.

| Candidate | Verified source and visual | What is established | Missing before exact replay |
|---|---|---|---|
| NAS100 continuation study | T1654–1814; F028 (1650–1665) | Symbol NAS100, H4 stated, imbalance plus repeatedly used/flipped key level. Date axis in May 2025. | Actual taken-vs-explanatory order, precise timestamp/entry/SL/TP and broker feed. |
| XAUUSD H3 missed buy | T1943–2025; F034 (1980–2025) | Gold H3 structure break; OC limit; liquidity above selected OC; Bishop reports missed entry. Date axis around 16–21 May 2025. | Exact pending time, selected price, stop and target; a MISSED expectation must remain missed. |
| XAUUSD M30 replacement buy | T2025–2067; F035 (2040–2055) | Gold M30 A-level body-close break, then market execution at retest; actual taken trade narrated. | Exact execution timestamp/price/SL/TP, and sponsorship wording ambiguity. |
| EURJPY bearish continuation | T2213–2481; F039–041 | Symbol EURJPY confirmed; W/D context, H4 bearish structure break, H3/H1 level/imbalance confluence. Charts show May 2025. | Exact entry event/time, stop, final target and executed order evidence. |
| USDCHF M30 hypothetical buy | T2522–2684; F044–045 | Symbol USDCHF, M30, level near 0.825x; prior sales then bullish body-close break/imbalance/liquidity; explicitly not taken. | Exact marked level read independently at native resolution, precise event time, SL/TP. Must not label as Bishop's executed trade. |
| EURJPY lower-TF sell illustration | T2919–3046; F049, F051 | EURJPY symbol, M30 stated around T2922; bearish flip/retest and liquidity sweep into external draw. | Whether distinct trade from earlier EURJPY, exact price/time/SL/TP. |

No precise numeric stop/entry/target fixture is promoted from these sheets in this pass. A close-looking ray or a current-price label is not automatically an executed entry price.

## Choices that must remain explicit

To implement the preceding safely requires decisions about swing/structure confirmation, impulse size, exact FVG definition/edges and overlap, tolerance for shared open/close prices, entry-timeframe priority, duplicate setups, pending expiry, execution costs, stop model, and target selection among multiple ERLs. This single video does not uniquely specify those numeric decisions. Use cross-video evidence where available, and label remaining defaults OUR CHOICE rather than “Bishop said.”
