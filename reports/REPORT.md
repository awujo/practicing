# SLK story-line backtest

Each row = a confirmed story (tap-reject-close + breakout of point B). Trade view: entry at the
confirmation close, stop beyond the tap wick, target = nearest opposite level/swing.
`win%` = target before stop. `expectancy_R` = average result in R (>0 = profitable before costs).
`kevin_target%` = target reached before an origin close back through the level (Kevin's invalidation).

Settings: `{"level_pivot": 1, "swing_pivot": 2, "trend_mode": "leg", "b_pivot": 1, "use_oc": true, "trend_filter": true, "tap_tol_pips": 0.0, "level_tol_pips": 0.0, "max_wait": 5, "max_retaps": 3, "same_bar_close": true, "htf_filter": true, "stop_buffer_pips": 2.0, "max_hold": 20, "mw_conflict_filter": true, "sweep_start": true, "most_recent_level": true, "flip_end": true, "htf_targets": true, "overlap_rule": true, "overlap_tol_pips": 3.0, "align_retap_ends": true, "alignment_start": true, "pullback_levels": true, "cadjpy_zone": true, "cadjpy_exception": true, "next_day_rule": "require"}`

## By story

| story   |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:--------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| D       |      5186 |   80.1 |           0.34 |         -0.007 |     -34.9 |            82.5 |               85.3 |
| M       |       121 |   67.8 |           0.52 |         -0.018 |      -2.2 |            69.4 |              406.7 |
| W       |       855 |   76.8 |           0.35 |         -0.022 |     -19   |            79.3 |              193.7 |

## By story and side

|               |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:--------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'BUY')  |      2682 |   80.5 |           0.32 |         -0.014 |     -37.9 |            83   |               90.5 |
| ('D', 'SELL') |      2504 |   79.6 |           0.37 |          0.001 |       3   |            81.9 |               79.2 |
| ('M', 'BUY')  |        60 |   75   |           0.57 |          0.074 |       4.5 |            75   |              421.9 |
| ('M', 'SELL') |        61 |   60.7 |           0.46 |         -0.11  |      -6.7 |            63.9 |              355.3 |
| ('W', 'BUY')  |       446 |   78.7 |           0.36 |         -0.007 |      -3.2 |            80.9 |              213.9 |
| ('W', 'SELL') |       409 |   74.8 |           0.34 |         -0.039 |     -15.8 |            77.5 |              172.7 |

## By story and higher-TF agreement

|                    |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:-------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'agree')     |      4605 |   79.7 |           0.35 |         -0.008 |     -37.2 |            82.1 |               85.9 |
| ('D', 'not agree') |       581 |   83.1 |           0.27 |          0.004 |       2.4 |            85.5 |               79.4 |
| ('M', 'no HTF')    |       121 |   67.8 |           0.52 |         -0.018 |      -2.2 |            69.4 |              406.7 |
| ('W', 'agree')     |       711 |   76.5 |           0.33 |         -0.039 |     -27.8 |            78.9 |              197.2 |
| ('W', 'not agree') |       144 |   78.5 |           0.46 |          0.061 |       8.8 |            81.2 |              178.2 |

## By story and level type

