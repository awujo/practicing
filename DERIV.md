# Deriv public market-data scanning

The same hourly pipeline now supports selected Deriv public API markets alongside IC Markets.
Settings → Markets → Pairs lists human names prefixed `Deriv`. No market is automatically added to anyone's
watchlist. New users retain their three starter FX pairs. Scan downloads use the union of selected keys once.

Internal keys use `DV` plus a normalized original API symbol, for example DV1HZ100V for Volatility100(1s)
and DVR100 for Volatility100. The catalogue retains the exact original API symbol for requests. Separate
files carry source=deriv and pip/precision metadata. Deriv errors never invoke cTrader or Dukascopy fallback.
Public candles and symbol discovery need no account token. This is the public Options API feed; it is not an
MT5 account connection. Deriv signals cannot be approved for orders through the IC Markets account.

Deriv H1 is resampled into UTC H2/H4/day/month and Monday-to-Monday seven-day weeks. Only completed
candles are used for bias, confirmation, reconciliation and paper tracking. FX keeps its existing17:00 New York
clock. Continuous synthetic/crypto markets keep scanning over weekends; selected noncontinuous Deriv markets
follow the FX weekend pause. Market/session availability still depends on the provider.

The observed public endpoint has a1000-candle response cap and about one year of historical retention.
Requests use at most30days (720 H1 bars), UTC-aligned starts and exclusive end boundaries. Live warmup is
bounded to366days; actual returned history can be shorter for newer instruments. Data outside the requested
window and inception partial-hour candles are discarded, never relabelled. Continuous-series gaps and missing
latest closed hours cause a source error and skip the scan. No claim of1200days or full historical coverage.

Price decimals follow the advertised quote increment. Existing FX, metal and stock-index strategy pip units
are preserved; synthetic/crypto pip units use the public feed's quote increment. Settings such as stop buffers
remain in those units; the original FX studies do not evaluate Deriv markets.

Checks: `python -m slk.deriv --probe --pair DV1HZ100V --days 366` runs download and full D/W/M bias+entry
computation without a database or Telegram messages. `--catalogue` refreshes data/deriv_symbols.json.
Deriv public feed checks workflow repeats this validation on GitHub; multiuser checks cover source isolation,
clocks, weekend selection, stale data, quotes and disabled order approval. The live workflow installs
websocket-client and continues to use the shared candle cache with distinct DV filenames.
