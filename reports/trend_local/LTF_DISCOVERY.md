# Lower-TF discovery

Study 3 (research/TREND_LTF_PLAN.md): which lower-TF condition at the entry makes a trade more likely to work?

Input: pattern_trades.csv.gz of slk.trend_study (one row per Kevin continuation level and entry kind, with the
slk.ltf_features columns, all measured from candles closed at the entry). Method, fixed BEFORE looking at results:
  1. Split by year: TRAIN = years < split, TEST = years >= split. Everything is chosen on TRAIN only.
  2. Every feature is cut into buckets: booleans / categories as they are, numbers into 3 equal-count buckets
     (tertile cut points from TRAIN).
  3. A bucket is a CANDIDATE when on TRAIN it has >= MIN_N trades and its avg R beats the TRAIN baseline of the
     same entry TF / entry kind by >= MIN_LIFT R, for the outcome column (default R_3R: fixed 3R target).
  4. Candidates are then shown on TEST once. A rule "holds" when TEST n >= MIN_N_TEST, TEST avg R beats the TEST
     baseline by >= MIN_LIFT / 2 and TEST avg R > 0 after costs.
  5. Pairs of two candidates (AND) are tried the same way (train-chosen, test-checked).
Many buckets are tested, so some TRAIN winners are luck: only TEST decides, and even a TEST pass on 8 pairs is a
lead for the full 28-pair run, not a rule. No ANN. Nothing here changes the live bot.

    python -m slk.ltf_discovery --trades reports/pattern_trades.csv.gz --split 2023 --out reports


Trades: 16878, 8 pairs, years 2022-2026; train < 2025 <= test. Outcome: R_3R (cost included).

## Best fixed target

| tf   | entry      | part   |    n |   R_1R |   R_2R |   R_3R |   R_5R |
|:-----|:-----------|:-------|-----:|-------:|-------:|-------:|-------:|
| H1   | h1_confirm | train  | 1987 | -0.166 | -0.165 | -0.167 | -0.173 |
| H1   | h1_confirm | test   | 1237 | -0.11  | -0.109 | -0.095 | -0.002 |
| H1   | limit      | train  | 4328 | -0.587 | -0.431 | -0.372 | -0.33  |
| H1   | limit      | test   | 2531 | -0.535 | -0.374 | -0.295 | -0.242 |
| H2   | h1_confirm | train  |  969 | -0.153 | -0.152 | -0.098 | -0.02  |
| H2   | h1_confirm | test   |  642 | -0.081 | -0.099 | -0.101 | -0.176 |
| H2   | limit      | train  | 1901 | -0.469 | -0.337 | -0.257 | -0.207 |
| H2   | limit      | test   | 1223 | -0.461 | -0.347 | -0.312 | -0.288 |
| H4   | h1_confirm | train  |  415 | -0.115 | -0.044 | -0.117 | -0.055 |
| H4   | h1_confirm | test   |  300 | -0.115 | -0.079 | -0.077 | -0.034 |
| H4   | limit      | train  |  801 | -0.427 | -0.377 | -0.303 | -0.241 |
| H4   | limit      | test   |  544 | -0.341 | -0.279 | -0.238 | -0.185 |

## Single conditions: held on TEST (5 of 49 train candidates, 446 tested)

| tf   | entry      | rule                           |   train n |   train avg R |   train base |   test n |   test avg R |   test base |
|:-----|:-----------|:-------------------------------|----------:|--------------:|-------------:|---------:|-------------:|------------:|
| H2   | h1_confirm | session=late                   |       164 |         0.03  |       -0.098 |      146 |        0.185 |      -0.101 |
| H2   | h1_confirm | break_body_atr>0.86            |       322 |         0.031 |       -0.098 |      206 |        0.066 |      -0.101 |
| H2   | h1_confirm | 15<hours_tap_to_entry<=23.3333 |       299 |         0.012 |       -0.098 |      208 |        0.015 |      -0.101 |
| H4   | h1_confirm | break_body_atr>0.8             |       136 |         0.042 |       -0.117 |      109 |        0.018 |      -0.077 |
| H4   | h1_confirm | bo_body_x_avg>2.43             |       138 |        -0.003 |       -0.117 |       92 |        0.162 |      -0.077 |

