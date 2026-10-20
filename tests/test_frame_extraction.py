"""Source pixels and source PTS must agree; output-clock labels are not evidence."""
import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('extract_frames', ROOT / 'knowledge-base/tools/extract_frames.py')
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)
pytestmark = pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg required')


def video(tmp_path, rate, count):
    raw = tmp_path / 'pixels.rgb'
    raw.write_bytes(b''.join(bytes([i * 3]) * (160 * 96 * 3) for i in range(count)))
    path = tmp_path / 'source.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                    '-video_size', '160x96', '-framerate', rate, '-i', str(raw),
                    '-c:v', 'ffv1', str(path)], check=True)
    return path


@pytest.mark.parametrize('rate,count,want_times,want_pixels', [
    ('1', 61, [0, 15, 30, 45, 60], [0, 45, 90, 135, 180]),
    ('3/2', 47, [0, 15.333, 30], [0, 69, 135]),
])
def test_interval_selects_source_time_not_future_midpoint(tmp_path, rate, count, want_times, want_pixels):
    path = video(tmp_path, rate, count)
    frames, times = E.extract_interval(str(path), str(tmp_path / 'out'), 15, 160, 2)
    assert times == pytest.approx(want_times, abs=.002)
    assert len(frames) == len(times)
    for name, expected in zip(frames, want_pixels):
        with Image.open(tmp_path / 'out' / name) as im:
            # Far from burned timestamp, this pixel directly encodes source frame number.
            assert im.convert('RGB').getpixel((145, 80))[0] == pytest.approx(expected, abs=3)
    index = tmp_path / 'index.md'
    E.write_index(index, 'source', times, [(15.3, 15.4, 'correct source cue')], 4)
    if rate == '3/2':
        assert '| 15.333 | 00:15 | correct source cue |' in index.read_text()


def test_interval_rejects_nonpositive(tmp_path):
    with pytest.raises(ValueError):
        E.extract_interval('unused', str(tmp_path), 0, 160, 2)


def test_variable_frame_rate_uses_actual_source_pts(tmp_path):
    # Frame timestamps0,.4,1.4,3.6; time gaps must not be relabeled1,2,3.
    source = video(tmp_path, '1', 5)
    vfr = tmp_path / 'vfr.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-vf',
                    'settb=AVTB,setpts=if(eq(N\\,0)\\,0\\,if(eq(N\\,1)\\,0.4\\,if(eq(N\\,2)\\,1.4\\,if(eq(N\\,3)\\,3.6\\,3.8))))/TB',
                    '-fps_mode', 'vfr', '-enc_time_base', '1:1000', '-c:v', 'ffv1', str(vfr)], check=True)
    frames, times = E.extract_interval(str(vfr), str(tmp_path / 'out'), 1, 160, 2)
    assert times == pytest.approx([0, 1.4, 3.6], abs=.002)
    for name, expected in zip(frames, [0, 6, 9]):
        with Image.open(tmp_path / 'out' / name) as im:
            assert im.convert('RGB').getpixel((145, 80))[0] == pytest.approx(expected, abs=3)


def test_sheet_rebuild_removes_stale_outputs(tmp_path):
    path = video(tmp_path, '1', 16)
    transcript = tmp_path / 'transcript.txt'
    transcript.write_text('[0-16] source narration\n')
    out = tmp_path / 'bundle' / 'example'
    (out / 'sheets').mkdir(parents=True)
    (out / 'sheets' / 'sheet_999.jpg').write_bytes(b'stale')
    (out / '_frames').mkdir()
    (out / '_frames' / 'f_99999.jpg').write_bytes(b'stale')
    subprocess.run(['python', str(ROOT / 'knowledge-base/tools/extract_frames.py'), 'sheets',
                    '--video', str(path), '--transcript', str(transcript), '--name', 'example',
                    '--out', str(tmp_path / 'bundle'), '--interval', '15', '--width', '160',
                    '--tile-width', '160', '--cols', '2', '--rows', '2'], check=True)
    import json
    assert json.loads((out / 'timestamps.json').read_text())['actual_seconds'] == [0, 15]
    assert len(list((out / 'sheets').glob('sheet_*.jpg'))) == 1
    assert not (out / '_frames').exists()
    assert '| 15 | 00:15 | source narration |' in (out / 'index.md').read_text()
