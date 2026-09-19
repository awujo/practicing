"""Tests for the parts of the frame extractor that are not ffmpeg.

The ffmpeg calls cannot be tested here (no ffmpeg in this environment,
and mocking a subprocess proves nothing about a filter string). What CAN
be tested is the transcript pairing -- and that is the part worth
testing, because a frame captioned with the wrong sentence is worse than
an uncaptioned one: it invents context that was never said, and the whole
point of this pipeline is to stop deriving rules from words alone.
"""

import textwrap

import pytest

from ..extract_frames import frame_times, parse_transcript, text_at, write_index


@pytest.fixture
def transcript(tmp_path):
    p = tmp_path / "transcript.txt"
    p.write_text(textwrap.dedent("""\
        [3.4-7.9] Good afternoon and happy Sunday everyone.
        [7.9-13.1] So today we will be talking about entries.
        [42.2-47.5] Now, we know that a four hour break out, right?
        [47.5-54.2] So if our break out is what confirms our bias.
    """))
    return str(p)


def test_cues_parse_with_their_times(transcript):
    cues = parse_transcript(transcript)
    assert len(cues) == 4
    assert cues[0] == (3.4, 7.9, "Good afternoon and happy Sunday everyone.")
    assert cues[-1][0] == 47.5


def test_lines_that_are_not_cues_are_skipped_not_guessed_at(tmp_path):
    """A transcript in another shape must yield nothing, visibly, rather
    than plausible-looking wrong captions."""
    p = tmp_path / "other.txt"
    p.write_text("00:03 Good afternoon\nsome prose with no timestamps at all\n")
    assert parse_transcript(str(p)) == []


def test_text_at_returns_what_is_being_said_then(transcript):
    assert "happy Sunday" in text_at(parse_transcript(transcript), 5.0)
    assert "four hour break out" in text_at(parse_transcript(transcript), 45.0)


def test_a_frame_in_a_silent_gap_gets_nearby_speech_with_a_window(transcript):
    """Frames land on a fixed grid, not on cue boundaries, so a frame at
    30s falls in a gap here. With a window it picks up the sentences
    around it -- which is what says what "this level" refers to."""
    cues = parse_transcript(transcript)
    assert text_at(cues, 30.0) == ""
    assert "four hour break out" in text_at(cues, 30.0, window=15.0)


def test_the_window_joins_every_overlapping_cue_in_order(transcript):
    said = text_at(parse_transcript(transcript), 50.0, window=10.0)
    assert said.index("four hour break out") < said.index("confirms our bias")


def test_frame_times_start_at_zero_and_cover_the_duration():
    assert frame_times(60, 15) == [0, 15, 30, 45, 60]
    # A duration that is not a multiple of the interval must not invent a
    # frame past the end of the video.
    assert frame_times(59, 15) == [0, 15, 30, 45]
    assert frame_times(10, 15) == [0]


def test_a_missing_or_absent_transcript_is_not_an_error(tmp_path):
    """15 of the 18 main-course videos have notes.md and no transcript.
    Requiring one is why that course went unframed: the workflow skipped
    every video it could not caption. The notes already record what was
    SAID; the frames are wanted for what was DRAWN."""
    assert parse_transcript("") == []
    assert parse_transcript(str(tmp_path / "nothing-here.txt")) == []


def test_the_index_says_so_when_there_is_no_transcript(tmp_path):
    """An empty caption column with no explanation reads like a bug in
    the pairing, which is the one failure this pipeline must not have
    ambiguity about."""
    out = tmp_path / "index.md"
    write_index(str(out), "video-07", [0, 15], cues=[], per_sheet=25)
    body = out.read_text()
    assert "No transcript for this video" in body
    assert "knowledge-base/videos/video-07/notes.md" in body
    # The rows are still there -- timestamps are the point of the index.
    assert "| 0 | 00:00 |" in body
    assert "| 15 | 00:15 |" in body


def test_the_index_carries_captions_when_there_is_a_transcript(transcript):
    """The no-transcript header must not leak into the normal case."""
    import os
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "index.md")
    write_index(out, "bishop-entries-part5", [5], cues=parse_transcript(transcript))
    body = open(out).read()
    assert "No transcript for this video" not in body
    assert "Good afternoon" in body


def test_both_modes_name_frames_by_the_second_they_were_seeked_to():
    """The burned label, the filename and the seek target must all be the
    same number, or a `t=` citation cannot be checked.

    Sheets mode used to run one `fps=1/interval` pass and burn a COMPUTED
    `n*interval` label. That is an assumption about which frame the
    filter picked, and it was wrong: bishop-repeating-system's sheet tile
    burned "t=1110s" over a chart with an FVG indicator and shaded zones,
    while `-ss 1110` on the same video gives a clean chart."""
    import inspect
    from ..extract_frames import build_sheets, extract_at_times, _label_filter

    src = inspect.getsource(extract_at_times)
    # Body only: the docstring names the fps filter while explaining why
    # it is gone, and a check that reads it would pass on the mention.
    body = src.replace(extract_at_times.__doc__ or "", "")
    assert '"-ss", str(t)' in body, "must seek to the requested second"
    assert 'f"t_{t:05d}.{ext}"' in body, "filename must carry that same second"
    assert "fps=1/" not in body, "the fps filter rewrites timestamps -- no longer used"

    # The label is formatted from the same `t` that is seeked to.
    assert "t\\=1110s" in _label_filter(1110)

    # Sheets are tiled by glob, because the names are timestamps not a
    # counter -- a %05d sequence would silently tile nothing.
    assert '"-pattern_type", "glob"' in inspect.getsource(build_sheets)


def test_zero_padding_keeps_lexicographic_order_equal_to_numeric_order():
    """build_sheets globs, so the tile's position on the sheet is decided
    by filename sort. Without padding, t_1110 would sort before t_195 and
    every index.md row would point at the wrong picture."""
    times = [0, 15, 195, 1110, 14370]
    names = sorted(f"t_{t:05d}.jpg" for t in times)
    assert names == [f"t_{t:05d}.jpg" for t in sorted(times)]
