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


Trades: 105442, 28 pairs, years 2018-2025; train < 2023 <= test. Outcome: R_3R (cost included).

## Best fixed target

| tf   | entry      | part   |     n |   R_1R |   R_2R |   R_3R |   R_5R |
|:-----|:-----------|:-------|------:|-------:|-------:|-------:|-------:|
| H1   | h1_confirm | train  | 12754 | -0.158 | -0.134 | -0.124 | -0.12  |
| H1   | h1_confirm | test   |  7471 | -0.164 | -0.156 | -0.163 | -0.155 |
| H1   | limit      | train  | 26996 | -0.576 | -0.429 | -0.36  | -0.285 |
| H1   | limit      | test   | 15705 | -0.572 | -0.426 | -0.359 | -0.305 |
| H2   | h1_confirm | train  |  6426 | -0.131 | -0.146 | -0.146 | -0.137 |
| H2   | h1_confirm | test   |  3676 | -0.108 | -0.107 | -0.099 | -0.121 |
| H2   | limit      | train  | 12147 | -0.432 | -0.329 | -0.28  | -0.248 |
| H2   | limit      | test   |  6810 | -0.424 | -0.291 | -0.235 | -0.215 |
| H4   | h1_confirm | train  |  3126 | -0.105 | -0.083 | -0.111 | -0.154 |
| H4   | h1_confirm | test   |  1792 | -0.133 | -0.121 | -0.095 | -0.077 |
| H4   | limit      | train  |  5444 | -0.353 | -0.256 | -0.24  | -0.228 |
| H4   | limit      | test   |  3095 | -0.351 | -0.285 | -0.214 | -0.177 |

## Single conditions: held on TEST (1 of 18 train candidates, 448 tested)

| tf   | entry      | rule   |   train n |   train avg R |   train base |   test n |   test avg R |   test base |
|:-----|:-----------|:-------|----------:|--------------:|-------------:|---------:|-------------:|------------:|
| H1   | h1_confirm | dow=6  |       226 |         0.067 |       -0.124 |      152 |        0.371 |      -0.163 |

## Single conditions: all TRAIN candidates (top 40 by train avg R)

| tf   | entry      | rule                |   train n |   train avg R |   train base |   test n |   test avg R |   test base | holds   |
|:-----|:-----------|:--------------------|----------:|--------------:|-------------:|---------:|-------------:|------------:|:--------|
| H1   | h1_confirm | dow=6               |       226 |         0.067 |       -0.124 |      152 |        0.371 |      -0.163 | True    |
| H4   | h1_confirm | atr_pips>15.5333    |      1042 |        -0.003 |       -0.111 |      617 |       -0.039 |      -0.095 | False   |
| H2   | limit      | session=late        |      1752 |        -0.022 |       -0.28  |     1205 |       -0.058 |      -0.235 | False   |
| H4   | limit      | session=late        |       900 |        -0.05  |       -0.24  |      597 |       -0.039 |      -0.214 | False   |
| H1   | limit      | session=late        |      3574 |        -0.078 |       -0.36  |     2674 |       -0.172 |      -0.359 | False   |
| H4   | limit      | 0.9<run_R<=0.94     |      1911 |        -0.08  |       -0.24  |     1077 |       -0.108 |      -0.214 | False   |
| H2   | limit      | stop_pips>10.3      |      4047 |        -0.09  |       -0.28  |     2482 |       -0.025 |      -0.235 | False   |
| H4   | limit      | 8.1<stop_pips<=12.7 |      1799 |        -0.095 |       -0.24  |      942 |       -0.049 |      -0.214 | False   |
| H4   | limit      | stop_pips>12.7      |      1808 |        -0.124 |       -0.24  |     1108 |       -0.105 |      -0.214 | False   |
| H4   | limit      | 0.6<stop_atr<=0.98  |      1822 |        -0.125 |       -0.24  |      924 |       -0.116 |      -0.214 | False   |
| H4   | limit      | stop_atr>0.98       |      1785 |        -0.129 |       -0.24  |     1126 |       -0.083 |      -0.214 | False   |
| H2   | limit      | stop_atr>0.78       |      4026 |        -0.14  |       -0.28  |     2522 |       -0.067 |      -0.235 | False   |
| H1   | limit      | stop_pips>7.8       |      8828 |        -0.151 |       -0.36  |     5339 |       -0.127 |      -0.359 | False   |
| H1   | limit      | stop_atr>0.59       |      8863 |        -0.169 |       -0.36  |     5481 |       -0.168 |      -0.359 | False   |
| H2   | limit      | 0.49<stop_atr<=0.78 |      4061 |        -0.178 |       -0.28  |     2228 |       -0.1   |      -0.235 | False   |
| H1   | limit      | h4_story=none       |       121 |        -0.185 |       -0.36  |        0 |      nan     |      -0.359 | False   |
| H1   | limit      | run_R>0.88          |      8549 |        -0.239 |       -0.36  |     5357 |       -0.193 |      -0.359 | False   |
| H1   | limit      | 0.79<run_R<=0.88    |      9242 |        -0.247 |       -0.36  |     4822 |       -0.249 |      -0.359 | False   |