|                |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:---------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'A')     |       332 |   80.4 |           0.29 |          0.014 |       4.5 |            81.9 |               83.2 |
| ('D', 'OC')    |       609 |   73.4 |           0.58 |         -0.048 |     -29.2 |            77.2 |               68.6 |
| ('D', 'V')     |       312 |   80.1 |           0.24 |         -0.046 |     -14.3 |            82.7 |               94.9 |
| ('D', 'align') |       786 |   82.6 |           0.42 |          0.014 |      10.8 |            87   |               93.8 |
| ('D', 'flip')  |      2444 |   80.9 |           0.29 |         -0.006 |     -14   |            82.6 |               86.2 |
| ('D', 'sweep') |       703 |   80.2 |           0.32 |          0.01  |       7.3 |            81.9 |               84.3 |
| ('M', 'A')     |        10 |   50   |           0.35 |         -0.276 |      -2.8 |            50   |              375.8 |
| ('M', 'OC')    |        11 |   72.7 |           0.43 |          0.039 |       0.4 |            81.8 |              382.1 |
| ('M', 'V')     |        15 |   93.3 |           0.45 |          0.31  |       4.6 |            93.3 |              446.3 |
| ('M', 'flip')  |        65 |   63.1 |           0.6  |         -0.053 |      -3.5 |            64.6 |              421.1 |
| ('M', 'sweep') |        20 |   70   |           0.45 |         -0.054 |      -1.1 |            70   |              298.7 |
| ('W', 'A')     |        78 |   70.5 |           0.36 |         -0.066 |      -5.1 |            71.8 |              165.8 |
| ('W', 'OC')    |        79 |   79.7 |           0.3  |         -0.022 |      -1.8 |            81   |              213.9 |
| ('W', 'V')     |        83 |   71.1 |           0.36 |         -0.116 |      -9.6 |            72.3 |              247.7 |
| ('W', 'flip')  |       456 |   76.5 |           0.35 |         -0.03  |     -13.9 |            79.6 |              181.8 |
| ('W', 'sweep') |       159 |   82.4 |           0.34 |          0.072 |      11.4 |            84.9 |              199   |

## By story and rule

|                           |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:--------------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'alignment')        |       786 |   82.6 |           0.42 |          0.014 |      10.8 |            87   |               93.8 |
| ('D', 'cadjpy')           |       275 |   66.9 |           0.94 |         -0.069 |     -18.9 |            73.5 |               43.1 |
| ('D', 'cadjpy+overlap')   |         1 |    0   |           1.2  |         -1     |      -1   |             0   |               97.3 |
| ('D', 'flip')             |        19 |   63.2 |           0.61 |         -0.14  |      -2.7 |            78.9 |               59.1 |
| ('D', 'flip+overlap')     |         3 |   33.3 |           1.17 |         -0.57  |      -1.7 |            33.3 |               49.4 |
| ('D', 'standard')         |      3055 |   82   |           0.27 |         -0.003 |      -8.6 |            83.6 |               86.6 |
| ('D', 'standard+overlap') |       344 |   69.8 |           0.4  |         -0.059 |     -20.2 |            71.8 |               93.8 |
| ('D', 'sweep_start')      |       703 |   80.2 |           0.32 |          0.01  |       7.3 |            81.9 |               84.3 |
| ('M', 'flip')             |         7 |   57.1 |           0.26 |         -0.274 |      -1.9 |            57.1 |              355.3 |
| ('M', 'standard')         |        94 |   68.1 |           0.55 |          0.008 |       0.8 |            70.2 |              421.9 |
| ('M', 'sweep_start')      |        20 |   70   |           0.45 |         -0.054 |      -1.1 |            70   |              298.7 |
| ('W', 'flip')             |         5 |   60   |           0.44 |         -0.152 |      -0.8 |            60   |              121.2 |
| ('W', 'flip+overlap')     |         1 |  100   |           0.55 |          0.55  |       0.6 |           100   |               86.4 |
| ('W', 'standard')         |       650 |   75.8 |           0.35 |         -0.046 |     -29.9 |            78.5 |              193.2 |
| ('W', 'standard+overlap') |        40 |   72.5 |           0.41 |         -0.005 |      -0.2 |            72.5 |              191.2 |
| ('W', 'sweep_start')      |       159 |   82.4 |           0.34 |          0.072 |      11.4 |            84.9 |              199   |

## By year (D story)