## Single conditions: all TRAIN candidates (top 40 by train avg R)

| tf   | entry      | rule                           |   train n |   train avg R |   train base |   test n |   test avg R |   test base | holds   |
|:-----|:-----------|:-------------------------------|----------:|--------------:|-------------:|---------:|-------------:|------------:|:--------|
| H4   | h1_confirm | run_R>0.97                     |       118 |         0.168 |       -0.117 |       77 |       -0.259 |      -0.077 | False   |
| H4   | h1_confirm | w_trend_agrees=yes             |       175 |         0.088 |       -0.117 |      132 |       -0.213 |      -0.077 | False   |
| H4   | h1_confirm | h4_story=same                  |       104 |         0.052 |       -0.117 |       77 |       -0.485 |      -0.077 | False   |
| H2   | h1_confirm | stop_pips>21.2                 |       320 |         0.049 |       -0.098 |      179 |       -0.048 |      -0.101 | False   |
| H4   | h1_confirm | break_body_atr>0.8             |       136 |         0.042 |       -0.117 |      109 |        0.018 |      -0.077 | True    |
| H2   | h1_confirm | atr_pips>19                    |       322 |         0.041 |       -0.098 |      173 |       -0.036 |      -0.101 | False   |
| H4   | h1_confirm | d_break_agrees=yes             |       225 |         0.039 |       -0.117 |      158 |       -0.337 |      -0.077 | False   |
| H4   | h1_confirm | prev_day_pos<=0.36             |       141 |         0.033 |       -0.117 |       85 |       -0.196 |      -0.077 | False   |
| H2   | h1_confirm | break_body_atr>0.86            |       322 |         0.031 |       -0.098 |      206 |        0.066 |      -0.101 | True    |
| H2   | h1_confirm | session=late                   |       164 |         0.03  |       -0.098 |      146 |        0.185 |      -0.101 | True    |
| H2   | h1_confirm | 4<bo_candle<=6                 |       318 |         0.028 |       -0.098 |      217 |       -0.225 |      -0.101 | False   |
| H4   | h1_confirm | stop_atr>1.6                   |       136 |         0.027 |       -0.117 |       94 |       -0.043 |      -0.077 | False   |
| H4   | h1_confirm | session=london                 |       119 |         0.025 |       -0.117 |       63 |       -0.239 |      -0.077 | False   |
| H4   | h1_confirm | session=ny                     |       135 |         0.02  |       -0.117 |      112 |       -0.132 |      -0.077 | False   |
| H2   | h1_confirm | daily=same                     |       119 |         0.019 |       -0.098 |       92 |       -0.088 |      -0.101 | False   |
| H4   | h1_confirm | w_break_agrees=yes             |       205 |         0.012 |       -0.117 |      142 |       -0.191 |      -0.077 | False   |
| H2   | h1_confirm | 15<hours_tap_to_entry<=23.3333 |       299 |         0.012 |       -0.098 |      208 |        0.015 |      -0.101 | True    |
| H4   | h1_confirm | atr_pips>19.5                  |       137 |         0.007 |       -0.117 |       88 |       -0.346 |      -0.077 | False   |
| H4   | h1_confirm | d_trend_agrees=yes             |       203 |         0.005 |       -0.117 |      147 |       -0.224 |      -0.077 | False   |
| H2   | h1_confirm | bo_body_x_avg<=1.56            |       324 |         0.004 |       -0.098 |      200 |       -0.165 |      -0.101 | False   |
| H4   | h1_confirm | bo_body_x_avg>2.43             |       138 |        -0.003 |       -0.117 |       92 |        0.162 |      -0.077 | True    |
| H1   | h1_confirm | dow=0                          |       349 |        -0.009 |       -0.167 |      178 |       -0.1   |      -0.095 | False   |
| H2   | limit      | stop_pips>11.4                 |       627 |        -0.014 |       -0.257 |      375 |       -0.11  |      -0.312 | False   |
| H4   | h1_confirm | stop_pips>22.9                 |       138 |        -0.015 |       -0.117 |       72 |       -0.214 |      -0.077 | False   |
| H4   | h1_confirm | daily=same_target_hit          |       106 |        -0.016 |       -0.117 |       72 |       -0.039 |      -0.077 | False   |
| H1   | h1_confirm | run_R>0.95                     |       612 |        -0.026 |       -0.167 |      305 |       -0.002 |      -0.095 | False   |
| H2   | limit      | session=late                   |       212 |        -0.027 |       -0.257 |      215 |       -0.05  |      -0.312 | False   |
| H2   | limit      | 0.47<stop_atr<=0.76            |       637 |        -0.032 |       -0.257 |      431 |       -0.222 |      -0.312 | False   |
| H1   | h1_confirm | h4_story=same                  |       238 |        -0.062 |       -0.167 |      164 |       -0.18  |      -0.095 | False   |
| H4   | limit      | session=late                   |       112 |        -0.092 |       -0.303 |      108 |       -0.091 |      -0.238 | False   |
| H2   | limit      | 0.87<run_R<=0.93               |       681 |        -0.1   |       -0.257 |      433 |       -0.152 |      -0.312 | False   |
| H2   | limit      | session=asia                   |       369 |        -0.113 |       -0.257 |      223 |       -0.208 |      -0.312 | False   |
| H4   | limit      | 8<stop_pips<=13.4333           |       263 |        -0.12  |       -0.303 |      189 |       -0.112 |      -0.238 | False   |
| H2   | limit      | 4<bo_candle<=6                 |       620 |        -0.123 |       -0.257 |      409 |       -0.322 |      -0.312 | False   |
| H4   | limit      | bo_candle>5                    |       244 |        -0.129 |       -0.303 |      204 |       -0.206 |      -0.238 | False   |
| H2   | limit      | 13<hours_tap_to_entry<=22      |       665 |        -0.131 |       -0.257 |      466 |       -0.214 |      -0.312 | False   |
| H2   | limit      | break_body_atr<=0.36           |       639 |        -0.132 |       -0.257 |      410 |       -0.369 |      -0.312 | False   |
| H2   | limit      | 3<hours_to_fill<=9             |       622 |        -0.137 |       -0.257 |      422 |       -0.293 |      -0.312 | False   |
| H4   | limit      | session=london                 |       197 |        -0.139 |       -0.303 |      124 |       -0.322 |      -0.238 | False   |
| H4   | limit      | break_body_atr<=0.35           |       269 |        -0.14  |       -0.303 |      182 |       -0.232 |      -0.238 | False   |

