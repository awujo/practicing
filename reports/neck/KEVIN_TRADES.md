# Kevin's trades: replay check

**1/6 PASS** (same pair and side, filled within 3 days of his time, entry and stop each
within 5 pips). Source of each trade: tests/kevin_trades.json (transcript + frames).

Entry settings: `qmr_entry` = neck, `qmr_stop_pips` = 18.0, `entry_tfs` = {"D": ["H4", "H2"], "W": ["D", "H4"], "M": ["W", "D"]}

| Result | Trade | Kevin (entry / stop / TP) | Bot | Bot result |
|---|---|---|---|---|
| **PASS** | euraud-h4-sell-feb17 | H4 SELL 2026-02-17 03:00: 1.6748 / 1.67667 / 1.666 | H4 qmr SELL fill 2026-02-18 02:00: 1.6749 / 1.6767 / TP1 1.6723 TP2 1.6623 (TRIGGERED qmr H4: entry off 1.5 pips, stop off 0.8 pips, 1.0 days from Kevin's time) | TP1 win, TP2 win |
| **FAIL** | gbpaud-h2-sell-feb19 | H2 SELL 2026-02-19 00:00: 1.9125 / 1.9143 / 1.9029 | H4 qmr SELL fill -: 1.9091 / 1.9109 / TP1 1.9064 TP2 1.8997 (MISSED qmr H4: entry off 33.7 pips, stop off 33.7 pips, 6.9 days from Kevin's time) | TP1 -, TP2 - |
| **FAIL** | usdchf-h1-buy-jan21 | H1 BUY 2026-01-21 08:00: 0.78997 / 0.78898 / 0.7913 | H4 qmr BUY fill 2026-03-25 21:00: 0.79112 / 0.78932 / TP1 0.79386 TP2 0.79579 (TRIGGERED qmr H4: entry off 11.5 pips, stop off 3.4 pips, 63.5 days from Kevin's time) | TP1 win, TP2 win |
| **FAIL** | eurgbp-h4-sell-feb02 | H4 SELL 2026-02-02 08:00: 0.866 / 0.8666 / 0.8627 | H2 qmr SELL fill 2026-07-01 07:00: 0.86124 / 0.8619 / TP1 0.86025 TP2 0.86025 (TRIGGERED qmr H2: entry off 47.6 pips, stop off 47.0 pips, 149.0 days from Kevin's time) | TP1 win, TP2 win |
| **FAIL** | eurgbp-h4-buy-jan15 | H4 BUY 2026-01-15 00:00: 0.8675 / 0.8657 / 0.8723 | H2 qmr BUY fill 2026-01-14 19:00: 0.86654 / 0.86558 / TP1 0.86804 TP2 0.86804 (TRIGGERED qmr H2: entry off 9.6 pips, stop off 1.2 pips, 0.2 days from Kevin's time) | TP1 loss, TP2 loss |
| **FAIL** | usdjpy-h1-buy-dec12 | H1 BUY 2025-12-12 12:00: 155.599 / 155.45 / 156.049 | H4 qmr BUY fill 2025-12-08 00:00: 155.11 / 154.93 / TP1 155.38 TP2 155.62 (TRIGGERED qmr H4: entry off 49.1 pips, stop off 52.2 pips, 4.5 days from Kevin's time) | TP1 loss, TP2 loss |
