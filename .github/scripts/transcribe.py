"""Transcribes an audio file with faster-whisper -- run only from the
transcribe.yml GitHub Actions workflow, where huggingface.co (the
model-weight host) is reachable. This session's own network egress
policy blocks huggingface.co, the same class of restriction already
documented for the backtest data pipeline (see backtest/README.md).

Paths come from AUDIO_PATH / TRANSCRIPT_PATH so the workflow can drive
it once per video in a loop. They default to the single-video paths the
workflow used before it did whole releases, so an older dispatch still
works.

Output format is one cue per line, `[start-end] text`, which is what
knowledge-base/tools/extract_frames.py's CUE regex parses to pair
transcript text with extracted frames. Changing it breaks that pairing
silently -- the index would render with an empty caption column and look
like a video that simply has no transcript.
"""

import os
import sys

from faster_whisper import WhisperModel

audio = os.environ.get("AUDIO_PATH", "/tmp/video/audio.wav")
out = os.environ.get("TRANSCRIPT_PATH", "/tmp/video/transcript.txt")
model_size = os.environ["WHISPER_MODEL"]

model = WhisperModel(model_size, device="cpu", compute_type="int8")
segments, info = model.transcribe(audio, beam_size=5, vad_filter=True)

print(f"Detected language: {info.language} (prob {info.language_probability:.2f})")

# Written incrementally: `segments` is a generator that does the actual
# work as it is consumed, and on a 30-minute video that is several
# minutes. Writing as we go means a killed job still leaves a usable
# partial transcript rather than an empty file.
count = 0
with open(out, "w") as f:
    for seg in segments:
        f.write(f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text.strip()}\n")
        count += 1

print(f"wrote {count} cues to {out}")

# A transcript with no cues is not a success. It means the audio was
# silent, the extraction produced nothing, or VAD rejected everything --
# and an empty file committed as a transcript is worse than none, because
# the workflow would then skip the video on every future run as "already
# transcribed".
if count == 0:
    sys.exit(f"no cues produced from {audio} -- refusing to write an empty transcript")
