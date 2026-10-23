# Course and plug frame timing correction

2026-10-20. Study preparation only; no detector changes.

The retained course/plug contact sheets used the original ffmpeg `fps` output
clock. A picture labelled at a 15-second grid point could actually have been
selected about half an interval later. These sheets can show chart concepts,
but cannot establish the exact state at the burned timestamp.

A fresh extraction of all 18 course videos and plug-and-play has been started
from the original public release assets (`video1`, `remaining-videes`,
`plug-and-play`). Original file size and SHA256 are checked against GitHub's
release metadata before extraction. The existing corrected extractor selects
the first source frame in each occupied 15-second bucket, preserves source PTS,
burns the actual source time and writes `timestamps.json`.

Current staging (not yet published over existing sheets):
`/workspace/scratch/corrected_course_frames/`. Original verified MP4s are retained
in `/workspace/scratch/course_sources/` for exact native-frame followups.
The staging `manifest.json` records source filename/tag, expected and actual
hashes, native dimensions, duration, frame/sheet counts and completion state.
Read its individual `state` fields; starting a job does not prove completion.

Extraction uses 1280px tiles, 2×2 sheets. Upscaling cannot add native chart detail.
A fifteen-second overview does not prove an intrabar fill or guarantee a brief
annotation was captured. Such claims still need exact-time/native-frame checks.
The nine unique Bishop-session videos were corrected separately and are not
modified by this task.

## Completion — 2026-10-23

All19originalassets were hash-verified and all19corrected outputs are now
published under `knowledge-base/frames/<slug>/`:2,481frames/630sheets.
`course_frame_manifest.json` contains sourceURL/hash/nativeprobe/actualPTS
counts and SHA256 for every output. A fresh verification checked originals,
monotonic distinct15-second buckets, counts and every published output hash.

Together with the earlier nineunique Bishop sessions this is3,445unique
sampledframes/874sheets across28uniquevideos. The Part3duplicate adds116frames
and29sheets as an alias; do not count it as additional teaching. Old course
images remain available in Git at `dd91b14`, and a local backup under
`/workspace/scratch/pre_source_pts_course_frames/`. Readerreports distinguish
old/mixed/correctedversion coverage; replacingimages does not retroactively
mean they reviewed every new picture. Exact intrabar/source-state claims still
require dedicated native-time review rather than15-second overview inference.
