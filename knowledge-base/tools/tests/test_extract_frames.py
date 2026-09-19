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

from ..extract_frames import frame_times, parse_transcript, text_at


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
