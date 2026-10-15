# Kevin's trades: replay check

**0/6 PASS** (same pair and side, filled within 3 days of his time, entry and stop each
within 5 pips). Source of each trade: tests/kevin_trades.json (transcript + frames).

Entry settings: `qmr_entry` = trigger, `qmr_stop_pips` = 18.0, `entry_tfs` = {"D": ["H4", "H2"], "W": ["D", "H4"], "M": ["W", "D"]}

| Result | Trade | Kevin (entry / stop / TP) | Bot | Bot result |
|---|---|---|---|---|
| **FAIL** | euraud-h4-sell-feb17 | H4 SELL 2026-02-17 03:00: 1.6748 / 1.67667 / 1.666 | H4 continuation SELL fill 2026-07-13 07:00: 1.6471 / 1.6486 / TP1 1.6448 TP2 1.6111 (TRIGGERED continuation H4: entry off 276.7 pips, stop off 280.2 pips, 146.2 days from Kevin's time) | TP1 win, TP2 timeout |
| **FAIL** | gbpaud-h2-sell-feb19 | H2 SELL 2026-02-19 00:00: 1.9125 / 1.9143 / 1.9029 | H2 qmr SELL fill 2026-02-23 15:00: 1.9119 / 1.9127 / TP1 1.9107 TP2 1.8997 (TRIGGERED qmr H2: entry off 6.2 pips, stop off 16.2 pips, 4.6 days from Kevin's time) | TP1 loss, TP2 loss |
| **FAIL** | usdchf-h1-buy-jan21 | H1 BUY 2026-01-21 08:00: 0.78997 / 0.78898 / 0.7913 | H2 continuation BUY fill 2026-03-29 21:00: 0.79504 / 0.79443 / TP1 0.79595 TP2 0.81043 (TRIGGERED continuation H2: entry off 50.7 pips, stop off 54.5 pips, 67.5 days from Kevin's time) | TP1 loss, TP2 loss |
| **FAIL** | eurgbp-h4-sell-feb02 | H4 SELL 2026-02-02 08:00: 0.866 / 0.8666 / 0.8627 | H2 qmr SELL fill 2026-10-08 04:00: 0.84826 / 0.84942 / TP1 0.84649 TP2 0.84577 (TRIGGERED qmr H2: entry off 177.4 pips, stop off 171.8 pips, 247.8 days from Kevin's time) | TP1 win, TP2 win |
| **FAIL** | eurgbp-h4-buy-jan15 | H4 BUY 2026-01-15 00:00: 0.8675 / 0.8657 / 0.8723 | H2 continuation BUY fill 2026-01-28 14:00: 0.86758 / 0.86697 / TP1 0.8685 TP2 0.87456 (TRIGGERED continuation H2: entry off 0.8 pips, stop off 12.7 pips, 13.6 days from Kevin's time) | TP1 loss, TP2 loss |
| **FAIL** | usdjpy-h1-buy-dec12 | H1 BUY 2025-12-12 12:00: 155.599 / 155.45 / 156.049 | H2 qmr BUY fill -: 154.69 / 154.58 / TP1 154.96 TP2 155.53 (MISSED qmr H2: entry off 90.8 pips, stop off 86.7 pips, 24.6 days from Kevin's time) | TP1 -, TP2 - |
