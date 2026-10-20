"""
Turn the course videos into something readable.

Why (2026-09-19). Every rule in this project was derived from
transcripts, and the one time that produced a concrete detector -- single
candle liquidity -- it measured WORSE than the thing it replaced and had
to be parked. The operator's diagnosis was blunt and correct: "you just
studied the transcribing, how do you expect to actually understand it
when you don't even see what the visual of it looks like." Trading is
taught by pointing at a chart. The words alone say "this low here", and
"here" is the entire content.

So: frames, paired with what is being said over them.

Two tiers, because reading four hours of video frame by frame is not
affordable. 14,373 seconds of Bishop video at one frame per 15s is ~960
frames, and a frame costs roughly 1,200 tokens to look at -- over a
million tokens to read them all once.

  sheets  -- every frame at `interval`, timestamp BURNED INTO each one,
             tiled into contact sheets. ~39 sheets for the whole course,
             cheap to skim, and the burnt-in timestamp is what makes a
             tile referenceable afterwards. Individual frames are deleted
             unless --keep-frames: they are 60MB+ and the sheets are the
             deliverable.

  frames  -- full resolution at specific timestamps, once the sheets have
             shown which moments matter. This is the tier that gets
             studied properly.

Both write an index.md pairing every frame with the transcript text
spoken over it, so a frame is never looked at without knowing what was
being explained.

Runs locally or in GitHub Actions; needs ffmpeg on PATH and nothing else.

    python3 knowledge-base/tools/extract_frames.py sheets \\
        --video bishop-entries-part5.mp4 \\
        --transcript knowledge-base/videos/bishop-entries-part5/transcript.txt \\
        --name bishop-entries-part5

    python3 knowledge-base/tools/extract_frames.py frames \\
        --video bishop-entries-part5.mp4 \\
        --transcript knowledge-base/videos/bishop-entries-part5/transcript.txt \\
        --name bishop-entries-part5 --at 420,435,450,1020
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# "[3.4-7.9] Good afternoon" -- the format every transcript in
# knowledge-base/videos/ uses.
CUE = re.compile(r"^\[(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\]\s*(.*)$")

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


def parse_transcript(path):
    """[(start, end, text)] in file order. Lines that do not match the cue
    format are skipped rather than guessed at -- a transcript with a
    different shape should produce an empty index, which is visible, not
    a set of plausible-looking wrong captions."""
    cues = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = CUE.match(line.strip())
            if m:
                cues.append((float(m.group(1)), float(m.group(2)), m.group(3).strip()))
    return cues


def text_at(cues, t, window=0.0):
    """What is being said at `t` (plus `window` seconds either side).

    Joined rather than nearest-match: a frame lands mid-sentence far more
    often than on a cue boundary, and the sentence around it is the part
    that says what "this level here" refers to."""
    hits = [c[2] for c in cues if c[1] >= t - window and c[0] <= t + window]
    return " ".join(hits).strip()


def frame_times(duration, interval):
    return [i for i in range(0, int(duration) + 1, interval)]


def probe_duration(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _hhmmss(t):
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def extract_interval(video, out_dir, interval, width, quality):
    """Select first source frame in each occupied interval bucket, preserving PTS."""
    if interval <= 0:
        raise ValueError("interval must be positive")
    os.makedirs(out_dir, exist_ok=True)
    label = (f"drawtext=fontfile={_font()}:" if _font() else "drawtext=")
    label += (r"text='t\=%{pts\:flt}s'"
              ":x=12:y=12:fontsize=28:fontcolor=yellow:box=1:boxcolor=black@0.65")
    # fps rounds onto a new clock and may select a frame half an interval
    # later than its output label. Keep the source presentation clock instead.
    filters = ["setpts=PTS-STARTPTS", f"select='if(isnan(prev_selected_t),1,gt(floor(t/{interval}),floor(prev_selected_t/{interval})))'", "showinfo"]
    if width:
        filters.append(f"scale={width}:-2")
    filters.append(label)
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-y", "-i", video,
         "-vf", ",".join(filters), "-fps_mode", "vfr", "-q:v", str(quality),
         os.path.join(out_dir, "f_%05d.jpg")], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"frame extraction failed: {result.stderr[-4000:]}")
    times = [float(t) for t in re.findall(r"\bpts_time:([0-9.eE+\-]+)", result.stderr)]
    files = sorted(f for f in os.listdir(out_dir) if f.startswith("f_"))
    if len(files) != len(times):
        raise RuntimeError(f"frame/time count mismatch: {len(files)} files vs {len(times)} timestamps")
    return files, times


def build_sheets(frame_dir, sheet_dir, cols, rows, tile_width, quality):
    os.makedirs(sheet_dir, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-start_number", "1", "-i", os.path.join(frame_dir, "f_%05d.jpg"),
         "-vf", f"scale={tile_width}:-2,tile={cols}x{rows}",
         "-q:v", str(quality),
         os.path.join(sheet_dir, "sheet_%03d.jpg")], check=True)
    return sorted(os.listdir(sheet_dir))


def write_index(path, name, times, cues, per_sheet=None):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {name}\n\n")
        fh.write("Frame timestamps paired with what is being said over them.\n")
        fh.write("Times are seconds from the start; the same number is burned\n")
        fh.write("into the top-left of each frame.\n\n")
        if per_sheet:
            fh.write(f"Contact sheets hold {per_sheet} frames each, in reading order:\n")
            fh.write(f"sheet_001 covers frames 1-{per_sheet}, and so on.\n\n")
        fh.write("| time | mm:ss | said over this frame |\n")
        fh.write("|---:|---|---|\n")
        for t in times:
            said = text_at(cues, t, window=4.0).replace("|", "/")
            fh.write(f"| {t:g} | {_hhmmss(t)} | {said} |\n")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("sheets", "frames"))
    ap.add_argument("--video", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--name", required=True, help="output folder name under --out")
    ap.add_argument("--out", default="knowledge-base/frames")
    ap.add_argument("--interval", type=int, default=15, help="seconds between frames (sheets mode)")
    ap.add_argument("--at", default="", help="comma-separated seconds (frames mode)")
    ap.add_argument("--width", type=int, default=1280,
                    help="scale width; 0 = native pixels, which frames mode "
                         "defaults to")
    ap.add_argument("--crop", default="",
                    help="ffmpeg crop, w:h:x:y, e.g. iw*0.82:ih*0.93:iw*0.03:0 to "
                         "drop the TradingView toolbar and watchlist. Cropping "
                         "rather than scaling is what preserves a 1px annotation")
    ap.add_argument("--quality", type=int, default=4, help="ffmpeg -q:v, lower is better")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--tile-width", type=int, default=420)
    ap.add_argument("--keep-frames", action="store_true",
                    help="keep the individual frames as well as the sheets "
                         "(tens of MB per video -- normally the sheets are the point)")
    args = ap.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg/ffprobe not found on PATH")

    cues = parse_transcript(args.transcript)
    if not cues:
        print(f"WARNING: no [start-end] cues parsed from {args.transcript} -- "
              f"the index will have no captions", file=sys.stderr)

    out_dir = os.path.join(args.out, args.name)
    os.makedirs(out_dir, exist_ok=True)

    if args.mode == "sheets":
        # Stage all output so failed re-extraction preserves the previous bundle.
        with tempfile.TemporaryDirectory(prefix=".extract-", dir=out_dir) as staging:
            frame_dir = os.path.join(staging, "frames")
            files, times = extract_interval(args.video, frame_dir, args.interval,
                                           args.width, args.quality)
            sheets = build_sheets(frame_dir, os.path.join(staging, "sheets"),
                                  args.cols, args.rows, args.tile_width, args.quality)
            write_index(os.path.join(staging, "index.md"), args.name, times, cues,
                        per_sheet=args.cols * args.rows)
            with open(os.path.join(staging, "timestamps.json"), "w") as fh:
                json.dump({"selection": "first source frame in each occupied interval bucket; empty buckets skipped",
                           "interval_seconds": args.interval, "actual_seconds": times}, fh)
                fh.write("\n")
            for name in ("sheets", "index.md", "timestamps.json"):
                destination = os.path.join(out_dir, name)
                if os.path.isdir(destination):
                    shutil.rmtree(destination)
                os.replace(os.path.join(staging, name), destination)
            destination = os.path.join(out_dir, "_frames")
            if os.path.isdir(destination):
                shutil.rmtree(destination)
            if args.keep_frames:
                shutil.move(frame_dir, destination)
        print(f"{args.name}: {len(files)} frames -> {len(sheets)} sheets "
              f"({args.cols}x{args.rows}), index.md written")
    else:
        # sheets wants 1280; frames wants every pixel there is.
        if "--width" not in sys.argv:
            args.width = 0
        times = [int(float(x)) for x in args.at.split(",") if x.strip()]
        if not times:
            sys.exit("frames mode needs --at with at least one timestamp")
        # Native pixels and PNG, unless told otherwise.
        #
        # The operator, 2026-09-19: "he uses a 1px line on his line tools
        # on his chart to indicate things which I don't even know if you
        # can read it." Right, and the first version of this could not:
        # scaling to 1280 and encoding to JPEG are both ways to lose a
        # one-pixel line, and those lines are the whole content of an
        # annotated chart.
        #
        # So frames mode downscales nothing by default and writes PNG.
        # Where the screen is still too wide to read afterwards, CROP --
        # dropping the toolbar and watchlist keeps every remaining pixel,
        # where scaling destroys them uniformly.
        chain = []
        if args.crop:
            chain.append(f"crop={args.crop}")
        if args.width:
            chain.append(f"scale={args.width}:-2")
        for t in times:
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-ss", str(t), "-i", args.video, "-frames:v", "1"]
            if chain:
                cmd += ["-vf", ",".join(chain)]
            cmd.append(os.path.join(out_dir, f"t_{t:05d}.png"))
            subprocess.run(cmd, check=True)
        write_index(os.path.join(out_dir, "index_selected.md"), args.name, times, cues)
        print(f"{args.name}: {len(times)} full-resolution frames written")


if __name__ == "__main__":
    main()
