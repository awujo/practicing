# Backtest

Two parts: a data pipeline (fetches and caches historical OHLCV candles)
and an engine (implements STRATEGY.md's ruleset against that data). See
`../knowledge-base/STRATEGY.md` for the ruleset itself.

Live execution is out of scope here -- it'll eventually run separately
against MT5 (the actual trading platform), once the ruleset extracted
here has been validated on historical data.

## Data source: Dukascopy, and why it changed from Oanda

Oanda was the original plan (it's the broker referenced throughout the
source material), but it rejects new clients -- including demo accounts
-- from Nigeria. Separately, and more fundamentally: **this pipeline
cannot run inside a Claude Code cloud session at all**, regardless of
vendor. Tested directly -- Oanda, Dukascopy, Twelve Data, and Binance
were all identically rejected by this session's own network egress
policy (403 policy denial at the proxy level, confirmed via
`$HTTPS_PROXY/__agentproxy/status`). That's an infrastructure restriction
on this specific execution environment, unrelated to which data vendor
gets picked. **Run this pipeline somewhere with normal outbound internet
access** -- your own machine works, but see "Running via GitHub Actions"
below for the recommended way to do this without depending on any local
machine (or its power supply) staying on.

Given that constraint, Dukascopy is the right choice anyway: **no
account, no KYC, no API key at all** -- so there's no signup step to hit
a geo-block on, from Nigeria or anywhere else. It also covers forex,
metals, oil, indices, AND crypto (ETH/USD) from one source, via the
`dukascopy-python` package, which handles the tick-data download and
decoding internally.

The Oanda code (`oanda_client.py`, `fetch_oanda.py`) is left in place,
unused, in case a future entity (a prop firm's own jurisdiction, for
instance) makes it usable later. The ccxt/Binance crypto fetcher
(`fetch_crypto.py`) is similarly kept as a fallback if Dukascopy's crypto
history turns out too short for a given backtest window.

## Running via GitHub Actions (recommended -- no local machine needed)

`.github/workflows/fetch-data.yml` runs the entire data pipeline on
GitHub's own servers -- unaffected by local power/internet reliability.
On a daily schedule (and any time via the "Run workflow" button on the
repo's Actions tab), it:

1. Downloads the previous data cache from the `data-latest` GitHub
   Release (if one exists) so the fetch is genuinely incremental instead
   of re-pulling full history every run -- Actions runners have no
   persistent disk between runs otherwise.
2. Runs `fetch_dukascopy.py --all` and `derive_granularities.py --all`.
3. Re-packages `backtest/data/` and publishes it back to the
   `data-latest` release, replacing the previous asset.

To get the data locally (e.g. to inspect it, or to feed a backtest
running somewhere else): download `backtest-data.tar.gz` from the
repo's `data-latest` release and extract it into `backtest/`.

GitHub can silently pause scheduled workflows on low-activity repos --
if a daily run seems to have been skipped, trigger it manually from the
Actions tab; that always works regardless of the cron schedule's state.

`.github/workflows/run-backtest.yml` runs the Phase 5 engine the same
way -- on demand, entirely on GitHub's servers. Trigger it from the
Actions tab with an `instrument` and `style` (aggressive/conservative)
input; it downloads the latest `data-latest` cache, restores any
previously published results, runs `backtest.engine.runner`, regenerates
the results dashboard (`backtest/engine/report.py`), and publishes it to
GitHub Pages -- so there's a standing webpage with win rate, average R,
and a cumulative-R equity curve per instrument/style run, updated
automatically after every run. **Requires `fetch-data.yml` to have
published data at least once first** -- if you run `run-backtest.yml`
before that, it now fails fast with a clear `::error::` message telling
you to run "Fetch backtest data" first, instead of the opaque "release
not found" error it used to show. Each run also still uploads the raw
trade-log CSV as a workflow artifact, for anyone who wants the underlying
data rather than just the summary.

**One-time manual step required**: GitHub Pages has to be enabled once
per repo -- go to **Settings -> Pages -> Source**, select **"Deploy from
a branch"**, branch **`gh-pages`** (folder `/ (root)`), and save. The
`gh-pages` branch itself doesn't exist yet -- it gets created
automatically the first time `run-backtest.yml` runs, so run the
workflow once first, then come back and set the Pages source to
`gh-pages` once it exists. After that, the dashboard is live at
`https://<owner>.github.io/<repo>/` and updates itself on every
subsequent run -- no further manual steps.

## Trade chart viewer (Render, not GitHub Pages)

The `index.html` dashboard above is good for aggregate stats, but it
doesn't show what a trade actually looked like on a chart -- no way to
eyeball whether the stop/target/key-level were placed somewhere sane
without hand-computing candle positions from the CSV. `backtest/webapp/`
is a small on-demand viewer for exactly that: click a trade, see Daily/
H4/H1 candlestick charts (same inline-SVG, no-CDN approach as the
dashboard's equity curve) with the entry, stop, target, and key level
drawn as horizontal lines, and the entry/exit candles marked.

Two things make this different from just adding pages to the GitHub
Pages site:
- **It reads live from GitHub on every request** -- the candle cache from
  the `data-latest` release, and whichever trade-log CSVs
  `run-backtest.yml` has most recently published to `gh-pages`. It isn't
  tied to any one backtest run; point it at the repo once and it reflects
  every future run (any instrument, any style) automatically, no
  redeploy needed.
- **Charts render on click, not ahead of time.** With 300+ trades in a
  single result set, pre-generating a chart page per trade would be slow
  to build and wasteful for the trades nobody ever looks at. A trade's
  chart is only rendered when its `/trade/<name>/<id>` page is requested.

It's meant to run on [Render](https://render.com), not GitHub Pages,
specifically so the repo can stay **private** -- Render pulls the repo's
data server-side with a GitHub token, instead of GitHub Pages needing the
whole repo to go public just to be viewable. The viewer itself also sits
behind HTTP Basic Auth (`WEBAPP_USERNAME`/`WEBAPP_PASSWORD`) since it's
showing the strategy's actual entries/stops/targets.

**One-time setup on Render:**
1. Create a Render account if you don't have one, connect it to GitHub,
   and grant it access to the `awujo/trading` repo (Render's GitHub App
   supports private repos).
2. On the Render dashboard: **New +** -> **Blueprint**, pick this repo.
   Render reads `render.yaml` at the repo root and creates the
   `slk-backtest-viewer` web service automatically.
3. Before (or right after) the first deploy, set these secret env vars on
   the service (Render dashboard -> the service -> **Environment**):
   - `GITHUB_TOKEN` -- a GitHub personal access token (fine-grained,
     scoped to `awujo/trading`) so the service can read the private
     repo's `data-latest` release and `gh-pages` results, AND (since the
     "Run a new backtest" feature below was added) trigger new
     `run-backtest.yml` runs. Needs both **Contents: read-only** and
     **Actions: read and write** -- a token created before that feature
     existed, with Contents-only, will 403/404 on the "Run a new
     backtest" page specifically (viewing existing results still works
     fine) until its permissions are widened or it's regenerated.
   - `WEBAPP_USERNAME` / `WEBAPP_PASSWORD` -- whatever you want to log in
     with. Leaving these unset does NOT lock you out, but it also means
     the viewer isn't password-protected -- set them before sharing the
     URL with anyone.
4. Deploy. The service comes up at a `*.onrender.com` URL Render assigns
   -- open it, log in, and click through to `/results/<instrument>_<style>`
   for any published run, then any trade row for its chart.

No further steps after that: every future `run-backtest.yml` run
publishes new results to `gh-pages`, and the viewer picks them up on its
own (results are re-fetched at most once a minute; each instrument's
candle cache at most once an hour -- see
`DATA_REFRESH_SECONDS`/`RESULTS_REFRESH_SECONDS` in
`backtest/webapp/data_access.py` if you want to tune that).

**Using Render's free plan:** `render.yaml` is set to `plan: free`, and
the candle-fetch path was deliberately built around this -- the full
`backtest-data.tar.gz` (all instruments, all granularities, decades of
history) is 260MB+ compressed, which would blow well past the free
tier's ~512MB RAM on every cold start and likely time out before it even
finished downloading. `fetch-data.yml` instead publishes a small
per-instrument archive (`EURUSD.tar.gz`, etc.) alongside the full one,
and `backtest/webapp/data_access.py` only ever downloads the ONE
instrument's archive for whatever trade you're actually viewing, cached
per instrument thereafter. That keeps a cold-start chart load down to a
few MB, not 260MB.

Two free-tier tradeoffs worth knowing about even with that fix:
- Free web services spin down after 15 minutes idle, and the container
  (and its `/tmp` disk) is gone when they do -- so the first click after
  any idle period re-downloads that one instrument's small archive.
  Expect a few extra seconds on the first chart after a while away, not
  a redeploy or any action from you.
- If you click through several *different* instruments in one session,
  each one's archive gets downloaded once (and cached for
  `DATA_REFRESH_SECONDS`) -- still small per instrument, just not free
  the very first time you look at a new one.

