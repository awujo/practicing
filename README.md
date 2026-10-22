# Kevin King SLK style - knowledge base only

Run Actions -> "Transcribe video release" -> Run workflow on THIS branch.
It transcribes every .mp4 in the release (default tag `kevin_King`) and makes
contact sheets, then commits them to:

- knowledge-base/videos/kevin-<name>/transcript.txt
- knowledge-base/frames/kevin-<name>/ (sheets + index)

No bot code lives here. Start the SLK-style work from these files.

### Reliable news reminder timer

In cron-job.org create an HTTP GET job running every minute:

```text
https://slk-backtest-viewer.onrender.com/cron/news?key=YOUR_EXISTING_CRON_SECRET
```

Replace the placeholder with the private `CRON_SECRET` configured on Render. Alternatively use `/cron/news` with an `X-Cron-Secret` request header. This runs news checks directly; GitHub scheduling delays do not affect this timer.