## Two conditions (AND): held on TEST (11 of 26 train candidates, 27 tested)

| tf   | entry   | rule                                   |   train n |   train avg R |   train base |   test n |   test avg R |   test base |
|:-----|:--------|:---------------------------------------|----------:|--------------:|-------------:|---------:|-------------:|------------:|
| H1   | limit   | session=late AND stop_pips>7.8         |      1436 |        -0.021 |        -0.36 |      933 |        0.176 |      -0.359 |
| H1   | limit   | session=late AND stop_atr>0.59         |      1107 |         0.06  |        -0.36 |      902 |        0.063 |      -0.359 |
| H1   | limit   | session=late AND run_R>0.88            |      1376 |        -0.121 |        -0.36 |      937 |        0.069 |      -0.359 |
| H2   | limit   | session=late AND stop_pips>10.3        |       625 |         0.076 |        -0.28 |      422 |        0.219 |      -0.235 |
| H2   | limit   | session=late AND 0.49<stop_atr<=0.78   |       557 |         0.104 |        -0.28 |      411 |        0.016 |      -0.235 |
| H2   | limit   | session=late AND stop_atr>0.78         |       490 |         0.077 |        -0.28 |      408 |        0.219 |      -0.235 |
| H2   | limit   | stop_pips>10.3 AND 0.49<stop_atr<=0.78 |      1231 |        -0.095 |        -0.28 |      738 |        0.054 |      -0.235 |
| H4   | limit   | session=late AND 8.1<stop_pips<=12.7   |       308 |        -0.016 |        -0.24 |      191 |        0.091 |      -0.214 |
| H4   | limit   | session=late AND stop_pips>12.7        |       316 |         0.147 |        -0.24 |      199 |        0.041 |      -0.214 |
| H4   | limit   | session=late AND 0.6<stop_atr<=0.98    |       328 |         0.113 |        -0.24 |      183 |        0.107 |      -0.214 |
| H4   | limit   | session=late AND stop_atr>0.98         |       237 |         0.1   |        -0.24 |      200 |        0.026 |      -0.214 |

## Two conditions (AND): all TRAIN candidates (top 40 by train avg R)

