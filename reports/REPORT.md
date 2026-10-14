# SLK story-line backtest

Each row = a confirmed story (tap-reject-close + breakout of point B). Trade view: entry at the
confirmation close, stop beyond the tap wick, target = nearest opposite level/swing.
`win%` = target before stop. `expectancy_R` = average result in R (>0 = profitable before costs).
`kevin_target%` = target reached before an origin close back through the level (Kevin's invalidation).

Settings: `{"level_pivot": 1, "swing_pivot": 2, "b_pivot": 1, "use_oc": true, "trend_filter": true, "tap_tol_pips": 0.0, "level_tol_pips": 0.0, "max_wait": 5, "max_retaps": 3, "same_bar_close": true, "htf_filter": true, "stop_buffer_pips": 2.0, "max_hold": 20, "mw_conflict_filter": true, "sweep_start": true, "most_recent_level": true, "flip_end": true, "htf_targets": true, "overlap_rule": true, "overlap_tol_pips": 3.0, "align_retap_ends": true, "alignment_start": true, "pullback_levels": true, "cadjpy_zone": true, "cadjpy_exception": true, "next_day_rule": "flag"}`

## By story

| story   |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:--------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| D       |      8748 |   77.4 |           0.37 |         -0.012 |    -101.6 |            80.2 |               71.2 |
| M       |       203 |   61.6 |           0.73 |         -0.051 |     -10.3 |            67   |              309.9 |
| W       |      1480 |   72.8 |           0.41 |         -0.033 |     -48.4 |            76.6 |              158.6 |

## By story and side

|               |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:--------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'BUY')  |      4309 |   76.8 |           0.36 |         -0.025 |    -108   |            79.8 |               76.1 |
| ('D', 'SELL') |      4439 |   77.9 |           0.37 |          0.001 |       6.4 |            80.5 |               66.3 |
| ('M', 'BUY')  |        88 |   67   |           0.81 |          0     |       0   |            68.2 |              353.1 |
| ('M', 'SELL') |       115 |   57.4 |           0.67 |         -0.09  |     -10.3 |            66.1 |              277.2 |
| ('W', 'BUY')  |       692 |   73.8 |           0.4  |         -0.024 |     -16.8 |            76.7 |              176.6 |
| ('W', 'SELL') |       788 |   72   |           0.42 |         -0.04  |     -31.6 |            76.5 |              142.4 |

## By story and higher-TF agreement

|                    |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:-------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'agree')     |      7609 |   77.4 |           0.37 |         -0.011 |     -82.1 |            80.2 |               71.7 |
| ('D', 'not agree') |      1139 |   77   |           0.36 |         -0.017 |     -19.6 |            80   |               68.1 |
| ('M', 'no HTF')    |       203 |   61.6 |           0.73 |         -0.051 |     -10.3 |            67   |              309.9 |
| ('W', 'agree')     |      1120 |   74.1 |           0.39 |         -0.029 |     -32.2 |            77.9 |              159.5 |
| ('W', 'not agree') |       360 |   68.9 |           0.45 |         -0.045 |     -16.2 |            72.8 |              151.7 |

## By story and level type

