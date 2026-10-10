"""Transcribes /tmp/video/audio.wav with faster-whisper -- run only from
the transcribe.yml GitHub Actions workflow, where huggingface.co (the
model-weight host) is reachable. This session's own network egress
policy blocks huggingface.co, the same class of restriction already
documented for the backtest data pipeline (see backtest/README.md)."""

import os

from faster_whisper import WhisperModel

model_size = os.environ["WHISPER_MODEL"]
model = WhisperModel(model_size, device="cpu", compute_type="int8")
segments, info = model.transcribe("/tmp/video/audio.wav", beam_size=5, vad_filter=True)

print(f"Detected language: {info.language} (prob {info.language_probability:.2f})")

with open("/tmp/video/transcript.txt", "w") as f:
    for seg in segments:
        f.write(f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text.strip()}\n")