| tf   | entry   | rule                                       |   train n |   train avg R |   train base |   test n |   test avg R |   test base | holds   |
|:-----|:--------|:-------------------------------------------|----------:|--------------:|-------------:|---------:|-------------:|------------:|:--------|
| H4   | limit   | session=late AND 0.9<run_R<=0.94           |       323 |         0.202 |        -0.24 |      203 |       -0.011 |      -0.214 | False   |
| H4   | limit   | session=late AND stop_pips>12.7            |       316 |         0.147 |        -0.24 |      199 |        0.041 |      -0.214 | True    |
| H4   | limit   | session=late AND 0.6<stop_atr<=0.98        |       328 |         0.113 |        -0.24 |      183 |        0.107 |      -0.214 | True    |
| H2   | limit   | session=late AND 0.49<stop_atr<=0.78       |       557 |         0.104 |        -0.28 |      411 |        0.016 |      -0.235 | True    |
| H4   | limit   | session=late AND stop_atr>0.98             |       237 |         0.1   |        -0.24 |      200 |        0.026 |      -0.214 | True    |
| H2   | limit   | session=late AND stop_atr>0.78             |       490 |         0.077 |        -0.28 |      408 |        0.219 |      -0.235 | True    |
| H2   | limit   | session=late AND stop_pips>10.3            |       625 |         0.076 |        -0.28 |      422 |        0.219 |      -0.235 | True    |
| H1   | limit   | session=late AND 0.79<run_R<=0.88          |      1265 |         0.074 |        -0.36 |      836 |       -0.093 |      -0.359 | False   |
| H1   | limit   | session=late AND stop_atr>0.59             |      1107 |         0.06  |        -0.36 |      902 |        0.063 |      -0.359 | True    |
| H4   | limit   | session=late AND 8.1<stop_pips<=12.7       |       308 |        -0.016 |        -0.24 |      191 |        0.091 |      -0.214 | True    |
| H1   | limit   | session=late AND stop_pips>7.8             |      1436 |        -0.021 |        -0.36 |      933 |        0.176 |      -0.359 | True    |
| H4   | limit   | 8.1<stop_pips<=12.7 AND 0.9<run_R<=0.94    |       680 |        -0.037 |        -0.24 |      360 |       -0.103 |      -0.214 | False   |
| H4   | limit   | 8.1<stop_pips<=12.7 AND stop_atr>0.98      |       620 |        -0.047 |        -0.24 |      394 |       -0.013 |      -0.214 | False   |
| H4   | limit   | stop_pips>12.7 AND 0.6<stop_atr<=0.98      |       561 |        -0.057 |        -0.24 |      344 |       -0.022 |      -0.214 | False   |
| H2   | limit   | stop_pips>10.3 AND stop_atr>0.78           |      2438 |        -0.068 |        -0.28 |     1532 |       -0.035 |      -0.235 | False   |
| H2   | limit   | stop_pips>10.3 AND 0.49<stop_atr<=0.78     |      1231 |        -0.095 |        -0.28 |      738 |        0.054 |      -0.235 | True    |
| H4   | limit   | 0.6<stop_atr<=0.98 AND 0.9<run_R<=0.94     |       625 |        -0.1   |        -0.24 |      293 |       -0.074 |      -0.214 | False   |
| H4   | limit   | stop_pips>12.7 AND 0.9<run_R<=0.94         |      1225 |        -0.108 |        -0.24 |      717 |       -0.111 |      -0.214 | False   |
| H1   | limit   | stop_atr>0.59 AND run_R>0.88               |      4756 |        -0.111 |        -0.36 |     2955 |       -0.093 |      -0.359 | False   |
| H1   | limit   | stop_pips>7.8 AND stop_atr>0.59            |      5384 |        -0.113 |        -0.36 |     3243 |       -0.106 |      -0.359 | False   |
| H4   | limit   | stop_atr>0.98 AND 0.9<run_R<=0.94          |      1105 |        -0.113 |        -0.24 |      675 |       -0.148 |      -0.214 | False   |
| H4   | limit   | 8.1<stop_pips<=12.7 AND 0.6<stop_atr<=0.98 |       774 |        -0.118 |        -0.24 |      305 |       -0.2   |      -0.214 | False   |
| H1   | limit   | session=late AND run_R>0.88                |      1376 |        -0.121 |        -0.36 |      937 |        0.069 |      -0.359 | True    |
| H1   | limit   | stop_pips>7.8 AND run_R>0.88               |      7476 |        -0.143 |        -0.36 |     4632 |       -0.111 |      -0.359 | False   |
| H1   | limit   | stop_pips>7.8 AND 0.79<run_R<=0.88         |      1352 |        -0.194 |        -0.36 |      707 |       -0.232 |      -0.359 | False   |
| H1   | limit   | stop_atr>0.59 AND 0.79<run_R<=0.88         |      3433 |        -0.205 |        -0.36 |     1932 |       -0.228 |      -0.359 | False   |