## Two conditions (AND): held on TEST (10 of 60 train candidates, 62 tested)

| tf   | entry      | rule                                              |   train n |   train avg R |   train base |   test n |   test avg R |   test base |
|:-----|:-----------|:--------------------------------------------------|----------:|--------------:|-------------:|---------:|-------------:|------------:|
| H1   | limit      | session=late AND stop_pips>9.4                    |       189 |        -0.096 |       -0.372 |      113 |        0.118 |      -0.295 |
| H1   | limit      | session=late AND stop_atr>0.58                    |       135 |         0.101 |       -0.372 |      131 |        0.076 |      -0.295 |
| H1   | limit      | dow=0 AND 0.81<run_R<=0.9                         |       245 |        -0.087 |       -0.372 |      125 |        0.096 |      -0.295 |
| H2   | h1_confirm | stop_pips>21.2 AND atr_pips>19                    |       178 |         0.143 |       -0.098 |       95 |        0.167 |      -0.101 |
| H2   | h1_confirm | stop_pips>21.2 AND 15<hours_tap_to_entry<=23.3333 |       106 |         0.13  |       -0.098 |       58 |        0.15  |      -0.101 |
| H2   | h1_confirm | atr_pips>19 AND 15<hours_tap_to_entry<=23.3333    |       101 |         0.049 |       -0.098 |       58 |        0.31  |      -0.101 |
| H2   | limit      | session=asia AND stop_pips>11.4                   |       155 |         0.207 |       -0.257 |       93 |        0.111 |      -0.312 |
| H2   | limit      | session=asia AND 13<hours_tap_to_entry<=22        |       112 |         0.109 |       -0.257 |       73 |        0.145 |      -0.312 |
| H2   | limit      | session=late AND break_body_atr<=0.36             |       106 |        -0.111 |       -0.257 |      120 |        0.074 |      -0.312 |
| H2   | limit      | stop_pips>11.4 AND 3<hours_to_fill<=9             |       216 |         0.056 |       -0.257 |      134 |        0.046 |      -0.312 |

