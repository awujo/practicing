# Independent source review: USDCHF p23 and GBPAUD p59–60

2026-10-24. Source-only reconstruction for replay against newly located existing local data. No data acquisition, candle analysis, fixture changes, engine edits or acceptance promotion. The source itself was rendered and visually inspected, rather than relying only on legacy annotations.

Primary artifact: `knowledge-base/supplementary/source/bishops_trade_chart_examples.pdf`, SHA256 `e6393b2e35cf79e3b3f8b63095cce9224ded8487f845e3dd29172730288c2729`. Independently rendered pages22,23,59,60 at maximum dimension2800 using pdftoppm; inspected complete images `/tmp/bishop-p22.png`, `/tmp/bishop-p23.png`, `/tmp/bishop-p59.png`, `/tmp/bishop-p60.png`. These temporary paths are conveniences, not replacement source artifacts. Crosschecked corresponding observations in `full_supplement_study.md` and fixture IDs in `tests/bishop_examples.json` without modifying them.

## Page boundary correction

**PDF p22 is Silver, not USDCHF context.** It contains XAGUSD H2 on Saxo and a separate XAGUSD.pi mobile broker chart. Its Daily bearish breakout/PDH swept, H4-with-idm and H2 engulfing annotations belong to Silver. They cannot supply missing USDCHF bias, setup family, broker execution or clock. Both USDCHF snapshots appear together on **p23**.

## Snapshot clocks independently read

Each header is a TradingView chart-creation timestamp. UTC conversion subtracts its explicitly printed UTC+1 offset. The UTC interval below preserves minute precision; seconds, setup/placement/fill times and execution are not inferred.

| Page/view | Printed source header | UTC snapshot minute, end exclusive |
|---|---|---|
| p23 USDCHF right (earlier) | Jul09,2026 15:41 UTC+1 | `[2026-07-09T14:41:00Z, 2026-07-09T14:42:00Z)` |
| p23 USDCHF left (later) | Jul10,2026 07:43 UTC+1 | `[2026-07-10T06:43:00Z, 2026-07-10T06:44:00Z)` |
| p59 GBPAUD Daily left | May12,2026 09:41 UTC+1 | `[2026-05-12T08:41:00Z, 2026-05-12T08:42:00Z)` |
| p59 GBPAUD H4 right | May12,2026 09:44 UTC+1 | `[2026-05-12T08:44:00Z, 2026-05-12T08:45:00Z)` |
| p60 GBPAUD M45 | May12,2026 09:52 UTC+1 | `[2026-05-12T08:52:00Z, 2026-05-12T08:53:00Z)` |

For identity control only, Silver p22's chart header reads Jul13,2026 06:24 UTC+1 (05:24 UTC minute). Its mobile status-bar clock23:27 has no independently established date/zone and must not be combined with USDCHF or the TradingView header.

## USDCHF p23: two illustrations of one region

Both charts explicitly identify **USDCHF · 1h · FOREXCOM**. Short-tool reward lies below entry. Independently readable numerical coordinates:

| View / existing observation ID | Entry | Stop | Target |
|---|---:|---:|---:|
| Earlier right / `pdf-p23-usdchf-sell-2` | 0.80736 | 0.80787 | 0.80532 |
| Later left / `pdf-p23-usdchf-sell-1` | 0.80736 | 0.80783 | 0.80535 |

The left target is 0.80535, not the old approximate0.80525. These source values agree with the existing unresolved fixtures. The 4.00R versus approximately4.28R implied drawing ratios reflect the distinct displayed boundaries; they are not two independently executed wins. The stop/target differences are observations between two snapshots, not proof of an actual order amendment or two accounts.

Visible relative structure: a prior decline, rebound into layered horizontal body/reference prices around the marked short region, renewed bearish move. The earlier right snapshot shows price below the drawn entry with the rest of the target area still to the right; the later left snapshot extends the same region and shows subsequent price below its target. This supports relative chronology and favorable excursion only.

**No printed CE-family, Daily/H4 bias annotation or explicit source-origin route appears on p23.** It is unsafe to call this a Daily-reject-Daily→H4 reaction→H1 engulf route merely because those models occur elsewhere. A bearish body sequence can support competing algorithm hypotheses, but it does not uniquely identify which references the author used, when they were available, or whether the entry was engulf/OC/breakout/direct. Record SELL illustration/H1 as known and the exact higher context/model as unresolved.

