"""Default FX scan universe (operational choice, not a teaching rule).

All 28 crosses of the eight major currencies; --pairs can select other assets.
This module deliberately has no engine, database or broker imports.
"""
PAIRS = tuple((
    "EURUSD GBPUSD AUDUSD NZDUSD USDJPY USDCAD USDCHF EURGBP EURJPY EURAUD EURCAD EURCHF EURNZD "
    "GBPJPY GBPAUD GBPCAD GBPCHF GBPNZD AUDJPY AUDCAD AUDCHF AUDNZD NZDJPY NZDCAD NZDCHF CADJPY "
    "CADCHF CHFJPY"
).split())