## Two conditions (AND): all TRAIN candidates (top 40 by train avg R)

| tf   | entry      | rule                                              |   train n |   train avg R |   train base |   test n |   test avg R |   test base | holds   |
|:-----|:-----------|:--------------------------------------------------|----------:|--------------:|-------------:|---------:|-------------:|------------:|:--------|
| H2   | limit      | session=asia AND 0.47<stop_atr<=0.76              |       121 |         0.325 |       -0.257 |       83 |       -0.124 |      -0.312 | False   |
| H2   | limit      | session=asia AND 4<bo_candle<=6                   |       114 |         0.289 |       -0.257 |       78 |       -0.092 |      -0.312 | False   |
| H4   | h1_confirm | d_trend_agrees=yes AND w_trend_agrees=yes         |       107 |         0.286 |       -0.117 |       87 |       -0.237 |      -0.077 | False   |
| H4   | h1_confirm | w_trend_agrees=yes AND d_break_agrees=yes         |       117 |         0.264 |       -0.117 |       89 |       -0.301 |      -0.077 | False   |
| H2   | h1_confirm | atr_pips>19 AND break_body_atr>0.86               |       103 |         0.257 |       -0.098 |       41 |        0.183 |      -0.101 | False   |
| H2   | h1_confirm | stop_pips>21.2 AND bo_body_x_avg<=1.56            |       108 |         0.256 |       -0.098 |       56 |       -0.131 |      -0.101 | False   |
| H2   | limit      | stop_pips>11.4 AND 0.47<stop_atr<=0.76            |       243 |         0.235 |       -0.257 |      131 |       -0.048 |      -0.312 | False   |
| H2   | h1_confirm | atr_pips>19 AND 4<bo_candle<=6                    |       117 |         0.22  |       -0.098 |       59 |       -0.201 |      -0.101 | False   |
| H2   | limit      | session=asia AND stop_pips>11.4                   |       155 |         0.207 |       -0.257 |       93 |        0.111 |      -0.312 | True    |
| H4   | h1_confirm | d_trend_agrees=yes AND w_break_agrees=yes         |       116 |         0.186 |       -0.117 |       91 |       -0.274 |      -0.077 | False   |
| H2   | h1_confirm | bo_body_x_avg<=1.56 AND 4<bo_candle<=6            |       109 |         0.179 |       -0.098 |       71 |       -0.426 |      -0.101 | False   |
| H2   | h1_confirm | 15<hours_tap_to_entry<=23.3333 AND 4<bo_candle<=6 |       119 |         0.164 |       -0.098 |       97 |       -0.121 |      -0.101 | False   |
| H2   | limit      | 0.47<stop_atr<=0.76 AND 13<hours_tap_to_entry<=22 |       218 |         0.164 |       -0.257 |      169 |       -0.247 |      -0.312 | False   |
| H2   | limit      | stop_pips>11.4 AND break_body_atr<=0.36           |       213 |         0.159 |       -0.257 |      126 |       -0.253 |      -0.312 | False   |
| H2   | limit      | stop_pips>11.4 AND 13<hours_tap_to_entry<=22      |       214 |         0.158 |       -0.257 |      143 |       -0.058 |      -0.312 | False   |
| H2   | limit      | 0.87<run_R<=0.93 AND 4<bo_candle<=6               |       225 |         0.153 |       -0.257 |      138 |       -0.201 |      -0.312 | False   |
| H2   | limit      | 0.47<stop_atr<=0.76 AND 4<bo_candle<=6            |       212 |         0.15  |       -0.257 |      149 |       -0.192 |      -0.312 | False   |
| H2   | h1_confirm | stop_pips>21.2 AND atr_pips>19                    |       178 |         0.143 |       -0.098 |       95 |        0.167 |      -0.101 | True    |
| H2   | limit      | 0.47<stop_atr<=0.76 AND break_body_atr<=0.36      |       226 |         0.136 |       -0.257 |      142 |       -0.257 |      -0.312 | False   |
| H4   | h1_confirm | d_break_agrees=yes AND w_break_agrees=yes         |       130 |         0.135 |       -0.117 |       92 |       -0.37  |      -0.077 | False   |
| H2   | h1_confirm | stop_pips>21.2 AND 15<hours_tap_to_entry<=23.3333 |       106 |         0.13  |       -0.098 |       58 |        0.15  |      -0.101 | True    |
| H2   | limit      | stop_pips>11.4 AND 4<bo_candle<=6                 |       201 |         0.12  |       -0.257 |      124 |       -0.156 |      -0.312 | False   |
| H2   | h1_confirm | stop_pips>21.2 AND 4<bo_candle<=6                 |       112 |         0.115 |       -0.098 |       57 |       -0.128 |      -0.101 | False   |
| H2   | limit      | session=asia AND 13<hours_tap_to_entry<=22        |       112 |         0.109 |       -0.257 |       73 |        0.145 |      -0.312 | True    |
| H4   | limit      | d_break_agrees=yes AND 8<stop_pips<=13.4333       |       146 |         0.107 |       -0.303 |      102 |       -0.189 |      -0.238 | False   |
| H1   | limit      | session=late AND stop_atr>0.58                    |       135 |         0.101 |       -0.372 |      131 |        0.076 |      -0.295 | True    |
| H4   | limit      | d_break_agrees=yes AND break_close_pos>0.38       |       153 |         0.088 |       -0.303 |       92 |       -0.129 |      -0.238 | False   |
| H4   | h1_confirm | w_trend_agrees=yes AND w_break_agrees=yes         |       154 |         0.085 |       -0.117 |      122 |       -0.239 |      -0.077 | False   |
| H1   | limit      | session=late AND 0.81<run_R<=0.9                  |       162 |         0.083 |       -0.372 |      170 |       -0.101 |      -0.295 | False   |
| H2   | limit      | 0.87<run_R<=0.93 AND 13<hours_tap_to_entry<=22    |       248 |         0.071 |       -0.257 |      156 |       -0.107 |      -0.312 | False   |
| H4   | h1_confirm | d_trend_agrees=yes AND d_break_agrees=yes         |       192 |         0.066 |       -0.117 |      135 |       -0.294 |      -0.077 | False   |
| H2   | limit      | stop_pips>11.4 AND 3<hours_to_fill<=9             |       216 |         0.056 |       -0.257 |      134 |        0.046 |      -0.312 | True    |
| H2   | limit      | break_body_atr<=0.36 AND 0.87<run_R<=0.93         |       226 |         0.056 |       -0.257 |      143 |       -0.286 |      -0.312 | False   |
| H2   | limit      | stop_pips>11.4 AND 0.87<run_R<=0.93               |       286 |         0.049 |       -0.257 |      195 |       -0.081 |      -0.312 | False   |
| H2   | h1_confirm | atr_pips>19 AND 15<hours_tap_to_entry<=23.3333    |       101 |         0.049 |       -0.098 |       58 |        0.31  |      -0.101 | True    |
| H2   | limit      | session=asia AND 0.87<run_R<=0.93                 |       142 |         0.048 |       -0.257 |       89 |       -0.083 |      -0.312 | False   |
| H2   | limit      | 0.47<stop_atr<=0.76 AND 3<hours_to_fill<=9        |       202 |         0.046 |       -0.257 |      157 |       -0.427 |      -0.312 | False   |
| H2   | limit      | break_body_atr<=0.36 AND 4<bo_candle<=6           |       211 |         0.027 |       -0.257 |      131 |       -0.493 |      -0.312 | False   |
| H2   | h1_confirm | break_body_atr>0.86 AND bo_body_x_avg<=1.56       |       107 |         0.003 |       -0.098 |       58 |       -0.09  |      -0.101 | False   |
| H2   | limit      | 4<bo_candle<=6 AND 3<hours_to_fill<=9             |       207 |        -0.004 |       -0.257 |      143 |       -0.435 |      -0.312 | False   |
