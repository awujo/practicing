# Why the bot misses Kevin's trades

Study 2 (research/TREND_LTF_PLAN.md): why does the bot not see Kevin's own trades (tests/kevin_trades.json)?

For each trade, around Kevin's time (WINDOW_DAYS either side):
  1. D / W story state on his side (slk.trend_study.daily_state): is there a bias he is trading with?
  2. H4 stories on his side (tap -> H1 break of B) confirmed in the window; level distance to his entry.
  3. Kevin continuation levels (slk.trend_study.pattern_trades, H4/H2/H1, limit at the line) on his side filled in
     the window; the closest line to his entry, its stop vs his stop.
  4. If no H4 story is found: re-run the H4 and D stories with ONE filter off at a time and name the filters
     that make a story on his side appear in the window.
Report: reports/KEVIN_GAP.md.

    python -m slk.kevin_gap --data data/examples --out reports


| id                   | kevin                                                       | D story         | W story         | H4 story                                                                                                   | levels                                                                                                      | appears when     |
|:---------------------|:------------------------------------------------------------|:----------------|:----------------|:-----------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------|:-----------------|
| euraud-h4-sell-feb17 | H4 SELL 2026-02-17 03:00 entry 1.6748 stop 1.67667 (18.7 p) | same_target_hit | same_target_hit | 4 found; closest level 1.6742 (6.4 p from his entry), confirmed 2026-02-19 02:00, stop 1.6754, target      | 2 filled; closest H1 line 1.6721 (27.4 p from his entry) stop 1.6733 (12.1 p) at 2026-02-20T01:00, 2R lost  | -                |
| gbpaud-h2-sell-feb19 | H2 SELL 2026-02-19 00:00 entry 1.9125 stop 1.9143 (18.5 p)  | same_target_hit | opposite        | 3 found; closest level 1.9179 (53.8 p from his entry), confirmed 2026-02-19 02:00, stop 1.9189, target     | 1 filled; closest H1 line 1.9264 (139.0 p from his entry) stop 1.9282 (18.1 p) at 2026-02-16T14:00, 2R lost | -                |
| usdchf-h1-buy-jan21  | H1 BUY 2026-01-21 08:00 entry 0.78997 stop 0.78898 (9.9 p)  | opposite        | opposite        | none                                                                                                       | 4 filled; closest H4 line 0.78939 (5.8 p from his entry) stop 0.78795 (14.4 p) at 2026-01-21T12:00, 2R won  | no single filter |
| eurgbp-h4-sell-feb02 | H4 SELL 2026-02-02 08:00 entry 0.866 stop 0.8666 (6.6 p)    | opposite        | opposite        | 3 found; closest level 0.86702 (10.2 p from his entry), confirmed 2026-02-02 10:00, stop 0.86758, target   | 4 filled; closest H4 line 0.8632 (28.0 p from his entry) stop 0.86375 (5.5 p) at 2026-02-04T14:00, 2R lost  | -                |
| eurgbp-h4-buy-jan15  | H4 BUY 2026-01-15 00:00 entry 0.8675 stop 0.8657 (18.0 p)   | same            | same_target_hit | none                                                                                                       | 9 filled; closest H2 line 0.8678 (3.0 p from his entry) stop 0.86713 (6.7 p) at 2026-01-12T10:00, 2R lost   | no single filter |
| usdjpy-h1-buy-dec12  | H1 BUY 2025-12-12 12:00 entry 155.599 stop 155.45 (14.9 p)  | same_target_hit | opposite        | 2 found; closest level 155.69 (9.6 p from his entry), confirmed 2025-12-11 06:00, stop 155.55, invalidated | 1 filled; closest H1 line 156.59 (99.1 p from his entry) stop 156.55 (3.9 p) at 2025-12-10T13:00, 2R lost   | -                |
