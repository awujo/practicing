# Primary source material

`bishops_trade_chart_examples.pdf` -- the 60-page Web3Bish0p / Defi Bishop
chart-example deck, committed 2026-09-02.

**Why it is in the repo rather than referenced.** It had been supplied only
in chat, and every analysis built on it (`bishop_pdf_sl_measurements.md`,
`bishop_chart_examples_pages7-60.md`, and the stop-placement arguments
throughout `bot/OPERATIONS_LOG.md`) was therefore unverifiable once the
conversation ended -- measurements had to be trusted rather than checked.
That went wrong in practice: a stop-anchor recommendation was made on
backtest results alone and only afterwards found to contradict the pip
distances measured from these pages. Anyone can now re-open page 6 and
check the numbers themselves.

11MB of binary in git history is a real cost, accepted deliberately: this
is the only primary source the strategy rests on, it does not change, and
losing it costs far more than storing it.
