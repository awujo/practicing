# Kevin's trades: replay check

**0/6 PASS** (same pair and side, filled within 3 days of his time, entry and stop each
within 5 pips). Source of each trade: tests/kevin_trades.json (transcript + frames).

Entry settings: `qmr_entry` = trigger, `qmr_stop_pips` = 18.0, `entry_tfs` = {"D": ["H4", "H2"], "W": ["D", "H4"], "M": ["W", "D"]}

| Result | Trade | Kevin (entry / stop / TP) | Bot | Bot result |
|---|---|---|---|---|
| **FAIL** | euraud-h4-sell-feb17 | H4 SELL 2026-02-17 03:00: 1.6748 / 1.67667 / 1.666 | H4 continuation SELL fill 2026-05-26 07:00: 1.6255 / 1.6273 / TP1 1.6228 TP2 1.6111 (TRIGGERED continuation H4: entry off 493.0 pips, stop off 493.5 pips, 98.2 days from Kevin's time) | TP1 win, TP2 loss |
| **FAIL** | gbpaud-h2-sell-feb19 | H2 SELL 2026-02-19 00:00: 1.9125 / 1.9143 / 1.9029 | H2 qmr SELL fill -: 1.9076 / 1.9083 / TP1 1.9065 TP2 1.8997 (MISSED qmr H2: entry off 49.0 pips, stop off 59.5 pips, 7.2 days from Kevin's time) | TP1 -, TP2 - |
| **FAIL** | usdchf-h1-buy-jan21 | H1 BUY 2026-01-21 08:00: 0.78997 / 0.78898 / 0.7913 | H2 continuation BUY fill -: 0.79149 / 0.79085 / TP1 0.79245 TP2 0.79579 (MISSED continuation H2: entry off 15.2 pips, stop off 18.7 pips, 64.2 days from Kevin's time) | TP1 -, TP2 - |
| **FAIL** | eurgbp-h4-sell-feb02 | H4 SELL 2026-02-02 08:00: 0.866 / 0.8666 / 0.8627 | H2 continuation SELL fill 2026-09-08 16:00: 0.85883 / 0.85898 / TP1 0.85861 TP2 0.84546 (TRIGGERED continuation H2: entry off 71.7 pips, stop off 76.2 pips, 218.3 days from Kevin's time) | TP1 win, TP2 loss |
| **FAIL** | eurgbp-h4-buy-jan15 | H4 BUY 2026-01-15 00:00: 0.8675 / 0.8657 / 0.8723 | H2 continuation BUY fill 2026-01-28 14:00: 0.86758 / 0.86697 / TP1 0.8685 TP2 0.87456 (TRIGGERED continuation H2: entry off 0.8 pips, stop off 12.7 pips, 13.6 days from Kevin's time) | TP1 loss, TP2 loss |
| **FAIL** | usdjpy-h1-buy-dec12 | H1 BUY 2025-12-12 12:00: 155.599 / 155.45 / 156.049 | H4 continuation BUY fill -: 155.66 / 155.55 / TP1 155.82 TP2 157.9 (MISSED continuation H4: entry off 5.6 pips, stop off 9.7 pips, 13.9 days from Kevin's time) | TP1 -, TP2 - |
