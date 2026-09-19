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
import os
import re
import shutil
import subprocess
import sys

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
    a set of plausible-looking wrong captions.

    No path, or a path that isn't there, means no captions rather than an
    error: 15 of the 18 main-course videos have hand-written notes.md and
    no transcript at all, and the frames are worth having without one --
    the notes already carry what was SAID, and it is what was DRAWN that
    only the frames can give."""
    if not path or not os.path.exists(path):
        return []
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


def _label_filter(t):
    """drawtext burning the REQUESTED time, which is also the time we
    seek to -- so the number on the frame and the number used to fetch it
    are the same value by construction."""
    f = (f"drawtext=fontfile={_font()}:" if _font() else "drawtext=")
    return f + (rf"text='t\={t}s'"
                ":x=12:y=12:fontsize=28:fontcolor=yellow:box=1:boxcolor=black@0.65")


def extract_at_times(video, out_dir, times, *, width=None, quality=4,
                     ext="jpg", crop="", label=False):
    """One seek per requested second. Both modes go through here, which
    is the point.

    Sheets mode used to do a single `fps=1/interval` pass and burn a
    COMPUTED label, `n*interval`, on each output frame. That label is an
    assumption about which input frame the filter picked, not a fact
    about the frame it is drawn on -- and the fps filter rewrites each
    frame's timestamp as it goes, so nothing downstream can check it.
    Frames mode meanwhile seeks to an explicit `-ss`. The two disagreed:
    bishop-repeating-system's sheet tile burned "t=1110s" over a chart
    with an FVG indicator enabled and shaded zones, while `-ss 1110` on
    the same video returns a clean chart. Same number, different moment.

    That is not a cosmetic problem. The contact sheet's burned number is
    what every citation in knowledge-base/ refers to, and index.md pairs
    transcript text to those same numbers. If the number does not
    identify the frame, a citation cannot be checked and the transcript
    can be paired with the wrong picture.

    Now both modes seek the same way to the same value, so a `t=` in a
    citation means one thing.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for t in times:
        chain = []
        if crop:
            chain.append(f"crop={crop}")
        if width:
            chain.append(f"scale={width}:-2")
        if label:
            chain.append(_label_filter(t))
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-ss", str(t), "-i", video, "-frames:v", "1"]
        if chain:
            cmd += ["-vf", ",".join(chain)]
        if ext == "jpg":
            cmd += ["-q:v", str(quality)]
        path = os.path.join(out_dir, f"t_{t:05d}.{ext}")
        cmd.append(path)
        subprocess.run(cmd, check=True)
        # A seek past the end produces no file rather than an error.
        if os.path.exists(path):
            written.append(os.path.basename(path))
    return written


def build_sheets(frame_dir, sheet_dir, cols, rows, tile_width, quality):
    """Tiles the extracted frames in filename order.

    Glob rather than a `%05d` sequence: frames are now named by the
    second they were seeked to (`t_01110.jpg`), not by a counter, so
    there is no sequence for ffmpeg to walk. Zero-padding makes
    lexicographic order the same as numeric order, which is what keeps a
    tile's position on the sheet matching its row in index.md.

    That naming is deliberate. A frame that carries its own timestamp in
    its filename can be checked against the sheet it is on; a frame
    called `f_00074.jpg` can only be trusted."""
    os.makedirs(sheet_dir, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-pattern_type", "glob", "-i", os.path.join(frame_dir, "t_*.jpg"),
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
        if not cues:
            fh.write("No transcript for this video, so the caption column is\n")
            fh.write(f"empty. See `knowledge-base/videos/{name}/notes.md` for what\n")
            fh.write("was said; these frames are here for what was drawn.\n\n")
        if per_sheet:
            fh.write(f"Contact sheets hold {per_sheet} frames each, in reading order:\n")
            fh.write(f"sheet_001 covers frames 1-{per_sheet}, and so on.\n\n")
        fh.write("| time | mm:ss | said over this frame |\n")
        fh.write("|---:|---|---|\n")
        for t in times:
            said = text_at(cues, t, window=4.0).replace("|", "/")
            fh.write(f"| {t} | {_hhmmss(t)} | {said} |\n")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("sheets", "frames"))
    ap.add_argument("--video", required=True)
    ap.add_argument("--transcript", default="",
                    help="optional; without it the index still pairs frames with "
                         "timestamps, just with an empty caption column")
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
        where = args.transcript or "(no --transcript given)"
        print(f"WARNING: no [start-end] cues parsed from {where} -- "
              f"the index will have no captions", file=sys.stderr)

    out_dir = os.path.join(args.out, args.name)
    os.makedirs(out_dir, exist_ok=True)

    if args.mode == "sheets":
        duration = probe_duration(args.video)
        times = frame_times(duration, args.interval)
        frame_dir = os.path.join(out_dir, "_frames")
        files = extract_at_times(args.video, frame_dir, times,
                                 width=args.width, quality=args.quality,
                                 ext="jpg", label=True)
        # Keep the index aligned with the frames that actually exist: a
        # seek past the end writes nothing.
        times = [t for t in times
                 if f"t_{t:05d}.jpg" in set(files)]
        sheets = build_sheets(frame_dir, os.path.join(out_dir, "sheets"),
                              args.cols, args.rows, args.tile_width, args.quality)
        write_index(os.path.join(out_dir, "index.md"), args.name, times, cues,
                    per_sheet=args.cols * args.rows)
        if not args.keep_frames:
            shutil.rmtree(frame_dir)
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
        extract_at_times(args.video, out_dir, times, width=args.width,
                         ext="png", crop=args.crop)
        write_index(os.path.join(out_dir, "index_selected.md"), args.name, times, cues)
        print(f"{args.name}: {len(times)} full-resolution frames written")


if __name__ == "__main__":
    main()
