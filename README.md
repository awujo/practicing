# Trading Strategy Knowledge Base

Source material and extracted strategy notes from mentor's video course (12 videos), being processed incrementally.

## Structure
- `knowledge-base/videos/video-XX/` — transcript + strategy notes extracted from each video
- `knowledge-base/frames/video-XX/` — key chart/setup screenshots extracted from each video
- `knowledge-base/STRATEGY.md` — the consolidated, cumulative strategy rulebook (built up as videos are processed)
- `backtest/` — backtesting code (once strategy rules are formalized)
- `bot/` — live automation code (once backtesting validates the strategy)

## Ingesting a new source video

Upload the video as a GitHub Release asset (the pattern already used for
`video1`, `remaining-videes`, `defi-bishop`, `plug-and-play`, etc. --
Releases handle large binaries git itself shouldn't carry), then trigger
`.github/workflows/transcribe.yml` from the Actions tab with that
release's tag. It downloads the video, extracts audio, transcribes it
with `faster-whisper`, and commits the raw transcript to
`knowledge-base/videos/<release_tag>/transcript.txt` -- entirely on
GitHub's infrastructure, since transcription needs to reach
huggingface.co for model weights, which most Claude Code sessions'
network policy (including backtesting work in this repo) blocks, the
same restriction documented in `backtest/README.md` for market-data
vendors. Once the transcript lands, it still needs a human (or an
assistant session) to actually read it and write the analysis notes --
transcription itself doesn't extract strategy content.

## Status
- [x] Video 1: "Welcome, Address and Mode of Operation" — processed (orientation only, no strategy rules)
- [x] Video 4: "Part 2 - Structure" — processed (core structure/liquidity framework extracted)
- [ ] Video 6: "Part 2 - Liquidity" — transcribing now
- [ ] Video 7: "Defined Ranges / Range Cycle" — queued
- [ ] Video 8: "Part 2 - Range" — queued
- [ ] Video 9: "Bias / Storyline" — queued
- [ ] Videos 2, 3, 5, 10, 11, 12 — not yet uploaded

See `knowledge-base/STRATEGY.md` for the current consolidated rulebook.