|   year |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|-------:|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
|   2018 |       601 |   73.2 |           0.53 |         -0.022 |     -13.2 |            75.5 |               85.8 |
|   2019 |       755 |   77.9 |           0.38 |         -0.007 |      -5.3 |            81.9 |               69.3 |
|   2020 |       759 |   81.4 |           0.35 |          0.008 |       5.8 |            82.2 |               87.4 |
|   2021 |       725 |   81.9 |           0.24 |         -0.02  |     -14.3 |            83.9 |               77.6 |
|   2022 |       612 |   81.7 |           0.3  |         -0.004 |      -2.2 |            85   |              107.4 |
|   2023 |       647 |   80.5 |           0.33 |         -0.025 |     -15.9 |            83.2 |              103.5 |
|   2024 |       552 |   81.2 |           0.25 |         -0.03  |     -16.4 |            84.1 |               75   |
|   2025 |       535 |   83.2 |           0.39 |          0.05  |      26.6 |            84.5 |               89.2 |

## By pair (D story)

| pair   |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:-------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| AUDCAD |       187 |   80.2 |           0.27 |         -0.011 |      -2.1 |            81.8 |               74.4 |
| AUDCHF |       188 |   76.1 |           0.45 |          0.018 |       3.4 |            77.1 |               55.2 |
| AUDJPY |        92 |   76.1 |           0.37 |         -0.046 |      -4.3 |            82.6 |               89.3 |
| AUDNZD |       203 |   84.7 |           0.22 |         -0.007 |      -1.4 |            88.2 |               61.4 |
| AUDUSD |       151 |   79.5 |           0.23 |         -0.057 |      -8.7 |            82.8 |               72.7 |
| CADCHF |       134 |   82.1 |           0.21 |         -0.023 |      -3.1 |            82.8 |               58.4 |
| CADJPY |       197 |   80.7 |           0.3  |         -0.02  |      -4   |            81.7 |               94.2 |
| CHFJPY |       196 |   78.1 |           0.43 |          0.012 |       2.4 |            81.1 |               94   |
| EURAUD |       197 |   82.7 |           0.51 |         -0.01  |      -1.9 |            84.3 |              125.1 |
| EURCAD |       186 |   82.8 |           0.23 |         -0.032 |      -6   |            84.4 |               99.4 |
| EURCHF |       149 |   75.2 |           0.38 |         -0.001 |      -0.1 |            76.5 |               55.7 |
| EURGBP |       226 |   79.2 |           0.28 |         -0.063 |     -14.2 |            80.5 |               49.9 |
| EURJPY |       199 |   80.4 |           0.41 |          0.066 |      13.1 |            82.9 |              104.3 |
| EURNZD |       187 |   75.9 |           0.28 |         -0.067 |     -12.5 |            80.7 |              135.6 |
| EURUSD |       150 |   82   |           0.54 |          0.015 |       2.2 |            84.7 |               85.3 |
| GBPAUD |       167 |   83.8 |           0.28 |          0.013 |       2.2 |            85   |              147.2 |
| GBPCAD |       185 |   78.9 |           0.56 |         -0.046 |      -8.5 |            81.1 |              117.6 |
| GBPCHF |       161 |   69.6 |           0.7  |         -0.027 |      -4.4 |            73.3 |               93.8 |
| GBPJPY |       189 |   81   |           0.33 |          0.04  |       7.6 |            82   |              146.4 |
| GBPNZD |       188 |   76.6 |           0.31 |         -0.057 |     -10.7 |            78.7 |              176.5 |
| GBPUSD |       224 |   85.7 |           0.25 |          0.032 |       7.2 |            86.2 |              118.4 |
| NZDCAD |       230 |   87.4 |           0.22 |          0.036 |       8.3 |            90.4 |               68.8 |
| NZDCHF |       212 |   79.2 |           0.4  |          0.061 |      12.9 |            82.1 |               55.4 |
| NZDJPY |       206 |   81.1 |           0.27 |          0.003 |       0.6 |            84   |               86.9 |
| NZDUSD |       224 |   82.6 |           0.32 |          0.009 |       2   |            85.3 |               69   |
| USDCAD |       181 |   81.8 |           0.29 |         -0.025 |      -4.6 |            84   |               83.6 |
| USDCHF |       203 |   77.8 |           0.33 |         -0.021 |      -4.4 |            79.8 |               62.3 |
| USDJPY |       174 |   74.7 |           0.38 |         -0.035 |      -6.1 |            81   |               85.6 |

