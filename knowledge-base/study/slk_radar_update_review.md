# SLK Radar update: evidence and proposed fit

Reviewed 2026-10-24. This is a feature review, not an implementation of new alerts or an extension.

## Evidence preserved

- [Extraction workflow40042615451](https://github.com/awujo/practicing/actions/runs/40042615451): successful, only the new release asset670611585 was processed. Duration809.56s (13:30); small Whisper model,10s frame interval,81 sampled frames across4 contact sheets. Generated evidence committed as520d6d5.
- [Timestamped transcript](../videos/kevin-devt-building-the-slk-bias-bot-new-featuress-on-slkradar-journal-feature-alert-replay-b/transcript.txt) and [frame index](../frames/kevin-devt-building-the-slk-bias-bot-new-featuress-on-slkradar-journal-feature-alert-replay-b/index.md). All4 contact sheets were inspected; selected native frames below resolve small UI text.
- Bishop material read directly from `claude-bishop-aggressive`, commit7fe38461f729e32b9bcefcf882d46ee398981413. That branch was not modified or merged. Primary [confirmation-entry transcript](https://github.com/awujo/practicing/blob/7fe38461f729e32b9bcefcf882d46ee398981413/knowledge-base/videos/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/transcript.txt); sheets007,008,011 inspected alongside speech. Supplementary entries notes were background, not a substitute for primary evidence.

Whisper mistranscribes terminology. Screen text is preferred for product names and conditions; a displayed pattern name does not establish its exact algorithm.

## Features demonstrated

| Feature | Evidence in the new video | Fit for our system |
|---|---|---|
| Chrome extension with a draggable chart dock; detects current symbol; regular/Deriv/crypto tabs |00:34–03:38; sheet001 | An optional desktop input interface. The Mini App can offer the same alert form for phone users. |
| User-set price alert; crossing, close above, close below, rejection; timeframe selection |03:44–05:03; sheet002 | New per-user watch conditions, separate from automatic story alerts. A crossing and a candle-close condition must have different trigger rules. |
| Confirmation selector: `4th's pin-bar conf…` and CISD |05:04–06:11 and06:53–07:19; [native05:10](examples/radar-update-t310.jpg), [native07:00](examples/radar-update-t420.jpg) | New named models; do not silently rename existing continuation/QMR models. Exact pin-bar/CISD definitions need specification before coding. |
| Optional lower-timeframe engulfing filter |06:12–06:45; [native06:30](examples/radar-update-t390.jpg) | Screen mapping:30m→15m,1h→30m,2h→1h,3h→1h,4h→2h. Optional filter, not proof of better performance. |
| Custom message, expiry, explanation of what will trigger, one Telegram notification |03:53–04:18; native07:00 | Per-user lifecycle, expiry and deduplication; broker feed is stated explicitly. The screen warns feed prices may differ from the chart. |
| Account settings and connected browsers |07:24–08:23 | Our Telegram authentication already identifies users; an extension would need its own securely paired browser session. |
| History filters: event type, market family, direction, timeframe chain, journal status |08:24–09:13; [native08:40](examples/radar-update-t520.jpg) | Extend existing scoped history rather than a global shared history. |
| Alert replay with timeframe changes and step-forward controls |09:14–10:48; [native09:40](examples/radar-update-t580.jpg) | Replay from the alert's actual knowledge time, with no future bars initially exposed. Narrator says candle refresh is hourly, so this is not evidence of instantaneous updates. |
| Journal: entry, stop, target, R, P/L, notes |10:53–11:10; [native10:50](examples/radar-update-t650.jpg) | Link small journal records to alerts; distinguish manually reported results from paper simulation and broker fills. Images/support comments are described as future additions, not established shipped features. |
| Telegram chart previews and replay link |11:12–13:24; sheets003–004 | Server-generated chart previews with marked levels and closed-bar timestamps. |

At10:24–10:33 another confirmation type is described as something he will add. The wording is unclear; it must not be presented as an already-supported model.

## What Bishop actually teaches

The same primary transcript distinguishes the H4 break confirming a daily bias (00:42–01:03) from an entry confirmation after price returns to the entry area (04:54 onward). These are two separate events.

- 01:44–02:15: after the H4 breakout candle closes, scale down toH2 and identify its breakout/liquidity and nearest key level for a direct entry.
- 02:30–03:45: direct entry at the H4 liquidity/key level is another approach.
- 04:54–06:20: confirmation entry waits for a key-level reaction, then examines a lower timeframe. Bishop listsH3/H2/H1/M45/M30/M15/M5. He explicitly leaves waiting for the higher rejection candle to close as a discretionary choice; that is not permission to label an unfinished lower confirmation candle as closed.
- 06:20–07:10: breakout and sweep+break are his stated preferences. This is a teaching preference, not measured evidence of performance.
- 07:45–09:19: his engulfing description involves invalidating an opposing open-close key level, including consecutive same-direction candles. It must not be replaced without justification by a generic textbook two-candle engulfing test.
- 09:18–11:40: another illustrated buy pattern sweeps the reference candle's low while its high remains standing, then yields a V-shaped level for a retest; sell is mirrored. He describes a related lower-timeframe engulfing as common but not guaranteed. [Bishop sheet011](https://github.com/awujo/practicing/blob/7fe38461f729e32b9bcefcf882d46ee398981413/knowledge-base/frames/bishop-defi-bishop-study-20-minute-series-part-5-approach-to-direct-and-confirmation-entries-case/sheets/sheet_011.jpg) shows the sequence.

The last pattern is a plausible connection to Radar's pin-bar feature. The videos do not prove identical candle-index, close, tolerance, expiry or entry rules, and Bishop's material does not establish Radar's exact CISD algorithm. Keep that uncertainty explicit.

## Recommended design order

1. Define the confirmation models from timestamped examples: reference candle, sweep side, preserved extreme, required body close, location tolerance, subsequent retest, invalidation, expiry and trigger-timeframe ordering. Record both buy and sell examples and non-examples. Define CISD independently rather than borrowing a name.
2. Add per-user alert watches to the backend and Mini App: symbol/provider, chosen level, condition, timeframe, optional engulfing mapping, expiry and note. Keep manual watches distinct from entries tied to an eligible confirmed story. A manual level watch should not require the automatic scanner to discover that level first.
3. Start with conditions supported by real data. Our existing H1 history can supportH1/H2/H4, but cannot reconstructM5/M15/M30/M45 bars. AnH1 confirmation requiringM30 engulfing also needs finer data. H2→H1 andH4→H2 filters can use existing history. Add and validateH3 separately if selected. Subhour models need a finer provider feed and faster scheduling.
4. Evaluate on closed candles using provider timestamps and existing broker calendars. Only accept bars with close time≤evaluation time. Catch up missed closed bars, expire invalid watches, and claim each delivery atomically. A quote crossing needs actual sampled prices or suitable higher-resolution history; hourly candles cannot establish the exact crossing time or intrabar sequence.
5. Keep the hourly story scanner. Run short, separate confirmation checks over only pending selected watches, sharing symbol/timeframe downloads. GitHub scheduling remains best-effort; use an authenticated external timer or an always-running service where timely subhour checks matter. No language-model calls are needed per check.
6. Build the desktop Chrome extension after the backend and phone form work: ManifestV3, limited chart-site permissions, draggable isolated UI, symbol/provider detection and explicit user-selected price/timeframe. Pair it to a Telegram user using a revocable scoped token; never embed the Telegram bot token or use the cron secret as a client credential. The backend evaluates and sends alerts even when the chart closes.
7. Add replay/journal/chart previews after the signal definitions are tested. Reuse candle storage and reference alert snapshots instead of duplicating research datasets in MySQL.

Chrome Web Store publication requires a developer account, listing assets and review. Standard Chrome on Android/iPhone does not offer desktop Chrome Web Store extensions; the Mini App remains the phone interface. Installing an extension is not required for Telegram delivery.

## Boundary of completed work

Completed: video extraction, primary transcript/frame review, Bishop comparison and this design assessment. Existing settings-save fixdb37169 is deployed and passed real MySQL full-form Deriv saves for owner/tenant users. No confirmation engine, price-watch API, journal/replay UI or Chrome extension was built or published in this review.
