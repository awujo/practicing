# Native source checks

`course07_strong_high/` preserves all 21 native PNGs inspected by the independent
verifier, with source SHA256 and requested seek times. These are original source
pixels extracted using the existing frame tool, not generated illustrations.
They have no burned timestamp; filenames encode requested source-zero seek
times. The generic scratch index's burned-label sentence does not apply.

`audio_rechecks/` preserves alternate forced-English ASR from native audio.
These are not human-verified transcripts and do not replace canonical text.
Each JSON records model, parameters, input WAV hash and source offset. Source
WAVs came from verified release MP4s using ffmpeg input seek and duration,
mono PCM16 at 16kHz. Filenames encode course/interval; source hashes/URLs are
in `course_frame_manifest.json`. Existing canonical speech still takes visual
referent checks; a confident-looking ASR token is not ground truth.

Small-English-model checks recover the garbled course8 opening: the student
asks whether two structural points must break (answer: one suffices), then
asks about timeframe-dependent ranges; W/D context and nested lower-TF cycles
are discussed. This corroborates other readable source passages. The middle
network-broken question remains uncertain. Course7 alternate ASR plus cursor
frames substantially resolves the OLD protected high versus NEW lower candidate
reference; see `full_study_verification.md`. Plug's sponsored-sales negation
remains ambiguous in the small-model check; no opposite universal rule follows.

A second forced-English `medium.en` run rechecked the same plug passage and
course8 network fragment. It corroborates the missed H3 order/M30 market entry
but still does not clearly resolve the sponsorship clause or the broken
question. Those uncertainties are retained. Model snapshot revisions and
weight hashes are recorded in `audio_rechecks/model_provenance.json`.
