# Kevin King SLK style - knowledge base only

Run Actions -> "Transcribe video release" -> Run workflow on THIS branch.
It transcribes every .mp4 in the release (default tag `kevin_King`) and makes
contact sheets, then commits them to:

- knowledge-base/videos/kevin-<name>/transcript.txt
- knowledge-base/frames/kevin-<name>/ (sheets + index)

No bot code lives here. Start the SLK-style work from these files.