|                |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:---------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'A')     |       585 |   78.5 |           0.33 |          0.001 |       0.6 |            80.5 |               74.4 |
| ('D', 'OC')    |       810 |   73.6 |           0.55 |         -0.021 |     -17   |            76.9 |               66.6 |
| ('D', 'V')     |       587 |   76.7 |           0.32 |         -0.034 |     -20.2 |            79.6 |               81.8 |
| ('D', 'align') |       286 |   79.4 |           0.53 |         -0.001 |      -0.3 |            83.9 |               91.8 |
| ('D', 'flip')  |      4846 |   78   |           0.34 |         -0.012 |     -56.8 |            80.6 |               69.5 |
| ('D', 'sweep') |      1634 |   77.1 |           0.36 |         -0.005 |      -7.8 |            80   |               69.8 |
| ('M', 'A')     |        22 |   50   |           0.48 |         -0.37  |      -8.1 |            54.5 |              377.4 |
| ('M', 'OC')    |         8 |  100   |           0.42 |          0.421 |       3.4 |           100   |              267.8 |
| ('M', 'V')     |        27 |   63   |           0.72 |         -0.129 |      -3.5 |            66.7 |              418.4 |
| ('M', 'flip')  |       107 |   55.1 |           0.88 |         -0.036 |      -3.9 |            60.7 |              274.9 |
| ('M', 'sweep') |        39 |   76.9 |           0.53 |          0.046 |       1.8 |            84.6 |              315.1 |
| ('W', 'A')     |       113 |   67.3 |           0.43 |         -0.076 |      -8.6 |            70.8 |              158.6 |
| ('W', 'OC')    |       131 |   75.6 |           0.35 |         -0.037 |      -4.9 |            79.4 |              189.1 |
| ('W', 'V')     |       103 |   68.9 |           0.43 |         -0.108 |     -11.2 |            69.9 |              217.1 |
| ('W', 'flip')  |       833 |   73.9 |           0.41 |         -0.016 |     -13.4 |            78.3 |              151.1 |
| ('W', 'sweep') |       300 |   72   |           0.42 |         -0.035 |     -10.5 |            75.3 |              152.4 |

## By story and rule

|                           |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:--------------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'alignment')        |       286 |   79.4 |           0.53 |         -0.001 |      -0.3 |            83.9 |               91.8 |
| ('D', 'cadjpy')           |       250 |   64.4 |           1.07 |         -0.067 |     -16.9 |            70   |               43.4 |
| ('D', 'cadjpy+overlap')   |         2 |   50   |           1.68 |          0.585 |       1.2 |            50   |               61.4 |
| ('D', 'flip')             |        72 |   73.6 |           0.55 |          0.05  |       3.6 |            80.6 |               50.3 |
| ('D', 'flip+overlap')     |         3 |   66.7 |           1.4  |          0.21  |       0.6 |            66.7 |               37.4 |
| ('D', 'standard')         |      6070 |   78.7 |           0.32 |         -0.01  |     -60.8 |            81.3 |               72   |
| ('D', 'standard+overlap') |       431 |   67.3 |           0.45 |         -0.049 |     -21.3 |            68.7 |               82   |
| ('D', 'sweep_start')      |      1634 |   77.1 |           0.36 |         -0.005 |      -7.8 |            80   |               69.8 |
| ('M', 'flip')             |        12 |   41.7 |           0.87 |         -0.298 |      -3.6 |            58.3 |              254   |
| ('M', 'standard')         |       152 |   59.2 |           0.77 |         -0.056 |      -8.6 |            63.2 |              336.8 |
| ('M', 'sweep_start')      |        39 |   76.9 |           0.53 |          0.046 |       1.8 |            84.6 |              315.1 |
| ('W', 'flip')             |        18 |   77.8 |           0.61 |          0.176 |       3.2 |            83.3 |              114.8 |
| ('W', 'flip+overlap')     |         1 |    0   |           1.18 |         -1     |      -1   |             0   |              128.3 |
| ('W', 'standard')         |      1118 |   73.3 |           0.4  |         -0.032 |     -36.3 |            77.2 |              159.8 |
| ('W', 'standard+overlap') |        43 |   67.4 |           0.38 |         -0.088 |      -3.8 |            69.8 |              163   |
| ('W', 'sweep_start')      |       300 |   72   |           0.42 |         -0.035 |     -10.5 |            75.3 |              152.4 |

## By year (D story)

