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
