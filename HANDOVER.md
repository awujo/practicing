# Handover

Read this first. It is written for whoever picks this up next — a new
agent, a new chat, or the operator after a gap — and it is meant to
replace scrolling back through a long conversation.

Last updated: 2026-09-29.

---

## 1. What this is, in one paragraph

An attempt to mechanise **SLK** (Structural Liquidity + Key levels) as
taught by two sources: **4th Man** (theory — what a thing *is*) and
**Bishop** (implementation — how it is *traded*). The operator's own
division of labour. The transcripts and chart measurements live under
`knowledge-base/`. The strategy is not mine and must not be improvised:
**if the source gives no number, the rule is expressed structurally or
it is not built.**

## 2. The single most important fact

**Nothing is trading.** Both live bots are notification-only. The
operator made that call on 2026-09-25 after the automated system lost
~10% on a demo account and a full-history backtest came back at gross
profit factor 0.99 — no edge.

The current goal is **not** an autonomous trader. It is a watcher that
never sleeps, reports the reasoning in plain English, and lets the
operator judge and take trades by hand. Their words: *"he is human, you
are machine."* Do not quietly re-enable execution.

## 3. Where the code is

    backtest/slk/        the SLK engine, rebuilt from the source
    bot/                 the live side: MT5, Telegram, the watchers
    knowledge-base/      transcripts, chart measurements, the spec
    backtest/engine/     the OLD engine, still used by the old bot

`backtest/slk/` was written from scratch on 2026-09-25 because the old
engine carried vocabulary that is mine and not the course's
("conservative" / "aggressive" entry styles, "engulfing" meaning a
candlestick pattern). Two hard constraints, stated in its `__init__.py`:

- **NO FUTURE** — every function takes candles up to *now*. Not a filter
  that remembers to bound itself; an argument that cannot contain
  tomorrow.
- **NO INVENTED NUMBERS** — see above. `n` (the swing width) has no
  default anywhere, deliberately, because the course never gives one.

### The SLK modules

    levels.py        the four key-level shapes, and the polarity flip
    stream.py        levels as they confirm, one candle at a time;
                     BreakTracker (breaks of structure)
    bias.py          rejection, closure, breakout on the next TF down
    cascade.py       THE BIAS. Structure is the bias; see §5
    sweep.py         liquidity: single-candle, IRL/ERL, the setup
    confirmation.py  the H1 open-close engulf (5.2)
    entries.py       inducement (5.3), breakout (5.4), sweep+break (5.5)
    liquidity.py     external range liquidity, as the target
    orders.py        one resting order per level, newest wins
    replay.py        the driver; walks H1 forward, observer hook for live
    narrative.py     the story in English, for Telegram
    run.py           backtest CLI
    analyse.py       per-trade CSV analysis

### The live side

    slk_watch.py       SLKWatcher: calls replay() and reports. Never trades.
    run_slk_watch.py   the SLK watcher process
    orchestrator.py    the OLD engine's live bot (LiveBot)
    run_live.py        the old bot's process
    signal_channel.py  the second Telegram bot (bias/storyline only)
    roll_call.py       the daily/weekly watchlist, shared by both engines
    telegram_notify.py the ORIGINAL Telegram log handler (old channel)

## 4. What runs on the VPS

Host `srv1294969`, **72.62.210.91**. Repo at
`/srv/slk-bot/mt5data/trading`. Everything trading-related runs inside
the Docker container **`mt5`** (MT5 under Wine, via `mt5linux`/rpyc),
working directory `/config/trading`, user `abc`. **It is `python3`, not
`python`.**

### Processes

| what | how it starts | state |
|---|---|---|
| `slk-bot2.service` | `/srv/slk-bot/launch_bot2.sh` | active, `--notify-only` |
| `slk-bot1.service` | `/srv/slk-bot/launch_bot1.sh` | **disabled** — entered at market, not limit |
| SLK watcher | manual `docker exec -d` (see below) | not yet a service |

The SLK watcher is **not** under systemd yet. That is the most obvious
next piece of operational work — it dies if the container restarts.

    source ~/.mt5_bot_env
    docker exec -d -u abc -e SLK_SIGNAL_TOKEN -e SLK_SIGNAL_CHAT \
      -w /config/trading mt5 sh -c \
      'python3 -u -m bot.run_slk_watch --n 2 --instruments ALL \
       --history-windows-config bot/history_windows.json \
       > /config/slk_watch.log 2>&1'

### Telegram, two channels

- **Old channel** — `telegram_notify.py`, attached as a logging handler.
  Now at `--telegram-level WARNING`, so it carries only real problems.
  The operator mutes it.
- **New channel** — `signal_channel.py`, its own bot token, env vars
  `SLK_SIGNAL_TOKEN` / `SLK_SIGNAL_CHAT`. Carries bias, storyline,
  setups, confirmations and roll calls from **both** engines, tagged
  `[SLK]` and `[aggressive]`. This is the one that gets read.

Credentials live in `~/.mt5_bot_env` on the host. `docker exec -e VAR`
with **no `=value`** passes them through without putting them in the
process table. The operator has explicitly said not to raise the subject
of rotating them again.

