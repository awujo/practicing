"""
VPS resource snapshot -- pure /proc reads, no new dependency (psutil
isn't in this project's requirements, and this doesn't need it).

Built 2026-08-29 to finally settle a question left open since the
reconnect-backoff work (bot/OPERATIONS_LOG.md, "2026-08-28 -- reconnect
backoff"): whether the recurring "Terminal: Authorization failed"
outages are VPS-side (this box is shared with another production app,
kugo-backend, that never idles -- confirmed contending for CPU/swap) or
broker-side (MetaQuotes-Demo's free pool being flaky). Nothing observed
so far distinguishes the two. Capturing load/memory/swap at the exact
moment a reconnect fails gives real correlation data instead of two
standing guesses -- high load+swap at failure time points at the VPS;
clean resource numbers at failure time point at the broker.

Linux-only (reads /proc directly) -- this only ever runs on the VPS."""

import os


def resource_snapshot() -> str:
    """One compact line: load average, memory used/total, swap
    used/total, CPU count. Returns a short "unavailable: <reason>" string
    instead of raising if /proc isn't readable (e.g. running this on a
    dev machine, or in a container without /proc mounted as expected) --
    a diagnostic that crashes the thing it's diagnosing defeats the
    point."""
    try:
        load1, load5, load15 = os.getloadavg()
    except OSError as exc:
        return f"unavailable: {exc}"

    mem = _read_proc_meminfo()
    if mem is None:
        return f"load={load1:.1f},{load5:.1f},{load15:.1f} mem=unavailable"

    mem_total_gb = mem.get("MemTotal", 0) / 1024 / 1024
    mem_available_gb = mem.get("MemAvailable", 0) / 1024 / 1024
    mem_used_gb = mem_total_gb - mem_available_gb
    swap_total_gb = mem.get("SwapTotal", 0) / 1024 / 1024
    swap_free_gb = mem.get("SwapFree", 0) / 1024 / 1024
    swap_used_gb = swap_total_gb - swap_free_gb

    cpus = os.cpu_count() or 0

    return (f"load={load1:.1f},{load5:.1f},{load15:.1f} "
            f"mem={mem_used_gb:.1f}/{mem_total_gb:.1f}GB "
            f"swap={swap_used_gb:.1f}/{swap_total_gb:.1f}GB "
            f"cpus={cpus}")


def _read_proc_meminfo() -> dict[str, int] | None:
    """Parses /proc/meminfo's "Key:     value kB" lines into {Key: kB}.
    Returns None if the file can't be read at all."""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
    except OSError:
        return None

    values = {}
    for line in lines:
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        digits = "".join(ch for ch in parts[1] if ch.isdigit())
        if digits:
            values[key] = int(digits)
    return values