No broker screenshot/order ticket accompanies USDCHF p23. A left drawing boundary is not an issuance timestamp. Right snapshot's price already below entry does not prove a limit was live beforehand; left snapshot's later excursion does not establish that a filled order achieved TP. The two fixture observations remain correlated variants of the same short region and must not inflate independent trade count.

## GBPAUD p59–60: explicit Daily/H4/M45 route

All three chart views identify FOREXCOM. p59 is a Daily left view and H4 right view; p60 is explicitly **GBPAUD · 45 · FOREXCOM**, meaning M45, not M15 or H1.

The source labels directly establish:

1. Daily bearish breakout and `Daily reject Daily`, printed on both p59 context views and retained on p60. This is source SELL/Daily context annotation, not an exact event-availability clock.
2. p59 H4 marks **1st Entry**: `H4 breakout with idm / CE on ltf`, at the earlier/higher reaction region.
3. p59 H4 separately marks **2nd Entry**: `H4 breakout with idm / CE on ltf`, at the later/lower region. These are separate opportunities, not proof that both were personally filled.
4. p60 refines the **2nd Entry**, with the label `H4 breakout with idm / H4rH4 / M45 break with idm`. This supplies an actual named lower-timeframe model: M45 breakout-with-inducement following the H4-with-idm/reaction context. It must not be replaced with a generic H1 engulf route.
5. p60's short-tool coordinates independently read **entry1.87881, stop1.88000, target1.87390**. The target is1.87390, not1.87393. The printed plan risk is11.9 conventional FX pips and reward49.1pips (approximately4.13R), not a proof of exact fixed11-pip stop doctrine.

The visible M45 sequence contains an upswing to an earlier high, a fall, a rebound into the annotated second-entry region and a subsequent sharp decline below the drawn target. H4 places this within the second opportunity after an earlier one. Exact numbered break, liquidity/reference candle, reaction contact and retest/placement clock need source candle alignment; the leader line and box are not sufficient to establish them numerically.

The first entry's exact lower timeframe, entry price, stop and target are not supplied by p59. The p60 second-entry risk box cannot fill those missing first-entry fields. No broker order, trade count or realized P&L is shown on these pages. Author social links on p60 establish provenance, not execution. Visible price beyond target is excursion, not booked return.

## What existing H1 data can and cannot test

This review does not inspect or acquire market data. For a later declared alternate-feed diagnostic:

- USDCHF's H1 source view makes H1 OHLC a compatible nominal resolution for structural-candle comparison, subject to exact feed/anchor/coverage differences. It still cannot prove intrabar reaction-before-confirmation, actual order placement, bid/ask fill, spread or fill/stop/target order. Missing Daily/H4 source route remains missing even with many alternate candles.
- GBPAUD H1 can support declared Daily/H4 aggregation and a context diagnostic where its calendar/anchor/coverage are established. **H1 cannot reconstruct the actual M45 source candles.** A45-minute boundary splits hourly bars; no aggregation of H1 OHLC recovers the internal open/close/high/low distribution. This is a mathematical resolution limitation, not an implementation preference.
- GBPAUD full second-entry model replay therefore requires independently valid source/compatible finer data (e.g. M15 or finer with correct anchor), or manually verified source M45 candle observations. Interpolating H1, relabelling it M45, substituting H1 CE, or treating nearest available timeframe as a match would change the documented model.
- An H1 alternate-feed run may still demonstrate specific context predicates and measured mismatches. It must report GBPAUD M45 entry as unresolved/unsupported instead of a full teacher-example pass.

## Disposition

Independent source read agrees with both USDCHF price variants and GBPAUD second-entry prices, chart feeds, printed timeframes and snapshot timestamps. USDCHF source bias/model and all setup/fill/execution clocks remain unresolved. GBPAUD Daily SELL annotation and second-entry M45 model are verified at the source-label level, while exact numerical causal events and execution remain unresolved. No source tolerance is established here and no existing expected price should be altered to fit an alternate feed.