If it turns out too slow or flaky on free, the only change needed to
move to a paid plan is `plan: starter` (or higher) in `render.yaml` --
nothing else about the app changes.

Run it locally instead with:
```
GITHUB_TOKEN=... WEBAPP_USERNAME=... WEBAPP_PASSWORD=... \
  python -m backtest.webapp.app
```

**Run a new backtest from the viewer.** `/run` is a small form
(instrument, style, optional year, optional R:R) that triggers a fresh
`run-backtest.yml` run and takes you to a status page that auto-refreshes
until it's done, then links straight to `/results/<name>` for that run --
same page every other result already renders on. Deliberately does NOT
run `run_backtest()` on the Render server itself: free tier's tight
request timeout and single worker are the wrong shape for a ~60-90s
full-history run blocking every other visitor. Instead it calls GitHub's
workflow_dispatch API (`data_access.run_backtest_dispatch()`) to kick off
the exact same workflow this whole project already uses, which runs on
GitHub's own infrastructure with no timeout/RAM pressure, then polls
`data_access.find_dispatched_run()`/`get_workflow_run()` for that run's
status (GitHub's dispatch API returns no run ID, a real API limitation --
finding "the run I just started" means listing recent runs and matching
by trigger timestamp, with a small clock-skew buffer). Pending-run state
(which token maps to which triggered run) lives in an in-memory dict, not
a database -- fine for a single-worker, single-operator tool, but it
means a run triggered right as the free-tier dyno spins down/restarts
would need to be re-found via the GitHub Actions tab directly rather than
the status page. Covered by `backtest/webapp/tests/test_data_access.py`
(the dispatch payload, matching-run lookup, run-status passthrough, all
against mocked `requests` calls -- no real network) and `test_app.py`
(the form, input validation, and all three status-page states: queued,
in-progress, done/failed).

## Setup (running the pipeline manually instead)

```bash
cd backtest/data_pipeline
pip install -r requirements.txt
```

No credentials needed -- Dukascopy requires none.

## Fetching data

Run these from the **repo root** (the folder containing `backtest/`,
`bot/`, `knowledge-base/`), not from inside `backtest/data_pipeline` --
`python -m` needs the `backtest` package to be importable from your
current directory:

```bash
# everything: all instruments, all granularities
python -m backtest.data_pipeline.fetch_dukascopy --all

# one instrument, all granularities
python -m backtest.data_pipeline.fetch_dukascopy --instrument EURUSD

# one instrument, one granularity
python -m backtest.data_pipeline.fetch_dukascopy --instrument XAUUSD --granularity H4
```

Incremental by default -- re-running only pulls candles newer than what's
already cached, so a daily cron-style re-run is cheap. See
`instruments.py` for the full supported instrument list and how to add
more.

**Validated**: a full `--all` run (all 26 instruments, all 8 native
granularities) has completed successfully end to end, including the
less-common CFD codes (`E_Light` for oil, `E_D&J-Ind`/`E_NQ-100`/
`E_N225Jap` for indices) and crypto (ETHUSD -- 313,743 M5 candles alone).
`derive_granularities --all` (H2/H3/M45) has also run successfully
against the resulting cache. The full pipeline is confirmed working.

**On first run, M30/M15/M5 default to 3 years of history instead of full
history** (the higher timeframes default to Dukascopy's full available
history, back to 2003). Minute-level data for 26 instruments across
decades would be slow to pull and produce unnecessarily huge cache files
-- 3 years is already plenty of confirmation-entry setups for a
meaningful backtest sample. Delete a cached CSV and re-run if you want
more history for a specific symbol/granularity later.

## Storage format

`backtest/data/{source}/{symbol}/{granularity}.csv`, columns
`time,open,high,low,close,volume`, UTC timestamps, one row per *closed*
candle only (the still-forming current candle is never cached). Not
committed to git -- it's regenerable from the fetchers, and would balloon
the repo size across dozens of instrument/granularity pairs.

## Deriving H2 / H3 / M45

Dukascopy has no native 2H, 3H, or 45-minute granularity -- only 1H and
4H between M30 and Daily. The Bishop PDF review found all three used as
confirmation timeframes by traders in the community, so `resample.py`
derives them locally from the cached H1 (-> H2, H3) and M15 (-> M45)
data via pandas resampling. No network call -- run it after
`fetch_dukascopy.py` has populated H1/M15 for the instrument(s) you need:

```bash
python -m backtest.data_pipeline.derive_granularities --all
python -m backtest.data_pipeline.derive_granularities --instrument EURUSD --granularity H2
```

Writes into the same cache format (`backtest/data/dukascopy/{symbol}/H2.csv`
etc.), so `backtest/engine/` doesn't need to know or care whether a
granularity was fetched directly or derived.

One assumption worth knowing about: bins are anchored to UTC midnight
(H2 = 00:00-02:00, 02:00-04:00, ...; M45 tiles exactly since 1440/45=32).
STRATEGY.md doesn't specify what anchor MT5/TradingView actually use for
these non-standard intervals, so if backtest results on H2/H3/M45 ever
look off from what you see live in MT5, a differently-anchored broker
candle is the first thing to check -- consistent with the "candle closes
can differ slightly between feeds" caveat already in STRATEGY.md
Section 2. Covered by `backtest/data_pipeline/tests/test_resample.py`
(OHLCV aggregation correctness, exact M45 tiling, and that gaps produce
no candle rather than a synthetic flat one).

## Engine

`backtest/engine/` implements STRATEGY.md's rules against cached candles,
built in phases so each is testable before the next depends on it:

- [x] **Phase 1 -- structure & liquidity primitives** (`structure.py`,
      `liquidity.py`, `candles.py`): the CRITICAL wick-sweep-vs-body-close-
      break rule (Section 4), the sweep+break state machine that produces
      strong high/low, SCF single-candle IRL/ERL tagging generalized to
      multi-candle structural liquidity (Section 3), and the sequential
      per-category liquidity target flip (daily/weekly/monthly/Asian).
      Covered by `engine/tests/` (synthetic candle sequences, run with
      `python -m pytest backtest/engine/tests/`).