|   year |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|-------:|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
|   2018 |       964 |   69.2 |           0.5  |         -0.027 |     -26.3 |            72   |               71.8 |
|   2019 |      1216 |   75.8 |           0.39 |         -0.007 |      -9   |            79.5 |               59   |
|   2020 |      1195 |   78   |           0.36 |         -0.016 |     -18.9 |            79.7 |               74.4 |
|   2021 |      1042 |   80.3 |           0.28 |         -0.012 |     -12.7 |            83   |               62.3 |
|   2022 |       997 |   80.8 |           0.31 |          0.002 |       2   |            83.5 |               89.6 |
|   2023 |      1127 |   79   |           0.37 |         -0.017 |     -19.2 |            82.5 |               79.8 |
|   2024 |      1111 |   78.5 |           0.32 |         -0.021 |     -23.3 |            81.3 |               67.5 |
|   2025 |      1096 |   77   |           0.42 |          0.005 |       5.8 |            79.5 |               72.4 |

## By pair (D story)

| pair   |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:-------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| AUDCAD |       306 |   76.5 |           0.3  |         -0.045 |     -13.9 |            80.4 |               57.2 |
| AUDCHF |       290 |   70   |           0.51 |         -0.028 |      -8.2 |            73.8 |               45   |
| AUDJPY |       326 |   73.9 |           0.39 |         -0.019 |      -6.2 |            78.5 |               83.2 |
| AUDNZD |       335 |   83.9 |           0.29 |          0.029 |       9.7 |            86.9 |               45.3 |
| AUDUSD |       360 |   78.9 |           0.27 |         -0.021 |      -7.6 |            82.5 |               56   |
| CADCHF |       204 |   80.4 |           0.3  |         -0.021 |      -4.3 |            82.4 |               48.3 |
| CADJPY |       277 |   78.3 |           0.39 |          0.012 |       3.4 |            80.5 |               80.6 |
| CHFJPY |       315 |   74.3 |           0.46 |         -0.002 |      -0.6 |            79   |               80.5 |
| EURAUD |       285 |   78.6 |           0.44 |         -0.048 |     -13.8 |            80.7 |              102.6 |
| EURCAD |       263 |   80.2 |           0.32 |          0.017 |       4.4 |            82.9 |               86.6 |
| EURCHF |       346 |   73.1 |           0.46 |         -0     |      -0.2 |            74.9 |               44.4 |
| EURGBP |       359 |   79.7 |           0.25 |         -0.047 |     -16.9 |            80.5 |               42.7 |
| EURJPY |       341 |   72.4 |           0.44 |         -0.025 |      -8.4 |            76   |               91.1 |
| EURNZD |       376 |   75.8 |           0.3  |         -0.06  |     -22.7 |            79.3 |              118.8 |
| EURUSD |       318 |   79.2 |           0.39 |         -0.007 |      -2.1 |            82.7 |               69.7 |
| GBPAUD |       285 |   81.8 |           0.31 |          0.009 |       2.5 |            83.5 |              126.9 |
| GBPCAD |       249 |   81.1 |           0.31 |          0.014 |       3.5 |            82.7 |              104.7 |
| GBPCHF |       353 |   71.4 |           0.54 |         -0.021 |      -7.4 |            73.4 |               77.3 |
| GBPJPY |       235 |   70.2 |           0.59 |         -0.052 |     -12.1 |            75.3 |              128.2 |
| GBPNZD |       325 |   77.2 |           0.37 |         -0.018 |      -5.7 |            80   |              136.4 |
| GBPUSD |       355 |   81.4 |           0.27 |         -0.007 |      -2.6 |            82.8 |               94.7 |
| NZDCAD |       343 |   83.7 |           0.3  |          0.049 |      16.7 |            86.9 |               57.4 |
| NZDCHF |       293 |   76.5 |           0.46 |          0.057 |      16.6 |            78.5 |               45.8 |
| NZDJPY |       289 |   79.9 |           0.32 |          0.012 |       3.5 |            83.7 |               68   |
| NZDUSD |       324 |   77.5 |           0.3  |         -0.056 |     -18.1 |            79.9 |               54   |
| USDCAD |       350 |   79.1 |           0.31 |         -0.002 |      -0.7 |            80.3 |               71.9 |
| USDCHF |       310 |   78.4 |           0.37 |         -0.003 |      -1   |            79   |               55.8 |
| USDJPY |       336 |   74.1 |           0.4  |         -0.029 |      -9.7 |            79.2 |               80   |

