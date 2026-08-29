from unittest.mock import mock_open, patch

from .. import diagnostics


MEMINFO_SAMPLE = """MemTotal:        2000000 kB
MemFree:          100000 kB
MemAvailable:     200000 kB
SwapTotal:        2000000 kB
SwapFree:          600000 kB
Buffers:           50000 kB
"""


def test_resource_snapshot_reports_load_memory_and_swap():
    with patch.object(diagnostics.os, "getloadavg", return_value=(7.2, 4.1, 3.8)), \
         patch.object(diagnostics.os, "cpu_count", return_value=2), \
         patch("builtins.open", mock_open(read_data=MEMINFO_SAMPLE)):
        result = diagnostics.resource_snapshot()

    assert "load=7.2,4.1,3.8" in result
    assert "cpus=2" in result
    # 2000000 kB total = ~1.9 GB; used = total - available = 1.8GB-ish
    assert "mem=1.7/1.9GB" in result
    assert "swap=1.3/1.9GB" in result


def test_resource_snapshot_survives_getloadavg_failing():
    with patch.object(diagnostics.os, "getloadavg", side_effect=OSError("no /proc")):
        result = diagnostics.resource_snapshot()
    assert result.startswith("unavailable:")


def test_resource_snapshot_survives_meminfo_being_unreadable():
    with patch.object(diagnostics.os, "getloadavg", return_value=(1.0, 1.0, 1.0)), \
         patch("builtins.open", side_effect=OSError("no /proc/meminfo")):
        result = diagnostics.resource_snapshot()
    assert "load=1.0,1.0,1.0" in result
    assert "mem=unavailable" in result


def test_read_proc_meminfo_parses_key_value_kb_lines():
    with patch("builtins.open", mock_open(read_data=MEMINFO_SAMPLE)):
        values = diagnostics._read_proc_meminfo()
    assert values["MemTotal"] == 2000000
    assert values["SwapFree"] == 600000


def test_read_proc_meminfo_returns_none_when_unreadable():
    with patch("builtins.open", side_effect=OSError("nope")):
        assert diagnostics._read_proc_meminfo() is None