### The box itself

It is **heavily contended**: `top` showed **88.9% steal** (the
hypervisor takes most of the CPU), memory ~72%, swap ~97%. It also hosts
unrelated businesses (studifypro, kugoo). Assume everything is 10–50×
slower than a laptop and that `nice` makes it worse. This is why so much
of the work has been performance, and why measurements taken here do not
transfer.

## 5. What the engine currently believes

This changed materially on 2026-09-29 and the change matters more than
anything else in the file.

**Structure is the bias.** A timeframe's own most recent break of
structure gives the direction. repeating-system t=396-409:

> *"on the weekly timeframe you can see that we are bullish... we've been
> having breakouts to the upside. So I know that my weekly is bullish.
> My daily... the recent breakout was still to the upside. At no point
> was there a bearish breakout. **So we are still bullish no matter
> what.**"*

A key-level rejection or a liquidity sweep is the **setup inside** that
direction, not a competing vote — t=415-424: *"we have daily reject,
daily **in alignment with the structure**."*

Before that fix there were three independent direction-producers and
they contradicted each other inside one message (EURCHF read "Weekly
says bearish" and "Weekly structurally bullish" simultaneously, over a
chart that was plainly an uptrend). If you find yourself adding a fourth
signal that votes on direction, stop.

The cascade, in order:

    bias     each timeframe's own most recent break of structure.
             Daily carries it (the H4 setup hangs off the Daily);
             the Weekly agreeing is the PROBABILITY statement.
    setup    on H4: internal-range liquidity taken, the NEAREST key
             level to it, and a rejection from that level
    entry    on H1: engulf / inducement / breakout / sweep+break
    stop     the FAR EDGE of the zone being entered (see §6)
    target   the nearest untaken external liquidity

## 6. Things established the hard way — do not re-derive

- **The stop is the far edge of the open-close zone**, not the engulfing
  candle's extreme. Measured from Bishop's own charts, 13/13 with zero
  exceptions, one of them a broker screenshot
  (`knowledge-base/supplementary/bishop_pdf_sl_measurements.md`).
  *"PIP COUNT IS NOT THE RULE. Zone height IS."* His stops run 3.0 pips
  to 518.9.
- **"Engulfing" means a key level price CLOSED THROUGH**, not a
  candlestick pattern.
- **A level is played once** — "using it the first time it presented
  itself". 35% of setups were the same level firing again.
- **Ties go to the newest level**, matching newest-confirmation-wins.
- **Weekly is not a gate.** On disagreement Bishop *leaves* the weekly
  and trades daily→H4 with a nearer target. Making it a filter deletes
  trades he explicitly still takes.
- **`--n` has no default.** The course never defines a swing
  numerically. Sweeping it (1 / 2 / 3) is still an unrun experiment.

## 7. Known-unfinished, honestly

1. **The SLK watcher is not a systemd service.** Highest-value chore.
2. **The `n` sensitivity sweep has never been run.**
3. **No real performance number since the stop-rule correction.** The
   only full-history figure (AUDCAD, gross PF 0.99, −239.6R net, 261.7R
   drawdown) was measured with the WRONG stop rule and is obsolete.
   `backtest/slk/run.py --all --n 2 --spread 1.0` would produce a new
   one; it takes hours on that box.
4. **Entry timeframe is H1 only.** The source's ladder reaches M5;
   scoped deliberately by the operator on 2026-09-19.
5. **A flipped key level is only traded the other way inside a reaction**
   (`entries.ReactionWatch`); the level stream still drops a
   disrespected level rather than flipping it.
6. **Spread is charged per trade against its own risk; slippage and
   correlation are not modelled at all.**

## 8. How to work on this

The operator is an experienced discretionary trader, is tired of this
project, and is paying for tokens. What they have asked for repeatedly,
in their own words:

- *"Model what was taught."* Do not invent. Quote the transcript with a
  timestamp when you add a rule.
- *"Always double check things rather than wasting tokens and time."*
  Before claiming a fix works, try to break it. Several bugs in this
  repo were found only by asking "could this test ever fail?" — and at
  least three tests here were vacuous when first written.
- Do not pipe `pytest` into `tail` and chain `&&` off it. The exit code
  becomes `tail`'s and broken code gets pushed. It happened twice.
- Read `backtest/slk/*.py` docstrings before changing them. They record
  *why*, including several wrong turns, so the same ground is not
  covered twice.

Run everything: `python3 -m pytest -q --ignore=backtest/webapp`
(1003 passing, 6 skipped as of this writing; `webapp` needs flask, which
is not installed in every environment).

Branch: `claude/trading-automation-strategy-8yx579`.

## 9. If something looks wrong in Telegram

The two most recent real bugs both surfaced that way, and both were
found by the operator comparing a message against a chart:

- A message contradicting itself → a modelling error (see §5).
- A structural reading that is weeks stale → `broke_at` and
  `newest_break` answer different questions and must not share an update
  rule.

That loop — read the message, check the chart, report the mismatch — is
currently the most effective debugging method available, because the
backtest numbers are not yet trustworthy enough to catch these.