## M/W conflict filter (D story)

Filter is on. Tables above score tradable stories only; here all D stories vs the ones the
filter keeps vs the ones it removes (latest confirmed M and W stories pointed opposite ways).

| view                       |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:---------------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| all D stories (filter off) |      6267 |   80.8 |           0.34 |         -0.003 |     -20.3 |            83.1 |               85.5 |
| tradable (filter on)       |      5186 |   80.1 |           0.34 |         -0.007 |     -34.9 |            82.5 |               85.3 |
| NO_TRADE: M/W conflict     |      1081 |   84   |           0.29 |          0.013 |      14.6 |            86   |               86.5 |

## By story and Next Day Rule (label)

|                   |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'next day') |      4910 |   80.9 |           0.31 |         -0.003 |     -15   |            83   |               87.4 |
| ('M', 'next day') |       121 |   67.8 |           0.52 |         -0.018 |      -2.2 |            69.4 |              406.7 |
| ('W', 'next day') |       855 |   76.8 |           0.35 |         -0.022 |     -19   |            79.3 |              193.7 |

## Variants (side by side, to choose defaults)

Same pairs and years for every line. Bias variants: tradable stories, trade view (entry at the
confirmation close, stop beyond the tap wick + buffer, target), `win%` = target before stop, `avg_R` /
`total_R` = result in R. Entry variants: filled entries on the default-rule stories, TP1 and TP2.
First value of each setting = current default.

| variant                         |   trades |   win% |   avg_R |   total_R |
|:--------------------------------|---------:|-------:|--------:|----------:|
| next_day_rule=require           |     6162 |   79.4 |  -0.009 |     -56.1 |
| next_day_rule=flag              |     9991 |   75.9 |  -0.019 |    -194.1 |
| flag: next-day breakouts only   |     5165 |   79.1 |   0.01  |      50.2 |
| flag: same-day breakouts only   |     4582 |   72.9 |  -0.05  |    -230.8 |
| flag: no breakout (cadjpy, n/a) |      244 |   65.6 |  -0.055 |     -13.5 |
| trend_mode=leg                  |     6162 |   79.4 |  -0.009 |     -56.1 |
| trend_mode=protected            |     6110 |   79.7 |  -0.005 |     -33.2 |
| cadjpy_exception=on             |     6162 |   79.4 |  -0.009 |     -56.1 |
| cadjpy_exception=off            |     5964 |   80   |  -0.006 |     -35.5 |
| pullback_levels=on              |     6162 |   79.4 |  -0.009 |     -56.1 |
| pullback_levels=off             |     4760 |   79.2 |  -0.002 |     -10.5 |
| entry_alignment=d_h4 (TP1)      |      550 |   32.2 |  -0.167 |     -91.9 |
| entry_alignment=d_h4 (TP2)      |      550 |   11.8 |   0.113 |      61.9 |
| entry_alignment=w_d_h4 (TP1)    |      502 |   31.9 |  -0.176 |     -88.3 |
| entry_alignment=w_d_h4 (TP2)    |      502 |   10.8 |   0.004 |       2   |
| entry_alignment=off (TP1)       |      628 |   32   |  -0.172 |    -108   |
| entry_alignment=off (TP2)       |      628 |   11.5 |   0.092 |      58.1 |
| entry_tfs=D=H4,H2 (TP1)         |      550 |   32.2 |  -0.167 |     -91.9 |
| entry_tfs=D=H4,H2 (TP2)         |      550 |   11.8 |   0.113 |      61.9 |
| entry_tfs=D=H4,H2,H1 (TP1)      |      801 |   31   |  -0.194 |    -155.8 |
| entry_tfs=D=H4,H2,H1 (TP2)      |      801 |   12.6 |   0.112 |      89.4 |
