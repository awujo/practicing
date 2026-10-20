# Trend entries on H4 key levels

Study 1 (research/TREND_LTF_PLAN.md): trend entries on H4 key levels, the way Kevin trades.

Owner 2026-10-20. Replaying Kevin's trades showed he trades WITH the D/W trend on H4/H2/H1 key levels with
7-19 pip stops, often after the Daily story already hit its target. Here: every H4 story (slk.story, STORIES H4 =
H4 key-level tap-reject-close + H1 body close beyond point B, same rules as the D story), whatever the Daily
story is doing.

Trade: entry at the H1 confirmation close, stop = the story stop (tap candle wick + 2 pips), walked on H1 for
MAX_DAYS (stop first when one H1 candle touches stop and target), COST_PIPS per trade. One row per story with the
path outcome for every target at once: +1R / +2R / +3R / +5R / the story target (the H4 ERL), MFE (best R
before the stop) and the lower-TF features of slk.ltf_features. Filters are columns, applied in the report:
  trend: none / D agrees / D and W agree (structure trend of the last CLOSED D / W candle at the entry)
  stop: tap wick / at least 7 pips (Kevin's smallest) / skip when wider than 25 pips (Kevin "15 to 20 pips")
  daily: D story on the same side active / D target already hit / no D story

    python -m slk.trend_study --data data/examples --out reports/trend_local      # local 8 pairs
    python -m slk.trend_study --start 2018 --end 2025 --out reports               # Actions, 28 pairs


8 pairs, 2022-01-07T02:00 .. 2026-10-20T05:00. Cost 1.2 pips. Max hold 5 days. avg R includes the cost; timeouts closed at market.

## All years

| filter                                |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |   target win% |   target avg R |
|:--------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|--------------:|---------------:|
| all H4 stories                        | 4542 |               43.1 |           0.85 |      45.6 |     -0.077 |      25.2 |     -0.083 |      15   |     -0.06  |       5.6 |     -0.066 |          61.7 |         -0.067 |
| D trend agrees                        | 3925 |               44   |           0.84 |      45.4 |     -0.078 |      24.9 |     -0.089 |      14.8 |     -0.067 |       5.6 |     -0.071 |          62.1 |         -0.063 |
| D + W trend agree                     | 2225 |               45.3 |           0.79 |      43.8 |     -0.107 |      23.7 |     -0.128 |      13.4 |     -0.119 |       4.5 |     -0.131 |          60.8 |         -0.067 |
| D + W agree, stop <= 25 pips          |  435 |               19.1 |           0.84 |      45.1 |     -0.166 |      27.6 |     -0.203 |      18.6 |     -0.203 |       8.5 |     -0.25  |          56.8 |         -0.136 |
| D + W agree, D target already hit     | 1090 |               47.3 |           0.8  |      43.8 |     -0.115 |      23.4 |     -0.144 |      12.8 |     -0.146 |       4.2 |     -0.157 |          60.6 |         -0.05  |
| D + W agree, D story same side active |  609 |               42   |           0.85 |      45   |     -0.085 |      27.3 |     -0.043 |      16.3 |     -0.022 |       5.9 |     -0.034 |          64.7 |         -0.07  |
| D + W agree, no D story / ended       |  251 |               48.5 |           0.81 |      44.2 |     -0.059 |      20.7 |     -0.147 |      11.2 |     -0.161 |       2.8 |     -0.228 |          52.2 |         -0.13  |
| against D trend                       |  617 |               38.5 |           0.89 |      47   |     -0.072 |      27.4 |     -0.045 |      16.5 |     -0.017 |       5.7 |     -0.037 |          59.6 |         -0.089 |

## Before 2025 (train)

| filter                                |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |   target win% |   target avg R |
|:--------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|--------------:|---------------:|
| all H4 stories                        | 2764 |              45.25 |          0.855 |      46.3 |     -0.063 |      26.1 |     -0.049 |      15.8 |     -0.025 |       6.2 |     -0.029 |          60.2 |         -0.069 |
| D trend agrees                        | 2380 |              46.65 |          0.86  |      46.4 |     -0.057 |      25.8 |     -0.05  |      15.5 |     -0.028 |       6.2 |     -0.031 |          60.9 |         -0.059 |
| D + W trend agree                     | 1241 |              49.5  |          0.8   |      45.2 |     -0.082 |      24.3 |     -0.101 |      13.4 |     -0.097 |       4.8 |     -0.112 |          59.1 |         -0.071 |
| D + W agree, stop <= 25 pips          |  204 |              19.1  |          0.795 |      45.6 |     -0.15  |      25.5 |     -0.246 |      17.2 |     -0.283 |       6.9 |     -0.453 |          54.4 |         -0.154 |
| D + W agree, D target already hit     |  592 |              51.9  |          0.82  |      46.3 |     -0.065 |      24.5 |     -0.099 |      14.2 |     -0.082 |       4.9 |     -0.102 |          59.6 |         -0.033 |
| D + W agree, D story same side active |  347 |              42.3  |          0.86  |      46.7 |     -0.067 |      27.4 |     -0.038 |      14.7 |     -0.037 |       6.1 |     -0.04  |          60.2 |         -0.096 |
| D + W agree, no D story / ended       |  136 |              50.4  |          0.76  |      41.9 |     -0.083 |      19.1 |     -0.185 |       8.1 |     -0.262 |       2.2 |     -0.338 |          54.4 |         -0.179 |
| against D trend                       |  384 |              37.45 |          0.84  |      45.6 |     -0.099 |      27.6 |     -0.039 |      17.7 |     -0.006 |       6   |     -0.018 |          56   |         -0.126 |

## 2025 and later (test)

| filter                                |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |   target win% |   target avg R |
|:--------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|--------------:|---------------:|
| all H4 stories                        | 1778 |               39.8 |          0.84  |      44.5 |     -0.099 |      23.9 |     -0.136 |      13.8 |     -0.115 |       4.7 |     -0.124 |          64.1 |         -0.063 |
| D trend agrees                        | 1545 |               39.8 |          0.82  |      43.8 |     -0.11  |      23.4 |     -0.148 |      13.7 |     -0.127 |       4.6 |     -0.133 |          63.8 |         -0.069 |
| D + W trend agree                     |  984 |               41.7 |          0.765 |      42   |     -0.139 |      23   |     -0.161 |      13.5 |     -0.147 |       4.3 |     -0.154 |          62.9 |         -0.062 |
| D + W agree, stop <= 25 pips          |  231 |               18.9 |          0.84  |      44.6 |     -0.18  |      29.4 |     -0.164 |      19.9 |     -0.132 |      10   |     -0.071 |          58.9 |         -0.12  |
| D + W agree, D target already hit     |  498 |               42.3 |          0.75  |      40.8 |     -0.175 |      22.1 |     -0.197 |      11.2 |     -0.223 |       3.4 |     -0.223 |          61.8 |         -0.07  |
| D + W agree, D story same side active |  262 |               41.7 |          0.82  |      42.7 |     -0.108 |      27.1 |     -0.05  |      18.3 |     -0.002 |       5.7 |     -0.026 |          70.6 |         -0.036 |
| D + W agree, no D story / ended       |  115 |               45   |          0.88  |      47   |     -0.03  |      22.6 |     -0.101 |      14.8 |     -0.041 |       3.5 |     -0.098 |          49.6 |         -0.073 |
| against D trend                       |  233 |               40.2 |          0.96  |      49.4 |     -0.027 |      27   |     -0.053 |      14.6 |     -0.033 |       5.2 |     -0.069 |          65.7 |         -0.028 |

## By year (D + W agree)

|   year |   ('R_2R', 'count') |   ('R_2R', 'mean') |   ('R_3R', 'count') |   ('R_3R', 'mean') |   ('R_target', 'count') |   ('R_target', 'mean') |
|-------:|--------------------:|-------------------:|--------------------:|-------------------:|------------------------:|-----------------------:|
|   2022 |                 382 |             -0.049 |                 382 |             -0.016 |                     382 |                 -0.046 |
|   2023 |                 465 |             -0.102 |                 465 |             -0.121 |                     465 |                 -0.054 |
|   2024 |                 394 |             -0.152 |                 394 |             -0.148 |                     394 |                 -0.114 |
|   2025 |                 607 |             -0.17  |                 607 |             -0.16  |                     607 |                 -0.065 |
|   2026 |                 377 |             -0.146 |                 377 |             -0.126 |                     377 |                 -0.058 |

# Kevin continuation levels on H4 / H2 / H1 (limit at the line, Kevin's stop)

Every Kevin continuation level (entry.patterns: A/V-shape, 3rd-candle wick rejection, impulsive internal
    break) on H4 / H2 / H1, SELL and BUY, whatever the stories say. Limit at the line once the breakout candle has
    closed, valid RETEST_BARS entry-TF candles; Kevin's stop (zone, else rejection wick, max 20 pips); one row per
    filled level with the context at the breakout close: D / W trend, last H4 / D / W structural break, D and H4
    story state. No story is required: the report filters on the context.

## H4 limit levels: all years

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 1345 |              10.3  |          0     |      39.9 |     -0.393 |      28.5 |     -0.337 |      22.7 |     -0.277 |      15.5 |     -0.218 |
| D + W trend agree                                    |  379 |              10.7  |          0     |      36.9 |     -0.456 |      26.6 |     -0.391 |      21.6 |     -0.319 |      16.1 |     -0.176 |
| against the D trend                                  |  702 |              10.2  |          0     |      39.9 |     -0.391 |      27.9 |     -0.352 |      22.2 |     -0.293 |      15.1 |     -0.249 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  543 |              10.5  |          0     |      40   |     -0.393 |      28.4 |     -0.345 |      22.1 |     -0.303 |      16.2 |     -0.179 |
| W + D + H4 last break agree                          |  321 |              10.5  |          0     |      36.8 |     -0.454 |      24.3 |     -0.455 |      19.3 |     -0.405 |      15   |     -0.255 |
| D + W trend + D/H4 in line                           |  270 |              10.3  |          0     |      37   |     -0.449 |      24.1 |     -0.462 |      18.9 |     -0.42  |      15.9 |     -0.203 |
| D + W trend + D/H4 in line, D target already hit     |  142 |              10.8  |          0     |      37.3 |     -0.427 |      26.1 |     -0.38  |      19   |     -0.386 |      14.8 |     -0.226 |
| D + W trend + D/H4 in line, D story same side active |   74 |              11.4  |          0.165 |      40.5 |     -0.401 |      23   |     -0.522 |      20.3 |     -0.401 |      18.9 |     -0.076 |
| D + W trend + D/H4 in line, no D story               |   54 |               8.75 |          0     |      31.5 |     -0.575 |      20.4 |     -0.594 |      16.7 |     -0.538 |      14.8 |     -0.316 |
| D + W trend + D/H4 in line, inside an H4 story       |  118 |               9.95 |          0     |      38.1 |     -0.432 |      24.6 |     -0.444 |      18.6 |     -0.44  |      16.9 |     -0.169 |

## H4 limit levels: before 2025 (train)

| filter                                               |   n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 801 |              10.5  |          0     |      38.6 |     -0.427 |      27.3 |     -0.377 |      22.1 |     -0.303 |      15.2 |     -0.241 |
| D + W trend agree                                    | 215 |              10.7  |          0     |      36.3 |     -0.477 |      27.4 |     -0.372 |      23.7 |     -0.236 |      17.7 |     -0.072 |
| against the D trend                                  | 421 |              10.1  |          0     |      38.7 |     -0.424 |      25.9 |     -0.422 |      20.2 |     -0.377 |      13.8 |     -0.333 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 331 |              11.2  |          0.29  |      41.7 |     -0.37  |      30.8 |     -0.275 |      26   |     -0.154 |      20.2 |      0.039 |
| W + D + H4 last break agree                          | 200 |              11.3  |          0     |      39.5 |     -0.416 |      29   |     -0.329 |      25   |     -0.188 |      20   |      0.022 |
| D + W trend + D/H4 in line                           | 162 |              11.25 |          0     |      38.3 |     -0.441 |      27.8 |     -0.364 |      24.7 |     -0.196 |      21   |      0.088 |
| D + W trend + D/H4 in line, D target already hit     |  84 |              11.65 |          0     |      36.9 |     -0.444 |      29.8 |     -0.27  |      25   |     -0.137 |      20.2 |      0.1   |
| D + W trend + D/H4 in line, D story same side active |  46 |              12.25 |          0.165 |      39.1 |     -0.435 |      23.9 |     -0.501 |      23.9 |     -0.262 |      21.7 |      0.086 |
| D + W trend + D/H4 in line, no D story               |  32 |               7.1  |          0     |      40.6 |     -0.443 |      28.1 |     -0.411 |      25   |     -0.255 |      21.9 |      0.057 |
| D + W trend + D/H4 in line, inside an H4 story       |  71 |              10.1  |          0     |      40.8 |     -0.376 |      28.2 |     -0.326 |      25.4 |     -0.164 |      22.5 |      0.174 |

## H4 limit levels: 2025 and later (test)

| filter                                               |   n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 544 |              10.15 |          0.245 |      41.7 |     -0.341 |      30.1 |     -0.279 |      23.5 |     -0.238 |      15.8 |     -0.185 |
| D + W trend agree                                    | 164 |              10.35 |          0     |      37.8 |     -0.429 |      25.6 |     -0.416 |      18.9 |     -0.429 |      14   |     -0.314 |
| against the D trend                                  | 281 |              10.5  |          0.16  |      41.6 |     -0.34  |      31   |     -0.246 |      25.3 |     -0.167 |      17.1 |     -0.123 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 212 |               9.95 |          0     |      37.3 |     -0.428 |      24.5 |     -0.454 |      16   |     -0.536 |       9.9 |     -0.519 |
| W + D + H4 last break agree                          | 121 |              10.2  |          0     |      32.2 |     -0.516 |      16.5 |     -0.664 |       9.9 |     -0.764 |       6.6 |     -0.713 |
| D + W trend + D/H4 in line                           | 108 |              10    |          0     |      35.2 |     -0.461 |      18.5 |     -0.61  |      10.2 |     -0.758 |       8.3 |     -0.639 |
| D + W trend + D/H4 in line, D target already hit     |  58 |              10.2  |          0.05  |      37.9 |     -0.402 |      20.7 |     -0.54  |      10.3 |     -0.747 |       6.9 |     -0.698 |
| D + W trend + D/H4 in line, D story same side active |  28 |               9.65 |          0.21  |      42.9 |     -0.343 |      21.4 |     -0.557 |      14.3 |     -0.629 |      14.3 |     -0.343 |
| D + W trend + D/H4 in line, no D story               |  22 |               9.7  |          0     |      18.2 |     -0.768 |       9.1 |     -0.859 |       4.5 |     -0.95  |       4.5 |     -0.859 |
| D + W trend + D/H4 in line, inside an H4 story       |  47 |               8.9  |          0     |      34   |     -0.517 |      19.1 |     -0.623 |       8.5 |     -0.857 |       8.5 |     -0.687 |

## H4 h1_confirm levels: all years

| filter                                               |   n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 715 |              17.9  |          0.93  |      48   |     -0.115 |      33.1 |     -0.059 |      22   |     -0.1   |      12.9 |     -0.046 |
| D + W trend agree                                    | 194 |              18.25 |          0.86  |      45.9 |     -0.147 |      33.5 |     -0.044 |      25.8 |      0.051 |      15.5 |      0.094 |
| against the D trend                                  | 365 |              17.9  |          0.92  |      47.4 |     -0.125 |      33.7 |     -0.039 |      21.4 |     -0.109 |      11.5 |     -0.094 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 297 |              18.3  |          0.85  |      45.8 |     -0.159 |      31.6 |     -0.108 |      21.5 |     -0.134 |      12.8 |     -0.073 |
| W + D + H4 last break agree                          | 165 |              17.8  |          0.74  |      41.2 |     -0.236 |      29.7 |     -0.161 |      22.4 |     -0.117 |      12.7 |     -0.141 |
| D + W trend + D/H4 in line                           | 138 |              18.35 |          0.765 |      40.6 |     -0.246 |      31.9 |     -0.09  |      25.4 |      0.015 |      13.8 |     -0.012 |
| D + W trend + D/H4 in line, D target already hit     |  71 |              18.5  |          0.85  |      42.3 |     -0.191 |      32.4 |     -0.073 |      25.4 |      0.016 |      12.7 |     -0.006 |
| D + W trend + D/H4 in line, D story same side active |  42 |              17.6  |          0.485 |      35.7 |     -0.365 |      33.3 |     -0.079 |      31   |      0.159 |      21.4 |      0.346 |
| D + W trend + D/H4 in line, no D story               |  25 |              19.2  |          0.47  |      44   |     -0.202 |      28   |     -0.158 |      16   |     -0.232 |       4   |     -0.632 |
| D + W trend + D/H4 in line, inside an H4 story       |  60 |              17.5  |          0.815 |      40   |     -0.26  |      31.7 |     -0.082 |      26.7 |      0.087 |      16.7 |      0.121 |

## H4 h1_confirm levels: before 2025 (train)

| filter                                               |   n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 415 |               18.5 |          0.92  |      47.5 |     -0.115 |      33   |     -0.044 |      21.4 |     -0.117 |      12.8 |     -0.055 |
| D + W trend agree                                    | 107 |               19.6 |          1.27  |      51.4 |     -0.026 |      39.3 |      0.137 |      31.8 |      0.286 |      17.8 |      0.295 |
| against the D trend                                  | 212 |               18.3 |          0.79  |      43.9 |     -0.186 |      31.1 |     -0.087 |      17.5 |     -0.234 |       9.9 |     -0.208 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 182 |               19.5 |          1.075 |      52.2 |     -0.017 |      37.4 |      0.077 |      26.9 |      0.091 |      15.9 |      0.146 |
| W + D + H4 last break agree                          | 105 |               18.9 |          1.31  |      52.4 |     -0.005 |      39   |      0.134 |      30.5 |      0.21  |      17.1 |      0.145 |
| D + W trend + D/H4 in line                           |  81 |               20.8 |          1.45  |      53.1 |      0.017 |      43.2 |      0.27  |      35.8 |      0.445 |      18.5 |      0.358 |
| D + W trend + D/H4 in line, D target already hit     |  39 |               21.4 |          1.73  |      56.4 |      0.127 |      46.2 |      0.369 |      41   |      0.625 |      20.5 |      0.592 |
| D + W trend + D/H4 in line, D story same side active |  25 |               17.6 |          0.75  |      48   |     -0.121 |      44   |      0.239 |      40   |      0.519 |      28   |      0.768 |
| D + W trend + D/H4 in line, no D story               |  17 |               21.1 |          1.45  |      52.9 |     -0.031 |      35.3 |      0.092 |      17.6 |     -0.075 |       0   |     -0.781 |
| D + W trend + D/H4 in line, inside an H4 story       |  36 |               23   |          1.155 |      50   |     -0.043 |      41.7 |      0.254 |      36.1 |      0.536 |      22.2 |      0.543 |

## H4 h1_confirm levels: 2025 and later (test)

| filter                                               |   n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 300 |              16.6  |          0.95  |      48.7 |     -0.115 |      33.3 |     -0.079 |      22.7 |     -0.077 |      13   |     -0.034 |
| D + W trend agree                                    |  87 |              17    |          0.6   |      39.1 |     -0.296 |      26.4 |     -0.267 |      18.4 |     -0.237 |      12.6 |     -0.153 |
| against the D trend                                  | 153 |              16.5  |          1.11  |      52.3 |     -0.039 |      37.3 |      0.028 |      26.8 |      0.064 |      13.7 |      0.063 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 115 |              16.7  |          0.56  |      35.7 |     -0.383 |      22.6 |     -0.402 |      13   |     -0.49  |       7.8 |     -0.419 |
| W + D + H4 last break agree                          |  60 |              17.05 |          0.365 |      21.7 |     -0.642 |      13.3 |     -0.675 |       8.3 |     -0.687 |       5   |     -0.642 |
| D + W trend + D/H4 in line                           |  57 |              17    |          0.39  |      22.8 |     -0.62  |      15.8 |     -0.602 |      10.5 |     -0.597 |       7   |     -0.538 |
| D + W trend + D/H4 in line, D target already hit     |  32 |              15.65 |          0.47  |      25   |     -0.579 |      15.6 |     -0.61  |       6.2 |     -0.726 |       3.1 |     -0.733 |
| D + W trend + D/H4 in line, D story same side active |  17 |              17    |          0.36  |      17.6 |     -0.723 |      17.6 |     -0.547 |      17.6 |     -0.37  |      11.8 |     -0.276 |
| D + W trend + D/H4 in line, no D story               |   8 |              18.85 |          0.165 |      25   |     -0.565 |      12.5 |     -0.69  |      12.5 |     -0.565 |      12.5 |     -0.315 |
| D + W trend + D/H4 in line, inside an H4 story       |  24 |              14.95 |          0.355 |      25   |     -0.586 |      16.7 |     -0.586 |      12.5 |     -0.586 |       8.3 |     -0.512 |

## H2 limit levels: all years

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 3124 |               8.5  |              0 |      37.5 |     -0.466 |      29.2 |     -0.341 |      23.3 |     -0.278 |      16.1 |     -0.239 |
| D + W trend agree                                    |  816 |               9.05 |              0 |      35.5 |     -0.488 |      27.3 |     -0.385 |      21.8 |     -0.329 |      15.3 |     -0.279 |
| against the D trend                                  | 1687 |               8.4  |              0 |      38.1 |     -0.459 |      29.5 |     -0.336 |      23.8 |     -0.267 |      16.1 |     -0.241 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 1058 |               8.7  |              0 |      37.6 |     -0.466 |      29.2 |     -0.347 |      22.8 |     -0.3   |      15.6 |     -0.267 |
| W + D + H4 last break agree                          |  593 |               8.9  |              0 |      35.2 |     -0.501 |      26   |     -0.436 |      20.7 |     -0.381 |      14.5 |     -0.33  |
| D + W trend + D/H4 in line                           |  524 |               8.9  |              0 |      37.6 |     -0.451 |      28.8 |     -0.348 |      22.9 |     -0.291 |      15.8 |     -0.247 |
| D + W trend + D/H4 in line, D target already hit     |  240 |               8.85 |              0 |      40.4 |     -0.391 |      32.9 |     -0.233 |      24.6 |     -0.226 |      15.4 |     -0.284 |
| D + W trend + D/H4 in line, D story same side active |  164 |               8.95 |              0 |      37.2 |     -0.465 |      26.2 |     -0.422 |      21.3 |     -0.355 |      17.1 |     -0.184 |
| D + W trend + D/H4 in line, no D story               |  120 |               9.2  |              0 |      32.5 |     -0.552 |      24.2 |     -0.477 |      21.7 |     -0.336 |      15   |     -0.256 |
| D + W trend + D/H4 in line, inside an H4 story       |  179 |               8.6  |              0 |      39.1 |     -0.435 |      28.5 |     -0.354 |      23.5 |     -0.27  |      15.1 |     -0.272 |

## H2 limit levels: before 2025 (train)

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 1901 |               8.7  |              0 |      36.3 |     -0.469 |      28.6 |     -0.337 |      23.3 |     -0.257 |      16.4 |     -0.207 |
| D + W trend agree                                    |  460 |               9.15 |              0 |      35.9 |     -0.487 |      27.8 |     -0.363 |      22.4 |     -0.297 |      17.4 |     -0.153 |
| against the D trend                                  | 1027 |               8.5  |              0 |      37.5 |     -0.448 |      29   |     -0.326 |      23.7 |     -0.247 |      15.9 |     -0.238 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  651 |               9.1  |              0 |      36.3 |     -0.476 |      28.4 |     -0.344 |      23   |     -0.266 |      16.4 |     -0.2   |
| W + D + H4 last break agree                          |  357 |               9.4  |              0 |      34.2 |     -0.526 |      24.9 |     -0.453 |      20.2 |     -0.386 |      14.6 |     -0.317 |
| D + W trend + D/H4 in line                           |  302 |               9.5  |              0 |      36.4 |     -0.479 |      28.1 |     -0.353 |      22.2 |     -0.301 |      16.9 |     -0.175 |
| D + W trend + D/H4 in line, D target already hit     |  147 |               9.6  |              0 |      42.2 |     -0.356 |      34.7 |     -0.138 |      25.9 |     -0.127 |      19   |     -0.018 |
| D + W trend + D/H4 in line, D story same side active |   87 |               9.6  |              0 |      32.2 |     -0.594 |      20.7 |     -0.617 |      16.1 |     -0.594 |      12.6 |     -0.479 |
| D + W trend + D/H4 in line, no D story               |   68 |               9.2  |              0 |      29.4 |     -0.598 |      23.5 |     -0.48  |      22.1 |     -0.304 |      17.6 |     -0.127 |
| D + W trend + D/H4 in line, inside an H4 story       |   97 |               8.4  |              0 |      38.1 |     -0.46  |      29.9 |     -0.31  |      25.8 |     -0.176 |      21.6 |      0.092 |

## H2 limit levels: 2025 and later (test)

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 1223 |               8.3  |              0 |      39.2 |     -0.461 |      30.2 |     -0.347 |      23.3 |     -0.312 |      15.6 |     -0.288 |
| D + W trend agree                                    |  356 |               8.85 |              0 |      35.1 |     -0.489 |      26.7 |     -0.413 |      21.1 |     -0.371 |      12.6 |     -0.441 |
| against the D trend                                  |  660 |               8.4  |              0 |      39.1 |     -0.476 |      30.3 |     -0.351 |      23.9 |     -0.298 |      16.5 |     -0.244 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  407 |               8    |              0 |      39.8 |     -0.45  |      30.5 |     -0.352 |      22.4 |     -0.353 |      14.3 |     -0.374 |
| W + D + H4 last break agree                          |  236 |               8    |              0 |      36.9 |     -0.465 |      27.5 |     -0.41  |      21.6 |     -0.372 |      14.4 |     -0.349 |
| D + W trend + D/H4 in line                           |  222 |               8.3  |              0 |      39.2 |     -0.413 |      29.7 |     -0.341 |      23.9 |     -0.278 |      14.4 |     -0.344 |
| D + W trend + D/H4 in line, D target already hit     |   93 |               7.9  |              0 |      37.6 |     -0.445 |      30.1 |     -0.383 |      22.6 |     -0.383 |       9.7 |     -0.705 |
| D + W trend + D/H4 in line, D story same side active |   77 |               8.7  |              0 |      42.9 |     -0.319 |      32.5 |     -0.202 |      27.3 |     -0.085 |      22.1 |      0.149 |
| D + W trend + D/H4 in line, no D story               |   52 |               8.7  |              0 |      36.5 |     -0.493 |      25   |     -0.474 |      21.2 |     -0.378 |      11.5 |     -0.425 |
| D + W trend + D/H4 in line, inside an H4 story       |   82 |               8.7  |              0 |      40.2 |     -0.406 |      26.8 |     -0.406 |      20.7 |     -0.381 |       7.3 |     -0.704 |

## H2 h1_confirm levels: all years

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 1611 |              16.2  |          0.91  |      48.4 |     -0.124 |      31.6 |     -0.131 |      23.9 |     -0.099 |      14.3 |     -0.082 |
| D + W trend agree                                    |  401 |              17.3  |          0.88  |      47.6 |     -0.138 |      31.2 |     -0.15  |      23.7 |     -0.128 |      14.2 |     -0.098 |
| against the D trend                                  |  876 |              16.3  |          0.935 |      48.9 |     -0.112 |      31.1 |     -0.151 |      24   |     -0.101 |      13.9 |     -0.114 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  547 |              17    |          0.91  |      48.1 |     -0.131 |      31.3 |     -0.139 |      23   |     -0.134 |      13.7 |     -0.116 |
| W + D + H4 last break agree                          |  294 |              17.3  |          0.845 |      45.9 |     -0.174 |      28.9 |     -0.218 |      22.1 |     -0.179 |      13.3 |     -0.188 |
| D + W trend + D/H4 in line                           |  261 |              17.4  |          0.97  |      49.8 |     -0.095 |      33   |     -0.098 |      24.9 |     -0.075 |      13.8 |     -0.125 |
| D + W trend + D/H4 in line, D target already hit     |  128 |              15.45 |          0.98  |      50   |     -0.104 |      32.8 |     -0.12  |      18.8 |     -0.324 |      10.9 |     -0.376 |
| D + W trend + D/H4 in line, D story same side active |   82 |              18.3  |          0.91  |      47.6 |     -0.13  |      32.9 |     -0.093 |      31.7 |      0.187 |      18.3 |      0.112 |
| D + W trend + D/H4 in line, no D story               |   51 |              20.7  |          1.08  |      52.9 |     -0.015 |      33.3 |     -0.048 |      29.4 |      0.128 |      13.7 |      0.12  |
| D + W trend + D/H4 in line, inside an H4 story       |   88 |              17.1  |          1     |      50   |     -0.062 |      30.7 |     -0.127 |      23.9 |     -0.093 |      10.2 |     -0.26  |

## H2 h1_confirm levels: before 2025 (train)

| filter                                               |   n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 969 |              16.8  |          0.87  |      46.5 |     -0.153 |      30.7 |     -0.152 |      23.9 |     -0.098 |      15.6 |     -0.02  |
| D + W trend agree                                    | 229 |              18.2  |          0.89  |      46.7 |     -0.13  |      31   |     -0.129 |      24   |     -0.082 |      14.4 |     -0.039 |
| against the D trend                                  | 531 |              16.7  |          0.88  |      47.5 |     -0.142 |      30.3 |     -0.171 |      23.5 |     -0.125 |      15.4 |     -0.07  |
| D + H4 last break agree (Kevin: D and H4 in line)    | 336 |              17    |          0.885 |      45.8 |     -0.155 |      30.1 |     -0.159 |      22.6 |     -0.131 |      13.7 |     -0.082 |
| W + D + H4 last break agree                          | 176 |              17.5  |          0.835 |      44.3 |     -0.174 |      26.1 |     -0.271 |      19.9 |     -0.224 |      11.9 |     -0.218 |
| D + W trend + D/H4 in line                           | 147 |              18.3  |          0.94  |      49   |     -0.071 |      32.7 |     -0.071 |      24.5 |     -0.045 |      12.9 |     -0.122 |
| D + W trend + D/H4 in line, D target already hit     |  79 |              17.3  |          1.17  |      50.6 |     -0.02  |      32.9 |     -0.045 |      20.3 |     -0.173 |      12.7 |     -0.169 |
| D + W trend + D/H4 in line, D story same side active |  40 |              18.3  |          0.8   |      42.5 |     -0.223 |      25   |     -0.323 |      25   |     -0.073 |      12.5 |     -0.22  |
| D + W trend + D/H4 in line, no D story               |  28 |              22.3  |          1.255 |      53.6 |      0.001 |      42.9 |      0.215 |      35.7 |      0.358 |      14.3 |      0.151 |
| D + W trend + D/H4 in line, inside an H4 story       |  48 |              16.65 |          1.015 |      50   |     -0.04  |      35.4 |      0.022 |      27.1 |      0.043 |      12.5 |     -0.068 |

## H2 h1_confirm levels: 2025 and later (test)

| filter                                               |   n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 642 |              15.4  |          1.06  |      51.1 |     -0.081 |      33   |     -0.099 |      23.8 |     -0.101 |      12.5 |     -0.176 |
| D + W trend agree                                    | 172 |              16.25 |          0.865 |      48.8 |     -0.149 |      31.4 |     -0.177 |      23.3 |     -0.189 |      14   |     -0.177 |
| against the D trend                                  | 345 |              15.7  |          1.09  |      51   |     -0.065 |      32.2 |     -0.119 |      24.6 |     -0.063 |      11.6 |     -0.181 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 211 |              16.9  |          1.06  |      51.7 |     -0.093 |      33.2 |     -0.107 |      23.7 |     -0.138 |      13.7 |     -0.171 |
| W + D + H4 last break agree                          | 118 |              17    |          0.865 |      48.3 |     -0.175 |      33.1 |     -0.139 |      25.4 |     -0.113 |      15.3 |     -0.143 |
| D + W trend + D/H4 in line                           | 114 |              16.95 |          1.05  |      50.9 |     -0.125 |      33.3 |     -0.131 |      25.4 |     -0.114 |      14.9 |     -0.13  |
| D + W trend + D/H4 in line, D target already hit     |  49 |              13.4  |          0.89  |      49   |     -0.241 |      32.7 |     -0.241 |      16.3 |     -0.567 |       8.2 |     -0.709 |
| D + W trend + D/H4 in line, D story same side active |  42 |              18.2  |          1.095 |      52.4 |     -0.041 |      40.5 |      0.126 |      38.1 |      0.436 |      23.8 |      0.429 |
| D + W trend + D/H4 in line, no D story               |  23 |              17    |          1.06  |      52.2 |     -0.035 |      21.7 |     -0.369 |      21.7 |     -0.152 |      13   |      0.083 |
| D + W trend + D/H4 in line, inside an H4 story       |  40 |              17.3  |          0.97  |      50   |     -0.089 |      25   |     -0.306 |      20   |     -0.256 |       7.5 |     -0.491 |

## H1 limit levels: all years

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 6859 |               6.6  |              0 |      34   |     -0.567 |      27.9 |     -0.41  |      22.6 |     -0.344 |      15.8 |     -0.298 |
| D + W trend agree                                    | 1811 |               7.4  |              0 |      32   |     -0.593 |      25.8 |     -0.459 |      20.4 |     -0.418 |      13.9 |     -0.401 |
| against the D trend                                  | 3713 |               6.5  |              0 |      35.3 |     -0.542 |      29.1 |     -0.374 |      23.8 |     -0.297 |      16.5 |     -0.251 |
| D + H4 last break agree (Kevin: D and H4 in line)    | 2155 |               6.7  |              0 |      32.3 |     -0.601 |      26.9 |     -0.443 |      22   |     -0.371 |      15.3 |     -0.332 |
| W + D + H4 last break agree                          | 1268 |               6.8  |              0 |      31   |     -0.625 |      25.2 |     -0.493 |      20.1 |     -0.444 |      13.9 |     -0.416 |
| D + W trend + D/H4 in line                           | 1067 |               7.1  |              0 |      30.4 |     -0.632 |      24.4 |     -0.511 |      19.5 |     -0.463 |      13.8 |     -0.416 |
| D + W trend + D/H4 in line, D target already hit     |  491 |               7.3  |              0 |      31.4 |     -0.625 |      24.4 |     -0.526 |      18.9 |     -0.502 |      13.2 |     -0.465 |
| D + W trend + D/H4 in line, D story same side active |  342 |               7.55 |              0 |      32.2 |     -0.579 |      26.9 |     -0.415 |      22.5 |     -0.322 |      15.5 |     -0.293 |
| D + W trend + D/H4 in line, no D story               |  234 |               6.2  |              0 |      25.6 |     -0.723 |      20.5 |     -0.621 |      16.2 |     -0.588 |      12.4 |     -0.494 |
| D + W trend + D/H4 in line, inside an H4 story       |  238 |               7.25 |              0 |      26.1 |     -0.697 |      21.4 |     -0.575 |      17.2 |     -0.529 |      13.9 |     -0.386 |

## H1 limit levels: before 2025 (train)

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 4328 |               7    |              0 |      32.5 |     -0.587 |      26.9 |     -0.431 |      21.6 |     -0.372 |      15.1 |     -0.33  |
| D + W trend agree                                    | 1070 |               7.8  |              0 |      30.7 |     -0.612 |      24.9 |     -0.479 |      19.6 |     -0.44  |      13.9 |     -0.39  |
| against the D trend                                  | 2347 |               6.8  |              0 |      34   |     -0.562 |      28.4 |     -0.39  |      23   |     -0.321 |      15.6 |     -0.3   |
| D + H4 last break agree (Kevin: D and H4 in line)    | 1381 |               7    |              0 |      31.6 |     -0.609 |      26.4 |     -0.451 |      21.8 |     -0.369 |      15.1 |     -0.335 |
| W + D + H4 last break agree                          |  797 |               7    |              0 |      30.6 |     -0.633 |      25.1 |     -0.494 |      20.2 |     -0.438 |      14.3 |     -0.388 |
| D + W trend + D/H4 in line                           |  630 |               7.5  |              0 |      29.4 |     -0.652 |      23.5 |     -0.535 |      18.9 |     -0.484 |      13.5 |     -0.43  |
| D + W trend + D/H4 in line, D target already hit     |  279 |               7.6  |              0 |      28.7 |     -0.696 |      22.6 |     -0.592 |      17.2 |     -0.581 |      12.2 |     -0.538 |
| D + W trend + D/H4 in line, D story same side active |  206 |               7.85 |              0 |      33.5 |     -0.538 |      27.2 |     -0.393 |      22.8 |     -0.295 |      16.5 |     -0.218 |
| D + W trend + D/H4 in line, no D story               |  145 |               6.6  |              0 |      24.8 |     -0.731 |      20   |     -0.628 |      16.6 |     -0.566 |      11.7 |     -0.524 |
| D + W trend + D/H4 in line, inside an H4 story       |  127 |               7.9  |              0 |      24.4 |     -0.725 |      22   |     -0.552 |      17.3 |     -0.52  |      15   |     -0.315 |

## H1 limit levels: 2025 and later (test)

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 2531 |               6.1  |              0 |      36.4 |     -0.535 |      29.7 |     -0.374 |      24.3 |     -0.295 |      17   |     -0.242 |
| D + W trend agree                                    |  741 |               6.9  |              0 |      33.9 |     -0.566 |      27.3 |     -0.43  |      21.6 |     -0.386 |      13.9 |     -0.419 |
| against the D trend                                  | 1366 |               6.2  |              0 |      37.6 |     -0.507 |      30.4 |     -0.347 |      25.2 |     -0.254 |      18.1 |     -0.167 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  774 |               6.15 |              0 |      33.6 |     -0.586 |      27.9 |     -0.428 |      22.4 |     -0.373 |      15.6 |     -0.327 |
| W + D + H4 last break agree                          |  471 |               6.5  |              0 |      31.6 |     -0.611 |      25.3 |     -0.493 |      20   |     -0.455 |      13.2 |     -0.463 |
| D + W trend + D/H4 in line                           |  437 |               6.8  |              0 |      31.8 |     -0.603 |      25.6 |     -0.478 |      20.4 |     -0.433 |      14.2 |     -0.396 |
| D + W trend + D/H4 in line, D target already hit     |  212 |               7.1  |              0 |      34.9 |     -0.533 |      26.9 |     -0.44  |      21.2 |     -0.398 |      14.6 |     -0.369 |
| D + W trend + D/H4 in line, D story same side active |  136 |               7    |              0 |      30.1 |     -0.641 |      26.5 |     -0.45  |      22.1 |     -0.362 |      14   |     -0.406 |
| D + W trend + D/H4 in line, no D story               |   89 |               5.2  |              0 |      27   |     -0.71  |      21.3 |     -0.609 |      15.7 |     -0.624 |      13.5 |     -0.445 |
| D + W trend + D/H4 in line, inside an H4 story       |  111 |               6.8  |              0 |      27.9 |     -0.666 |      20.7 |     -0.603 |      17.1 |     -0.54  |      12.6 |     -0.468 |

## H1 h1_confirm levels: all years

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 3224 |               13.6 |          0.94  |      48.6 |     -0.145 |      32.2 |     -0.143 |      23.9 |     -0.139 |      15   |     -0.107 |
| D + W trend agree                                    |  826 |               15.6 |          0.79  |      45.6 |     -0.193 |      29.5 |     -0.209 |      21.5 |     -0.22  |      12.8 |     -0.25  |
| against the D trend                                  | 1773 |               13.2 |          1.02  |      50.6 |     -0.106 |      33.8 |     -0.101 |      25.2 |     -0.087 |      16.1 |     -0.031 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  984 |               13.8 |          0.91  |      47.6 |     -0.167 |      31.8 |     -0.155 |      23.2 |     -0.169 |      14.7 |     -0.136 |
| W + D + H4 last break agree                          |  556 |               14.7 |          0.835 |      46.8 |     -0.181 |      30.8 |     -0.186 |      21.8 |     -0.219 |      13.3 |     -0.234 |
| D + W trend + D/H4 in line                           |  469 |               15   |          0.82  |      45.8 |     -0.192 |      31.1 |     -0.167 |      22.4 |     -0.188 |      14.3 |     -0.171 |
| D + W trend + D/H4 in line, D target already hit     |  225 |               15.7 |          0.79  |      44.4 |     -0.225 |      29.8 |     -0.211 |      21.3 |     -0.243 |      12   |     -0.31  |
| D + W trend + D/H4 in line, D story same side active |  149 |               15   |          0.97  |      49   |     -0.127 |      36.2 |     -0.02  |      24.8 |     -0.071 |      16.8 |     -0.008 |
| D + W trend + D/H4 in line, no D story               |   95 |               12.9 |          0.73  |      44.2 |     -0.217 |      26.3 |     -0.293 |      21.1 |     -0.24  |      15.8 |     -0.098 |
| D + W trend + D/H4 in line, inside an H4 story       |  104 |               15.2 |          0.61  |      42.3 |     -0.257 |      25   |     -0.334 |      18.3 |     -0.323 |      11.5 |     -0.328 |

## H1 h1_confirm levels: before 2025 (train)

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 1987 |              14.8  |          0.88  |      47   |     -0.166 |      31.1 |     -0.165 |      23   |     -0.167 |      13.8 |     -0.173 |
| D + W trend agree                                    |  482 |              17.1  |          0.725 |      42.5 |     -0.237 |      26.8 |     -0.266 |      20.1 |     -0.245 |      11.8 |     -0.288 |
| against the D trend                                  | 1093 |              13.9  |          0.99  |      49.9 |     -0.116 |      33.6 |     -0.103 |      24.7 |     -0.11  |      14.7 |     -0.122 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  630 |              15    |          0.825 |      44.8 |     -0.205 |      30   |     -0.193 |      21.9 |     -0.214 |      13.7 |     -0.198 |
| W + D + H4 last break agree                          |  353 |              15.7  |          0.79  |      44.5 |     -0.21  |      28.6 |     -0.229 |      21   |     -0.241 |      12.7 |     -0.242 |
| D + W trend + D/H4 in line                           |  280 |              16.25 |          0.73  |      42.1 |     -0.245 |      27.1 |     -0.259 |      19.6 |     -0.276 |      12.1 |     -0.291 |
| D + W trend + D/H4 in line, D target already hit     |  120 |              17.25 |          0.8   |      43.3 |     -0.217 |      25   |     -0.315 |      19.2 |     -0.298 |      10.8 |     -0.407 |
| D + W trend + D/H4 in line, D story same side active |   94 |              16.55 |          0.855 |      45.7 |     -0.174 |      31.9 |     -0.132 |      22.3 |     -0.162 |      14.9 |     -0.085 |
| D + W trend + D/H4 in line, no D story               |   66 |              14.65 |          0.43  |      34.8 |     -0.397 |      24.2 |     -0.336 |      16.7 |     -0.397 |      10.6 |     -0.375 |
| D + W trend + D/H4 in line, inside an H4 story       |   55 |              15.2  |          0.6   |      41.8 |     -0.255 |      23.6 |     -0.346 |      16.4 |     -0.344 |      10.9 |     -0.281 |

## H1 h1_confirm levels: 2025 and later (test)

| filter                                               |    n |   median stop pips |   MFE median R |   1R win% |   1R avg R |   2R win% |   2R avg R |   3R win% |   3R avg R |   5R win% |   5R avg R |
|:-----------------------------------------------------|-----:|-------------------:|---------------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|----------:|-----------:|
| all levels                                           | 1237 |              12    |          1.04  |      51.3 |     -0.11  |      34   |     -0.109 |      25.3 |     -0.095 |      16.8 |     -0.002 |
| D + W trend agree                                    |  344 |              13.85 |          0.985 |      50   |     -0.131 |      33.4 |     -0.129 |      23.5 |     -0.186 |      14.2 |     -0.198 |
| against the D trend                                  |  680 |              12.2  |          1.065 |      51.9 |     -0.09  |      34.3 |     -0.097 |      25.9 |     -0.05  |      18.2 |      0.115 |
| D + H4 last break agree (Kevin: D and H4 in line)    |  354 |              11.85 |          1.105 |      52.5 |     -0.099 |      35   |     -0.086 |      25.4 |     -0.088 |      16.7 |     -0.028 |
| W + D + H4 last break agree                          |  203 |              12.5  |          1.04  |      50.7 |     -0.13  |      34.5 |     -0.112 |      23.2 |     -0.18  |      14.3 |     -0.221 |
| D + W trend + D/H4 in line                           |  189 |              12.9  |          1.05  |      51.3 |     -0.114 |      37   |     -0.031 |      26.5 |     -0.057 |      17.5 |      0.006 |
| D + W trend + D/H4 in line, D target already hit     |  105 |              13.8  |          0.75  |      45.7 |     -0.235 |      35.2 |     -0.092 |      23.8 |     -0.18  |      13.3 |     -0.2   |
| D + W trend + D/H4 in line, D story same side active |   55 |              12.6  |          1.37  |      54.5 |     -0.047 |      43.6 |      0.171 |      29.1 |      0.087 |      20   |      0.123 |
| D + W trend + D/H4 in line, no D story               |   29 |              12.1  |          1.34  |      65.5 |      0.194 |      31   |     -0.193 |      31   |      0.118 |      27.6 |      0.531 |
| D + W trend + D/H4 in line, inside an H4 story       |   49 |              15    |          0.75  |      42.9 |     -0.26  |      26.5 |     -0.321 |      20.4 |     -0.3   |      12.2 |     -0.382 |