## M/W conflict filter (D story)

Filter is on. Tables above score tradable stories only; here all D stories vs the ones the
filter keeps vs the ones it removes (latest confirmed M and W stories pointed opposite ways).

| view                       |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:---------------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| all D stories (filter off) |      9940 |   77.7 |           0.36 |         -0.012 |    -119.5 |            80.6 |               71.6 |
| tradable (filter on)       |      8748 |   77.4 |           0.37 |         -0.012 |    -101.6 |            80.2 |               71.2 |
| NO_TRADE: M/W conflict     |      1192 |   80.4 |           0.27 |         -0.015 |     -17.9 |            83.6 |               74   |

## By story and Next Day Rule (label)

|                   |   stories |   win% |   avg_R_target |   expectancy_R |   total_R |   kevin_target% |   median_stop_pips |
|:------------------|----------:|-------:|---------------:|---------------:|----------:|----------------:|-------------------:|
| ('D', 'next day') |      4435 |   79.9 |           0.31 |          0.009 |      40.6 |            81.4 |               86.3 |
| ('D', 'same day') |      4061 |   75.5 |           0.39 |         -0.031 |    -126.6 |            79.5 |               58.5 |
| ('M', 'next day') |       107 |   70.1 |           0.52 |          0.053 |       5.7 |            71   |              409.1 |
| ('M', 'same day') |        96 |   52.1 |           0.96 |         -0.167 |     -16   |            62.5 |              254.4 |
| ('W', 'next day') |       770 |   76.4 |           0.33 |         -0.004 |      -2.7 |            77.9 |              192.3 |
| ('W', 'same day') |       710 |   69   |           0.49 |         -0.064 |     -45.7 |            75.2 |              127.4 |

## Variants (side by side, to choose defaults)

Same pairs and years for every line. Bias variants: tradable stories, trade view (entry at the
confirmation close, stop beyond the tap wick + buffer, target), `win%` = target before stop, `avg_R` /
`total_R` = result in R. Entry variants: filled entries on the default-rule stories, TP1 and TP2.
First value of each setting = current default.

| variant                         |   trades |   win% |   avg_R |   total_R |
|:--------------------------------|---------:|-------:|--------:|----------:|
| next_day_rule=flag              |    10431 |   76.4 |  -0.015 |    -160.4 |
| flag: next-day breakouts only   |     5312 |   79.2 |   0.008 |      43.6 |
| flag: same-day breakouts only   |     4867 |   74.1 |  -0.039 |    -188.3 |
| flag: no breakout (cadjpy, n/a) |      252 |   64.3 |  -0.062 |     -15.7 |
| next_day_rule=require           |     6110 |   79.7 |  -0.005 |     -33.2 |
| cadjpy_exception=on             |    10431 |   76.4 |  -0.015 |    -160.4 |
| cadjpy_exception=off            |    10298 |   76.8 |  -0.014 |    -143.1 |
| pullback_levels=on              |    10431 |   76.4 |  -0.015 |    -160.4 |
| pullback_levels=off             |     7727 |   75.1 |  -0.021 |    -163.1 |
| entry_alignment=d_h4 (TP1)      |     1168 |   30   |  -0.218 |    -254.5 |
| entry_alignment=d_h4 (TP2)      |     1168 |   11.9 |  -0.018 |     -21.6 |
| entry_alignment=w_d_h4 (TP1)    |     1060 |   29.1 |  -0.24  |    -254.4 |
| entry_alignment=w_d_h4 (TP2)    |     1060 |   11.1 |  -0.075 |     -79.5 |
| entry_alignment=off (TP1)       |     1377 |   29.8 |  -0.219 |    -301.4 |
| entry_alignment=off (TP2)       |     1377 |   11.6 |   0.006 |       7.7 |