- [x] **Phase 2 -- key-level detection & ranking** (`key_levels.py`,
      `imbalance.py`, `ranking.py`): A-shape/V-shape (close-price peaks/
      troughs, per Section 5's "marked on closes, not wicks" resolution)
      and open-close continuation levels; the universal disrespect/flip
      rule (reuses Phase 1's body-close CRITICAL rule); QMR test-counting
      (2+ prior tests before disrespect, Video 17); and a 4-factor scored
      ranking system (imbalance overlap, recency, QMR test count,
      imbalance-fill size) with CALLER-SUPPLIED weights rather than a
      hardcoded combination formula -- see the module docstring in
      `ranking.py` for why. Also resolves the one real definitional gap
      in STRATEGY.md: "imbalance"/FVG is never precisely defined anywhere
      in the source material, so `imbalance.py` uses the standard ICT
      3-candle gap definition as a stated assumption.
- [x] **Phase 3 -- bias cascade & bias-flip state machine** (`bias.py`):
      the 3-condition flip test (Video 16, completed by Video 17) -- a
      higher-timeframe bias only flips when price trades into the next
      key level on its origin timeframe, rejects and closes the new
      direction, AND the next lower timeframe also stops confirming the
      old direction; if the lower timeframe still confirms the old
      direction, the bias stays put (Video 16's resolved ambiguity).
      Enforces Video 17's completion directly in the type system: only
      `Confirmation` objects (breakout or sweep+break, from
      `detect_confirmations()`) can satisfy condition (c) -- open-close
      breaks and engulfing (Phase 2's disrespect logic) are a different
      type and structurally can't be passed in as flip evidence, so the
      "never validates a bias flip" rule can't be accidentally violated
      by a future caller. Also implements the confirmed strict priority
      hierarchy (Weekly > Daily > 4H > lower timeframes) and Video 16's
      breakout-vs-sweep+break acceptance (both count as valid
      confirmation; `detect_confirmations()` merges them without
      double-tagging a single event as both).
- [x] **Phase 4 -- entry triggers & trade management** (`entries.py`,
      `trade_management.py`): engulfing-candle detection; Video 14's 3
      execution-facing entry patterns (direct mitigation, fresh-IRL-
      required, nested disrespect -- a restatement of Video 13's
      4-branch decision tree); Video 12's IRL-necessity rule (required
      for origin trades, optional for continuation); four distinct
      mechanized stop-loss rules (Video 13, plus a user-supplied
      "plug and play" chart cross-check): a continuation trade whose key
      level overlaps an imbalance gets a stop just past the FAR edge of
      that specific imbalance + padding (`imbalance_stop_loss()` --
      takes priority whenever it applies, since this is what "plug and
      play" actually is); a continuation trade with no overlapping
      imbalance falls back to a fixed ~10 pips; a continuation trade with
      no IRL formed gets a tighter stop just past the engulfed candle's
      own extreme; an origin trade's stop goes beyond the structural
      extreme + padding (this last rule still has the staleness issue
      described below -- deliberately left out of scope when the
      imbalance rule was added). The Aggressive/Conservative entry-style
      split (Section 5,
      "both sanctioned -- build/test both"); trade stacking via
      `PositionManager` (Video 14 -- multiple concurrent same-direction
      positions, deliberately not restricted to origin-only or
      continuation-only since that's an open question per Section 9);
      the 1:3 primary risk-reward target; Video 16's tiered exit-target
      rule (a storyline concludes at another key level on its OWN origin
      timeframe, not the lower-timeframe entry-trigger level); and
      Bishop's conservative-target cap for countertrend trades taken off
      a swept breakout-candle extreme.
- [x] **Phase 5 -- full backtest runner** (`runner.py`, `trade_log.py`):
      wires Phases 1-4 together into one real MVP chain -- Weekly
      (optional bias origin, outranks everything below it) -> Daily (bias
      origin when Weekly data isn't cached yet) -> H4 (lower-timeframe
      flip evidence) -> H1 (entry trigger and trade management), the
      concrete instantiation of Section 2's "Daily beats 4H... scale down
      further for entries" routine, now extended one level up. Weekly
      runs its own full `BiasCascade`, gated by Daily confirmations for
      the flip test exactly the way H4 confirmations gate Daily's --
      falls back cleanly to the plain Daily->H4->H1 chain if the "W"
      granularity hasn't been fetched for an instrument yet, so it's
      backward compatible with data caches from before this was added.
      Bias is bootstrapped from the first confirmed structure on each
      timeframe, replayed forward through `bias.replay_bias()` (new in
      this phase -- a backtest driver built on top of the already-tested
      `BiasCascade`, not a reimplementation of it). Entries only fire
      through the **Bishop liquidity-cascade gate** (see below) -- once a
      candle clears that gate, it's classified via Phase 4's 3-pattern
      logic, with stop/target rules selected by trade kind and IRL
      presence exactly as Phase 4 defines them.
      MAE/MFE and R-multiples are computed by walking forward candle by
      candle to whichever of stop/target is touched first. Run via
      `python -m backtest.engine.runner --instrument EURUSD --style
      conservative` (from the repo root) or the `run-backtest.yml`
      GitHub Actions workflow -- both write a `TradeRecord` CSV plus a
      console summary (win rate, total/average R).
      `trade_log.py`'s `TradeRecord` schema logs far more than win/loss
      per trade -- full multi-timeframe bias context, all 4 of Phase 2's
      ranking factors, which entry pattern and stop-loss rule fired, and
      MAE/MFE in R-multiples -- specifically so the resulting dataset
      doubles as ML training data later, not just a backtest report.
      Validated end-to-end against a synthetic multi-timeframe scenario
      (`engine/tests/test_runner.py`) covering both entry styles, since
      this session has no way to run it against real cached data itself
      (see "Data source" above) -- **the first real run against actual
      Dukascopy history is still the true first test of this chain**,
      same caveat as the data pipeline had at first.

      **Performance**: a full-history H1 run (EURUSD's uncapped H1 cache
      is well over 100,000 candles) can legitimately take up to a couple
      minutes -- that's expected, not a hang. Two things keep it there
      rather than effectively hanging: `_last_direction_at()` uses a
      pre-sorted bisect lookup instead of rescanning the whole
      confirmation list per candle, and `MAX_TRADE_DURATION_CANDLES`
      (500 H1 bars, ~3 weeks) caps how far `_resolve_trade_outcome()`
      searches forward before giving up on an unresolved trade --
      without that cap, a trade opened early in a multi-year series
      could scan every remaining candle to the end of history if its
      target was never hit again, and with many trades opening over that
      history the cost multiplies badly. The cap is a performance fix
      but also a more faithful one: Section 8 states this is a
      day-trading approach that "does not swing trades overnight as a
      rule," so a trade genuinely unresolved after ~3 weeks of H1 bars
      isn't realistic to model as still open anyway. Stress-tested
      against a synthetic 180,000-candle H1 series (deliberately
      pathological -- random-walk data fires far more engulfing signals
      than real price action does) at ~13,700 trades in 86 seconds; real
      data should run faster than that worst case.

      **Bug found and fixed via that same synthetic stress-testing
      approach**: a real EURUSD run showed a mathematically impossible
      combination -- a 1.6% win rate alongside a strongly positive total R.
      Root cause: an "origin" trade's stop-loss is placed beyond a
      Daily-timeframe "structural extreme" snapshot (`origin_stop_loss()`),
      but `trade_kind == "origin"` is decided purely by TIME proximity to
      the bias-flip breakpoint (`ORIGIN_WINDOW`), with no check that price
      is still PRICE-close to that structural extreme by the time an entry
      actually fires. When it isn't, the computed stop can land on the
      WRONG side of entry (e.g. above entry for a bullish trade) -- hitting
      it is then a favorable move, so the trade logs as `closed_loss` while
      carrying a positive `r_multiple`, corrupting both the win-rate and
      total-R numbers independently of each other. Fixed with a
      `_stop_on_correct_side()` invariant check right after stop-loss
      placement -- any trade whose computed stop isn't on the protective
      side of entry is skipped rather than opened. Confirmed via a 20,000
      H1-candle synthetic run: before the fix, 237 of 1433 closed trades
      (16.5%) carried this exact corruption (all landing at a suspicious,
      uniform +1.0R rather than genuine losses); after the fix, every
      closed trade's `r_multiple` is cleanly either -1.0 (stop) or +3.0
      (target), matching the primary 1:3 target exactly, with win rate and
      total R back in mathematical agreement. Covered by
      `test_stop_on_correct_side_rejects_inverted_bullish_stop` in
      `engine/tests/test_runner.py`.

      **Rebuild: the Bishop liquidity-cascade entry gate.** The stop-fix
      above was a real bug, but a 1.6% win rate on a live EURUSD run
      pointed at something bigger: the ORIGINAL entry logic fired on ANY
      H1 engulfing candle aligned with the effective bias, with zero
      check that a real setup had actually formed first -- none of the
      selectivity the Bishop supplementary material
      (`knowledge-base/supplementary/b_*.md`, all 6 videos plus the PDF
      chart examples, cross-validated independently of the main mentor
      course) describes. That material documents a specific mechanical
      sequence: 4H breakout (in the bias direction) -> a single-candle
      liquidity point forms on the retracement side -> price sweeps it ->
      price reacts off the NEAREST same-direction H4 key level -> THAT
      reaction (an engulf, in this build) is the entry trigger. The
      runner now enforces this as a precomputed gate that runs before the
      per-trade loop, in two steps:
      - `_find_liquidity_setups()`: for every confirmed H4 breakout, finds
        the first single-candle liquidity point (`liquidity.py`'s
        `structural_liquidity_points()`, n=1 -- Bishop's primary/simplest
        case) that forms afterward on the retracement side, and the
        nearest same-direction H4 key level for price to react from.
      - `_find_entry_candidates()`: for each setup, a bounded forward scan
        (`LIQUIDITY_SWEEP_LOOKAHEAD` H1 candles) for the sweep, then a
        further bounded scan (`REACTION_LOOKAHEAD`) for an engulfing
        candle that also touches the reaction level -- the confirmed
        entry trigger.
      Everything downstream (Video 14's 3 patterns, the 4 stop-loss
      rules, the 1:3 target, MAE/MFE) is unchanged -- only WHICH candles
      get evaluated, and WHICH key level they're evaluated against (the
      Bishop-validated H4 level, not an ad-hoc H1-engulf-derived one),
      changed. Effect on the 180,000-candle synthetic stress benchmark:
      268 trades in 40.7s, down from ~13,700 trades in 86s under the old
      ungated logic -- both faster (far fewer candidates to resolve
      outcomes for) and, more importantly, actually selective the way the
      real strategy is meant to be. Covered by
      `test_find_liquidity_setups_finds_breakout_then_liquidity_then_reaction_level`,
      `test_find_liquidity_setups_yields_nothing_without_a_breakout`, and
      the direct regression test
      `test_run_backtest_rejects_a_bias_aligned_engulf_with_no_underlying_cascade`
      (the exact old fixture that used to produce a trade under the
      ungated logic now correctly produces zero).

      **Explicitly NOT yet built in this gate** (see `runner.py`'s module
      docstring for the full list): a 2H fallback for the liquidity point
      (Bishop notes it sometimes forms there instead of 4H); breakout and
      sweep+break as alternative confirmation-entry triggers (only
      engulfing is wired in -- Bishop's material describes 3 valid
      types); Bishop's imbalance-fill-priority override and "elbow
      structure" caution (both documented in the knowledge base, neither
      wired into `_find_liquidity_setups()` yet); and "plug and play"'s
      remaining two rules (its stop-loss mechanic is now implemented --
      see below): a daily-confirmation fallback when Daily doesn't
      independently confirm but has repeatedly tested the same weekly
      level, and a named compound entry signature ("conservation sector")
      with a "resting liquidity nearby" component `ranking.py` doesn't
      currently weight.

      **Root cause found for a pile of unresolved trades, and the "plug
      and play" stop-loss fix.** A live run flagged something odd: 94 of
      123 trades (76%) never resolved within `MAX_TRADE_DURATION_CANDLES`
      (~3 weeks of H1 bars) and logged `still_open` -- overwhelmingly
      `trade_kind == "origin"` trades. Investigation (re-checking every
      stop-loss figure stated across all 18 core videos plus the Bishop
      supplementary material) found that NONE of them ever describes a
      stop wider than 10-15 pips -- Video 11's "10-15 pips on daily-
      timeframe entries" is the single widest figure anywhere. `origin`
      trades aren't an exception to that: Videos 4/12 describe the origin
      entry as taken "right where order flow was confirmed" -- i.e.
      essentially AT the strong high/low itself -- so "stop beyond the
      strong high/low + room to breathe" (Video 13) and "~10-15 pips" are
      describing the SAME stop, not two different scales. The bug: 
      `trade_kind == "origin"` is decided purely by TIME proximity to the
      daily bias flip (`ORIGIN_WINDOW`, 3 days), with no check that price
      is still PRICE-close to the strong high/low by the time an H1 entry
      actually fires -- so `origin_stop_loss()` can end up anchored to a
      structural point that's now a long way from entry, producing stops
      (and 3R targets) far outside anything the source material
      describes.

      What was fixed in this pass, for continuation trades specifically: a
      real GBPUSD "plug and play" chart (user-supplied, cross-checked
      directly) confirmed that a plug-and-play stop sits just past the
      FAR edge of the specific imbalance overlapping the key level --
      because the trade's whole thesis is "price came here to sweep
      liquidity AND rebalance THIS gap," and has no logical reason to
      trade beyond it if that thesis holds. `imbalance_stop_loss()`
      implements this and now takes priority over the generic
      continuation stop rules whenever a continuation trade's key level
      overlaps an imbalance (`trade_kind == "continuation" and
      imbalance_overlap`) -- logged as `stop_kind == "imbalance"`.
      Deliberately scoped to continuation trades only per direct
      instruction; origin trades still used the (then stale-prone)
      structural-extreme stop. Covered by
      `test_run_backtest_uses_imbalance_stop_for_plug_and_play_continuation_trades`
      in `engine/tests/test_runner.py`.

      **Follow-up fix: the origin-trade stop-loss, verified frame-by-frame
      against Video 13 and Video 4.** Video 13's direct student Q&A on
      origin stop-loss placement says to stop "just beyond this
      particular high/low -- the strong high/low that was actually
      created -- give it a bit more room to breathe," and its worked Gold
      example shows two tightly-spaced local key levels, not a
      days-old daily extreme. Video 4's "origin of the move" walkthrough
      goes further: frame-by-frame review of the mentor's own TradingView
      risk/reward tool (downloaded from the video's GitHub release asset,
      frames extracted with `ffmpeg` at 8s intervals) shows him repeatedly
      dragging only the TARGET edge of the box while the STOP edge stays
      fixed at a constant 9 pips (`0.00090`) below entry across every
      frame -- direct visual confirmation that the origin stop is a
      *local*, tightly-scoped point, matching the "two major assignments"
      principle he states explicitly elsewhere in the same video ("price
      is looking to attack liquidity... and rebalance... at what
      particular pricing level do you expect price to bounce off from?").
      This lines up exactly with a gate the runner already computes:
      `_find_liquidity_setups()` finds, for every entry, the single H4
      liquidity point that was swept to trigger that specific reaction
      (`LiquiditySetup.liquidity_price`) -- the "particular high/low that
      was actually created" the mentor means -- but it was being thrown
      away; `origin_stop_loss()` instead pulled from a Daily-timeframe
      strong-high/low snapshot (`_strong_at()`/`_strong_extreme_snapshots()`,
      now removed) chosen by pure time-proximity to the bias flip, which
      could be price-stale (or not yet set at all) by the time an H1
      entry actually fired. Fix: `EntryCandidate` now carries
      `liquidity_price` forward from its originating `LiquiditySetup`, and
      `origin_stop_loss()` anchors to `candidate.liquidity_price` instead
      -- the same local point used to trigger the trade in the first
      place. Covered by
      `test_run_backtest_anchors_origin_stop_to_the_setup_own_liquidity_point`,
      which also demonstrates the old failure mode directly: with the
      Daily strong-low snapshot not yet set that early after the bias
      flip, the old code returned `None` and silently dropped the trade
      entirely, rather than just mis-sizing its stop.

      **Wiring in the ranking system (why the backtest's win rate looked
      lower than a discretionary trader's).** After the origin-stop fix
      above, a live EURUSD/conservative run went from 123 trades (94
      `still_open`) to 396 (2 `still_open`) with a 28.2% win rate -- a
      valid measurement now, but still well under a claimed ~80% for the
      same strategy traded by hand. Investigating that gap turned up two
      concrete, unrelated-to-Bishop's-teaching implementation gaps, not a
      strategy misunderstanding: (1) `ranking.py` fully implements
      Section 5's 4-factor key-level quality scoring (imbalance overlap,
      recency, QMR test count, imbalance-fill-size override) but
      `score_candidates()` was never called from `runner.py` --
      `ranking_score` logged `0.0` on every single trade; (2)
      `_find_liquidity_setups()`'s reaction-level selection was a bare
      "nearest in price to the swept liquidity point" rule, which can
      never reproduce Bishop's own "Repeating System" override (a farther
      level with a bigger unfilled imbalance wins outright over a nearer
      one). In short: the backtest was taking every mechanically
      qualifying setup with zero discretion layered on top, while a
      discretionary trader is constantly doing the selective filtering
      `ranking.py` was built to formalize.

      Fix: `_rank_reaction_level()` (new, in `runner.py`) scores every
      same-direction H4 key level still in play by the time liquidity is
      swept via `score_candidates()`, replacing the nearest-price pick,
      and falls back to Video 18's `default_to_extreme()` on score ties.
      `ranking_score` itself isn't threaded through to `TradeRecord` yet
      (still logs `0.0`) -- a natural follow-up, not done in this pass.
      Covered by
      `test_rank_reaction_level_lets_a_bigger_imbalance_override_the_nearer_level`
      (an isolated case with a clear, non-tied winner) and
      `test_rank_reaction_level_returns_the_only_candidate_without_scoring`.
      This changes which key level gets used for EVERY trade, origin and
      continuation alike (not just origin trades, unlike the two fixes
      above) -- expect the aggregate stats to move again on the next
      real-data run, not just the origin subset.

      **Immediate follow-up: a real hang on the first live rerun.** The
      real EURUSD/conservative run triggered right after this landed
      never finished -- GitHub Actions' "Run backtest" step sat
      `in_progress` for 20+ minutes with no output, versus ~1 minute for
      every prior run. Root cause: `candidate_levels` in
      `_find_liquidity_setups()` filtered same-direction H4 key levels by
      `lvl.time <= liquidity_point.time` only -- no LOWER time bound. Over
      a 23-year series that can be every matching-bias key level ever
      detected, and `_rank_reaction_level()` now runs a
      `count_tests_before_disrespect()` scan (formation -> liquidity
      sweep) for EACH one -- for an old level, that window can span years
      of H4 candles. A synthetic stress test confirmed it directly:
      a 5,000-candle (~3.4 year) series took 32s with the unbounded
      version; that scales worse than linearly as the series (and the
      candidate pool) grows, matching the observed hang on 23 years of
      real data. Fix: `candidate_levels` is now also bounded to the
      CURRENT structural leg -- formed at or after the previous breakout,
      any direction -- which caps both the candidate count and each
      candidate's scan window to a single inter-breakout span. Same
      synthetic test, WITH the fix: a 20,000-candle (~13 year) series
      completed in 12s. Not yet covered by an automated regression test
      (the synthetic fixtures in `test_runner.py` are all single-breakout,
      so they never exercised the unbounded path) -- worth adding one
      if this area gets touched again.

      **Found via the trade-chart viewer: the same "unbounded historical
      match by price alone" bug, in imbalance matching.** The very first
      real trade looked at through `backtest/webapp/`'s new candlestick
      charts (a "plug and play" continuation trade) had an 83-pip stop --
      nothing like the tight 5-15 pip stops every video example shows.
      Its `imbalance_fill_size` was 114.4 pips: the "imbalance" it was
      anchored to was a huge, clearly-anomalous gap. Root cause was the
      same class of bug as the hang above, just in a different spot:
      `h1_imbalances = detect_imbalances(h1)` is computed once over the
      WHOLE multi-year H1 series, and `overlapping = [im for im in
      h1_imbalances if overlaps_level(im, new_key_level.price)]` matched
      by PRICE only -- an imbalance from years earlier or later, with
      nothing to do with this setup, could win just because its price
      range happened to bracket the key level, and `widest_imbalance`
      then picked the single biggest one out of all of those spurious
      matches. Same issue existed on the H4 side feeding `ranking.py`'s
      `imbalance_overlap`/`imbalance_fill_size` factors
      (`_rank_reaction_level()`'s `h4_imbalances` argument). Fix: both
      sites now bound the imbalance match to a relevant time window --
      the H1 site to between the key level's own formation and the entry
      (`new_key_level.time <= im.time <= curr.time`, matching "price is
      returning to fill an imbalance that already exists"), the H4 site
      to the same current-structural-leg bound already used for
      `candidate_levels`. Covered by
      `test_run_backtest_ignores_an_overlapping_imbalance_formed_after_entry`,
      a direct regression test for the exact scenario found live: an
      otherwise-identical overlapping imbalance placed after entry is now
      correctly excluded. Also changes `test_run_backtest_uses_imbalance_
      stop_for_plug_and_play_continuation_trades`'s fixture, which used to
      place its imbalance after the entry trigger too (fine for exercising
      detection mechanics, but not actually a scenario "plug and play"
      describes) -- it's now positioned between the sweep and the
      reaction, which is what price returning to fill an already-existing
      gap actually looks like.

      **Entry-gate rebuild, part 1: multi-timeframe alignment.** A long
      user walkthrough (real charts, direct Q&A) surfaced that the entry
      gate was missing something Bishop's material treats as load-bearing:
      "4H can't stand alone if at least the Daily isn't aligned to it."
      `resolve_effective_bias()` only ever checked which single
      highest-priority timeframe had an active bias reading -- it never
      confirmed that Daily and H4 *each* independently gave their own
      breakout or sweep+break (never an open-close break or plain engulf,
      per the bias-flip rules already in `bias.py`) agreeing with the
      trade direction. `_aligned_timeframes()` (new) checks Weekly/Daily/H4
      each for their own recent confirmation, bounded by `ALIGNMENT_LOOKBACK`
      per tier (a modeling choice, not a number from the source material);
      `run_backtest` now requires at least Daily+H4 aligned before a setup
      is even considered, and logs which tiers aligned on `TradeRecord`
      (`aligned_timeframes`) so a later pass can check whether more
      alignment actually correlates with a better win rate. This is the
      first of several planned entry-gate changes from that same
      conversation (four distinct confirmation-entry trigger types
      replacing the single engulf-only path, origin/continuation
      reclassified as independent of which trigger fired, per-trigger stop
      rules, and ERL-capped targets) -- landing incrementally, each with
      its own tests, rather than as one large change.

      **Entry-gate rebuild, part 2: reaction-level selection is reactive,
      not scored.** The same conversation corrected a deeper assumption:
      which same-direction H4 key level price actually reacts from isn't
      a ranking/scoring problem at all -- "we don't predict, we react."
      `_rank_reaction_level()` (part of the ranking-fix change above) is
      removed; `_find_liquidity_setups()` now orders every same-direction
      candidate still in play (same current-structural-leg bound as
      before) nearest-to-extreme by distance from the swept liquidity
      point, and `_find_entry_candidates()` tries them in that order,
      taking whichever candidate is the first to actually produce a
      genuine touch-and-engulf reaction within the existing
      `REACTION_LOOKAHEAD` window -- falling through to the next candidate
      if the nearer one never holds. The extreme (farthest) candidate is
      the last resort, not a scored pick, and a deep retracement through
      the breakout point does NOT disqualify a candidate from being
      reacted off. `ranking.py` and its own tests are untouched and still
      exercise the 4-factor scoring logic standalone; they're just no
      longer wired into this gate. Covered by updating
      `test_find_liquidity_setups_finds_breakout_then_liquidity_then_reaction_level`
      to assert the full nearest-to-extreme ordering instead of a single
      scored winner, and by the two now-redundant `_rank_reaction_level`
      isolation tests being removed (the function no longer exists). This
      also flips the shared `synthetic_cache` fixture's actual reaction
      level back to 1.1012 (the nearest candidate, which already produces
      a genuine reaction in that fixture) instead of the scored tie-break's
      1.101 -- see the fixture's own H1 comments, which already described
      1.1012 and were never updated when scoring was wired in.

      **Entry-gate rebuild, part 3: the 4th-man confirmation trigger.**
      Same conversation surfaced a 4th distinct confirmation-entry trigger
      type, beyond plug-and-play/breakout-sweep+break/engulfing: "4th man
      confirmation" (a name Bishop's own students use, not present
      anywhere in the transcribed knowledge base -- confirmed directly by
      the user). `entries.py`'s new `fourth_man_confirmation_level()` is a
      2-candle liquidity-sweep-and-reclaim detector: the current candle
      sweeps one side of the previous candle's range, closes back INTO
      it, while the previous candle's OTHER side stays untouched ("still
      standing") -- the same shape Bishop's supplementary "building bias
      with liquidity" material uses backward-looking for bias, here used
      forward-looking as a direct entry trigger. Returns a V-shape
      (bullish) / A-shape (bearish) `KeyLevel` at the reclaim candle's
      close, matching key_levels.py's existing closing-price convention
      and the "2 candles in, one KeyLevel out" shape `detect_open_close_
      level()` already uses. Preferred on 1H/2H per direct user guidance,
      with 30M also valid per Bishop's own material -- not yet wired into
      `runner.py`'s entry gate (that's the next part, alongside the other
      3 trigger types and the origin/continuation rework); this pass is
      the standalone, tested detection primitive only. Covered by
      `engine/tests/test_entries.py`: valid bullish/bearish sweep-and-
      reclaim, and two negative cases (the "other side" also breaking, no
      sweep at all).

      **Entry-gate rebuild, part 4: origin/continuation by literal
      sequence.** Same conversation corrected trade_kind's whole basis:
      "origin" vs. "continuation" is about POSITION IN THE MOVE (first
      instance vs. repeated instance), independent of which of the 4
      confirmation-entry trigger types fired -- not a fixed time window.
      The old `ORIGIN_WINDOW` heuristic (3 calendar days from the most
      recent Daily bias-flip breakpoint) could misclassify a trade purely
      because it happened to fall inside/outside an arbitrary window,
      with no relationship to whether an earlier trade had actually
      already been taken in that leg. `bias.py`'s new `origin_time_at()`
      (a companion to `bias_at()`) returns the actual TIME of the
      breakpoint currently in effect, not just its direction;
      `runner.py`'s new `claimed_origins` bookkeeping in the main loop
      claims the FIRST entry per (effective_tf, direction, origin_time)
      leg as "origin" and labels every later entry in that same
      still-active leg "continuation" -- H4 (which has no full
      BiasCascade replay, only a running confirmation stream) uses its
      own most recent confirmation's time as the origin-event stand-in
      via the new `_last_time_at()`. Claiming only happens AFTER a
      candidate survives the stop-on-correct-side guard, so a setup that
      gets rejected there doesn't burn the "origin" slot for the real
      first trade in that leg. `ORIGIN_WINDOW` is removed entirely.

      This surfaced two real fixture/test consequences, not just a
      rename: (1) a fixture with only ONE trade in its whole series is
      now correctly "origin" by construction (nothing precedes it) --
      `synthetic_cache`'s base scenario flips from "continuation" to
      "origin", tightening its stop from a flat 10 pips to the swept
      liquidity point (1.1015, stop 1.1014), which in turn needed one
      more H1 candle appended so the now-closer 1:3 target still
      resolves within the fixture. Tests that specifically exercise
      "continuation" stop-loss behavior (the plug-and-play imbalance
      stop, the ignores-imbalance-after-entry regression, aggressive
      entry pricing) now call a new `_add_earlier_origin_trade()` helper
      that appends a genuine second, independent H4 breakout+liquidity+
      reaction cascade earlier in time, so it claims "origin" and leaves
      the fixture's own trade as "continuation" -- verified directly
      against `_find_liquidity_setups()`/`_find_entry_candidates()`
      before wiring in, same practice as the original fixture derivation.
      (2) This also surfaced a real, previously-invisible edge case:
      `origin_stop_loss()` anchors only to the swept liquidity point, but
      an AGGRESSIVE-style entry can land AT a reaction key level that
      sits beyond that liquidity point in the trade direction, putting
      the stop on the wrong side of entry. `_stop_on_correct_side()`
      already catches and drops that trade rather than open a corrupted
      one (no bug there), but it means aggressive+origin trades in that
      configuration get silently skipped today. Not fixed in this pass
      (out of scope for a classification-only change) -- flagged here as
      a concrete Task 5 (stop-loss rebuild) follow-up: origin stops
      should anchor past the FARTHEST point actually reached, not just
      the liquidity point in isolation.

      **Entry-gate rebuild, part 5: stop-loss keyed to trigger type.**
      Same conversation delivered a direct correction to the whole
      stop-loss model: placement is keyed to WHICH CONFIRMATION-ENTRY
      TRIGGER fired -- plug and play / engulfing / 4th man confirmation /
      breakout-as-entry -- NOT to trade_kind. The old "origin trades get
      their own stop rule, anchored to the swept liquidity point, taking
      priority over everything else" framing (part 4's own follow-up
      note above) is retired entirely. Three of the four triggers are now
      wired into the gate itself:
      - `_find_entry_candidates()`'s reaction search now uses a new
        `_reaction_trigger()` (checks engulfing first, then Task 3's
        `fourth_man_confirmation_level()`) instead of only accepting
        engulfing -- `EntryCandidate` carries a new `trigger` field.
      - Two new stop-loss functions in `entries.py`: `engulfing_stop_loss()`
        (a pad beyond whichever of the engulfing/engulfed candles' own
        wicks is MORE EXTREME -- "the engulfing candle might sweep the
        engulfed candle... the lowest btw both of them", a direct
        correction to an earlier version of this rule that only used the
        engulfing candle's own wick) and `fourth_man_stop_loss()` (a pad
        below/above the sweeping candle's own extreme, the 4th-man
        default).
      - A UNIVERSAL fallback, applying across all four trigger types:
        when a trigger's own natural stop anchor comes out unreasonably
        wide, fall back to the H4 key level itself (the reaction level
        the setup rejected from) instead -- "if the logic is correct and
        price shouldn't come back to it... The probability is like 1 or 2
        out of 10" (direct user quote). `origin_stop_loss()` is REUSED for
        this (its formula -- pad beyond a specific reference price -- was
        already exactly right; only its ROLE changed, from an
        origin-specific rule to a cross-trigger fallback; see its
        docstring). The new `_natural_stop_too_wide()` (runner.py) decides
        when to use it, gated by a new `MAX_NATURAL_STOP_PIPS` constant
        (30 pips -- a judgment call, not a number from the source
        material, picked generously above STRATEGY.md's own 5-15 pip
        worked examples).
      - Plug and play (imbalance overlap) still takes priority over the
        other three rules whenever it applies, unchanged from before.
      - New `trigger_type` field on `TradeRecord`, and `stop_kind` values
        changed to match: `"plug_and_play"` / `"engulfing"` /
        `"fourth_man"` (plus `"engulfing_kl_fallback"` /
        `"fourth_man_kl_fallback"` when the universal fallback fires) --
        replacing the old `"imbalance"` / `"origin"` / `"continuation"` /
        `"tight_no_irl"` values. `continuation_stop_loss()` and
        `tight_stop_loss_no_irl()` are no longer wired into this gate
        (same "still exists, no longer called" treatment `ranking.py` got
        in part 2) since trade_kind/IRL-required no longer select the
        stop rule.

      This incidentally FIXES the wrong-side-stop edge case part 4
      flagged as a follow-up: an aggressive entry at a reaction level
      beyond the swept liquidity point no longer risks a wrong-side stop,
      because the engulfing/4th-man rules derive from price actually near
      entry rather than a separate liquidity-point reference --
      `test_run_backtest_aggressive_style_enters_at_key_level_price` no
      longer needs the `_add_earlier_origin_trade()` workaround it
      briefly picked up in part 4 and now asserts a real, single-trade
      stop value directly. Every existing fixture whose expected stop_kind/
      stop_loss depended on the old model was re-verified against the
      actual code (not guessed) and updated -- most fixtures needed one
      more trailing H1 candle since the new engulfing-derived stops tend
      tighter, pushing the 1:3 target further from entry than the old
      liquidity-point anchor did. Two new dedicated tests cover the pieces
      with no prior coverage: `test_run_backtest_fires_on_a_fourth_man_
      reaction` (an end-to-end entry via the 4th-man trigger, not just the
      isolated detector) and `test_run_backtest_falls_back_to_the_key_
      level_when_the_natural_stop_is_too_wide` (a 64-pip engulfed wick
      correctly triggers the universal fallback instead of chasing it).

      NOT done in this pass, flagged rather than silently skipped (see
      runner.py's and entries.py's own module docstrings): breakout-as-
      its-own-entry-trigger still isn't detected (so `breakout_leg_stop_
      loss()` isn't added either, since nothing would call it); the "must
      also clear any other nearby same-type KL still reachable" stop-width
      rule isn't implemented.

      **Entry-gate rebuild, part 6: ERL-capped targets.** Same
      conversation's last correction to the mechanics: 3:1/4:1 is a
      DEFAULT, not an unconditional target -- "price wants to go from
      internal range liquidity to external," and a straight R:R target
      that would overshoot the REAL external range liquidity actually
      visible on 4H/Daily/Weekly should be capped there instead, not left
      to run past it. `trade_management.py`'s `primary_target()` gains an
      optional `erl_price` parameter: when given, it caps the plain 1:3
      target at `erl_price` if the plain target would overshoot it
      (backward compatible -- omitting `erl_price` reproduces the old
      unconditional behavior exactly, so every pre-existing caller/test
      of `primary_target()` is untouched). `runner.py`'s new
      `_nearest_erl()` computes that price: the nearest untaken
      structural swing point (`structural_liquidity_points()`, n=2), in
      the trade direction, across whichever of 4H/Daily/Weekly candle
      series are passed -- checking all three and taking whichever is
      NEAREST naturally recovers "the real, closest constraint" without
      needing to prioritize by timeframe, since a closer H4 point already
      wins over a farther Daily/Weekly one by construction. Wired into
      the main loop's target computation (`erl_price = _nearest_erl(...)`
      before `primary_target(...)`). Keeps the existing 3:1
      `RISK_REWARD_PRIMARY` baseline unchanged -- STRATEGY.md's "3:1 or
      4:1" isn't given a precise rule for choosing between the two, so
      this only adds the cap on top of the existing default rather than
      guessing a selection rule.

      This immediately started binding in nearly every existing fixture:
      the shared `synthetic_cache`-derived H4 series has its own genuine
      swing highs (H4 idx2 at 1.1030, idx6 at 1.1042) sitting closer than
      the raw 3:1 target for most of this session's entry prices --
      correct, realistic behavior for the toy fixture's tight structure,
      not a bug to route around. Every affected test's `r_multiple`
      assertion was recomputed from the actual capped `primary_target`
      (now also asserted directly, not just the resulting R-multiple) so
      the ERL-cap behavior is visible in test code, not just incidentally
      passing. Two new dedicated `_nearest_erl()` unit tests cover the
      piece with no other coverage: picking the nearer of two real,
      already-formed points across different timeframes (not just
      whichever series happens to be checked first), and excluding a
      point that hasn't formed yet as of entry time or that already sits
      behind entry (not a forward constraint anymore). `trade_management
      .py` also gained a direct `primary_target()` ERL-capping test
      (capped when nearer, unchanged when the ERL sits beyond the plain
      target, and the bearish mirror).

      NOT done in this pass: `_nearest_erl()` doesn't check whether a
      candidate point has already been swept by price before entry (an
      already-taken swing point isn't real ERL anymore, but that
      refinement isn't modeled) -- flagged in runner.py's module
      docstring rather than silently skipped.

      **Entry-gate rebuild, part 7 (final): stop/target decision audit
      trail, and the dashboard catches up.** Closes out the 7-part
      rebuild from the same conversation. `TradeRecord` gains 5 new
      fields, persisted specifically so the empirical claims behind
      parts 5-6's mechanized rules can eventually be validated against
      real data instead of just assumed -- e.g. the direct user quote
      behind the universal stop-loss fallback ("if the logic is correct
      and price shouldn't come back to it... The probability is like 1
      or 2 out of 10") is exactly the kind of claim a backtest dataset
      should be able to check, not just encode: `natural_stop_loss` (what
      the trigger's own rule would have placed, before any fallback),
      `stop_fallback_used`, `raw_target` (the plain rr target before any
      ERL cap), `erl_price` (the ERL actually used to cap it, if any),
      `erl_capped`. Wired through `run_backtest`'s stop-loss and target
      blocks alongside the values already being computed there -- no new
      detection logic, just persisting decisions already being made.
      `report.py`'s trade-by-trade reasoning table also now shows
      `trigger_type` and `aligned_timeframes` per row (previously
      computed and logged since parts 1 and 5, but never surfaced on the
      dashboard) -- `.get()` with a "—" placeholder so CSVs from earlier
      runs, before these columns existed, still render instead of
      erroring. New tests: audit-trail assertions added to the part 5/6
      tests that already exercise the plug-and-play/engulfing/4th-man/
      fallback/ERL-cap paths (rather than duplicating fixtures), a CSV
      round-trip check for the new fields, and a report test confirming
      graceful degradation on an older-format CSV missing the newer
      columns entirely.

      NOT done in this pass, and not attempted (see runner.py's module
      docstring for the full list this rebuild leaves open): whether
      price later revisits an unused natural/default stop level even
      after the trade closed (would need a post-close forward scan --
      the single most direct way to validate the "1 or 2 out of 10"
      claim itself, and the most natural next step if this backtest ever
      moves toward the "intelligent system" framing raised in the
      originating conversation); breakout-as-its-own-entry-trigger;
      the "cover other nearby same-type KL" stop-width rule; 2H liquidity
      fallback.

      **ERL redefinition: Daily/Weekly period extremes, not H4 swing
      fractals.** The first real backtest run after the 7-part rebuild
      above (EURUSD, full 2003-2026 history, conservative style) surfaced
      a serious problem in part 6's ERL cap: total R went from +71
      (pre-rebuild baseline) to -22, DESPITE win rate improving from 31%
      to 77%. Breaking the "after" run down by `erl_capped`: 530 of 551
      trades (96%) got their target capped, and those capped trades
      averaged only +0.025R per trade -- wins were real but tiny, nowhere
      near enough to cover the fixed -1R losses. Root cause: `_nearest_erl
      ()` used a generic 2-candle swing fractal (`structural_liquidity_
      points(..., n=2)`) across H4/Daily/Weekly as its ERL definition --
      on 23 years of H4 candles there's a swing point every few bars, so
      it fired on nearly every trade. That's not what ERL means in this
      codebase's own pre-existing model: `liquidity.py`'s
      `SequentialLiquidityTracker` (Section 3, built well before this
      rebuild) already defines ERL as a PERIOD's own high/low (previous
      daily/weekly/monthly/session extreme), and this rebuild's Task 6
      never consulted it, inventing a new and wrong concept from scratch
      instead. Fixed: `_nearest_erl()` now only accepts Daily/Weekly
      candle series (H4 dropped entirely -- it's the entry cascade's own
      internal working timeframe, not external relative to it) and a new
      `_unswept_period_extremes()` treats each period's own high/low as a
      candidate, excluding (a) the still-forming period `as_of_time`
      itself falls inside (a "previous" reference has to have actually
      closed) and (b) any period extreme already exceeded by a LATER
      period before entry (once swept, it's not real untaken liquidity
      anymore -- the exact gap flagged as a known limitation in part 6,
      now filled in, since its real-world impact wasn't visible until
      tested against actual market data). Implemented as an O(n)
      monotonic-stack "next greater/smaller-or-equal element" scan per
      call, not an O(n^2) rescan per candidate -- a Daily series alone is
      8,000+ candles across a full backtest, called once per trade.
      Even a genuinely correct ERL doesn't always cause a reversal when
      swept (direct user correction) -- that's inherently probabilistic
      and this fix doesn't pretend to model it; it only stops manufacturing
      false-positive ERL candidates that were never real external
      liquidity in the first place. New tests replace the old H4-fractal-
      based ones: `_unswept_period_extremes()` isolation tests (still-
      forming exclusion, already-swept exclusion), `_nearest_erl()`
      cross-timeframe/behind-entry tests using only Daily/Weekly, and a
      wiring regression test asserting the runner never passes H4 into
      `_nearest_erl()` again. Every part-6/7 fixture's `primary_target`/
      `erl_price`/`erl_capped` assertions were re-verified against the
      corrected behavior -- most now resolve to the plain, uncapped 3:1
      target, since the shared fixture's own tiny 9-day Daily series has
      no genuine untaken high near the relevant price range once day 8's
      dominant spike (needed to bootstrap the Daily bias) is excluded as
      still-forming.

      **Year/date-range filtering and configurable R:R.** `run_backtest()`
      gains `start_date`/`end_date`/`rr` parameters (and the CLI gains
      `--year`/`--start`/`--end`/`--rr`, `run-backtest.yml` gains matching
      `year`/`rr` workflow_dispatch inputs) so a specific calendar year
      (e.g. 2026) or an alternate target ratio (STRATEGY.md's "3:1 or
      4:1", not just the 3:1 default) can be reported without a code
      change. Deliberately NOT a data-loading window: start_date/end_date
      only gate which finished trades get appended to the returned/
      written records -- ALL cached history still loads and still drives
      bias-building, alignment, `claimed_origins` origin/continuation
      bookkeeping, and `concurrent_open_positions_at_entry` stacking
      context, so a 2020 trade still correctly claims an "origin" slot
      even when only 2026 is being reported, and pre-2026 open positions
      still count toward stacking for a 2026 entry. Narrowing the loaded
      data itself would silently break all of that context, not just trim
      the output. The CLI writes filtered/alternate-rr runs to a
      suffixed filename (`EURUSD_conservative_2026.csv`,
      `..._rr4.csv`) rather than the canonical `{instrument}_{style}.csv`,
      so they land alongside the main dashboard entry instead of
      overwriting it.

      `report.py` turns the CSV trade logs into the GitHub Pages
      dashboard described above -- dependency-free (no Chart.js/CDN, just
      inline SVG generated in Python), so it renders identically whether
      or not the viewer's browser can reach a CDN. Beyond the summary
      stats and equity curve, it also renders a **trade-by-trade
      reasoning table** directly on the page (not just a CSV download) --
      each row reconstructs the trade's story from `TradeRecord`'s
      fields: the bias reading on every timeframe and which one won the
      priority hierarchy, which entry pattern fired, the key level and
      its QMR/imbalance quality signals, and which stop-loss rule
      applied -- so the dashboard answers "why did it take this trade",
      not just "did it win". Capped at the most recent 1,000 trades per
      run to keep the page a sane size; the CSV download link still has
      the full history. Covered by `engine/tests/test_report.py`.
- [ ] **Not yet built**: Monthly (the one remaining level of the full
      Monthly->Weekly->Daily->4H->lower cascade -- Weekly is now wired,
      see Phase 5 above); performance metrics beyond win rate/total R
      (drawdown, profit factor); multi-instrument batch runs;
      weight-sweeping across Phase 2's `ranking.py` factors or Phase 4's
      entry-style/stop-rule variants against real results.

Four deliberate design choices worth flagging:
- STRATEGY.md never gives a precise algorithm for identifying "a prior
  swing point" ("look to the left" is qualitative). Phase 1 uses a
  standard n-bar fractal (local extreme over n bars each side) with `n`
  exposed as a parameter, so swing sensitivity is a backtest-tunable
  input rather than something silently hardcoded as if it were part of
  the taught rule.
- STRATEGY.md's Section 9 explicitly flags unresolved tension between its
  four key-level ranking factors, with no combination rule given. Phase 2
  doesn't guess one -- `ranking.py`'s `DEFAULT_WEIGHTS` (equal weighting)
  is a placeholder to have something runnable, and every factor is left
  independently inspectable on `RankedCandidate` so different weightings
  can be swept during backtesting instead of assumed.
- Video 18 draws a semantic distinction between "break of structure"
  (initiation/origin) and "breakout" (continuation) that's separate from
  Video 16's visual sweep-vs-no-sweep distinction, and Section 2 itself
  reconciles them as related but not identical. Phase 3 doesn't implement
  a third independent classifier for this -- a confirmation event is
  BOS/origin exactly when it's the event that flips `BiasCascade.direction`,
  and a continuation/breakout otherwise, which is a direct reading of
  Section 2's own reconciliation ("a storyline typically begins with a
  break of structure... subsequent confirmations in that established
  direction are properly breakouts").
- Video 13's original 4-branch decision tree describes branches 2 and 4
  with more candle-by-candle detail than Video 14's 3-pattern restatement
  captures (e.g. branch 2 mentions an intermediate "third candle taps the
  original IRL" step Video 14 doesn't repeat). `entries.py`'s
  `classify_entry_pattern()` implements Video 14's simpler 3-pattern
  version directly off the candles immediately following the engulf,
  which is a deliberate simplification -- worth revisiting against real
  backtest output if FRESH_IRL_REQUIRED or NESTED_DISRESPECT classifications
  look wrong on actual charts.
- `runner.py`'s module docstring lists its own MVP simplifications in
  full (Weekly->Daily->H4->H1 with Weekly optional/Monthly still out of
  scope, bootstrapped initial bias, simplified H4/H1 bias readings,
  engulf-open as the consumed key level, a proximity-based
  origin/continuation heuristic, bounded look-ahead windows for QMR/
  confirmation checks, and the same-candle stop-vs-target tie-break) --
  not repeated here to avoid the two copies drifting out of sync.

Candle processing is a plain forward loop over a `list[Candle]`, not
vectorized pandas -- so the same detection code can later replay live,
just-closed MT5 bars one at a time instead of only working in batch mode.
