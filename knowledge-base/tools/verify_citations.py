"""
Check every quote in SLK_SPEC.md against the raw transcripts.

The spec is my READING of the videos, and the code is checked against
the spec -- so an error made while watching a video survives every
audit downstream of it. That is not hypothetical: the QMR definition
was wrong in the spec for days and was caught because the operator said
so, not because anything re-read video-14. And the one quote checked by
hand on 2026-09-24, the load-bearing "if you have these two" line, had
a timestamp ten seconds out, which is enough to lose a passage in an
hour-long video.

This closes that gap mechanically. For each *"quoted"* passage followed
by a (source t=...) citation it:

  1. resolves the shorthand to a transcript,
  2. finds where the quote's own words actually appear,
  3. reports the REAL time range against the cited one.

WHAT A MISMATCH MEANS

  NOT FOUND    the words are not in that transcript. Either the wrong
               source is cited, or the quote was reconstructed from
               memory rather than copied. Both are serious.
  DRIFT        the words are there, at a different time. The claim
               stands; the citation does not lead anyone to it.
  OK           found, and the cited range overlaps where it sits.

Matching is deliberately fuzzy on punctuation and case but NOT on
words, and it searches the longest ellipsis-free fragment of each
quote -- the spec elides with "..." and inserts [clarifications], and
neither should count against a real quote.

USAGE

    python3 -m knowledge-base.tools.verify_citations      # from repo root
    python3 knowledge-base/tools/verify_citations.py
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
VIDEOS = os.path.join(KB, "videos")
SPEC = os.path.join(KB, "SLK_SPEC.md")

# The spec's shorthand, as it is actually written in the prose.
SOURCES = {
    "bias-1": "bishop-building-bias-1",
    "bias-2": "bishop-building-bias-2",
    "bd2": "bishop-trades-breakdown-2",
    "bd3": "bishop-trades-breakdown-3",
    "part5": "bishop-entries-part5",
    "entries-part5": "bishop-entries-part5",
    "routine": "bishop-daily-routine",
    "repeat": "bishop-repeating-system",
    "next": "bishop-what-next",
    "entries": "bishop-bias-entries",
    "bias-entries": "bishop-bias-entries",
    "plug-and-play": "plug-and-play",
    "plug and play": "plug-and-play",
}

LINE = re.compile(r"^\[(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\]\s*(.*)$")


def load(name):
    path = os.path.join(VIDEOS, name, "transcript.txt")
    if not os.path.exists(path):
        return None
    out = []
    for line in open(path):
        m = LINE.match(line.strip())
        if m:
            out.append((float(m.group(1)), float(m.group(2)), m.group(3)))
    return out


# What the auto-transcriber reliably mishears, mapped to what was said.
# Verified by reading the passages: bias-1 t=192-296 is entirely about
# "K-Levels", and bias-2 t=1137 says "single kind of liquidity" where
# the drawing on screen is single CANDLE liquidity. Without these the
# checker reports NOT FOUND on quotes that are in the transcript and
# correctly cited, which is worse than useless -- it would send someone
# to re-cite a claim that was right.
HEARD = [
    (r"\bk level\b", "key level"),
    (r"\bk levels\b", "key levels"),
    (r"\bsingle kind of liquidity\b", "single candle liquidity"),
    (r"\bkind of liquidity\b", "candle liquidity"),
    (r"\bweakly\b", "weekly"),
    (r"\btime frame\b", "timeframe"),
    (r"\btime frames\b", "timeframes"),
    (r"\bfour hour\b", "4h"),
    (r"\bfour hours\b", "4h"),
    (r"\b4 hour\b", "4h"),
]


def words(text):
    """Lowercased word list, punctuation dropped, known mishearings
    folded. Fuzzy on how a thing was written down and on what the
    transcriber got wrong, strict on WHICH WORDS were said."""
    t = re.sub(r"[^a-z0-9]+", " ", text.lower())
    for pat, sub in HEARD:
        t = re.sub(pat, sub, t)
    return t.split()


def fragments(quote):
    """The quote split at every elision or editorial insertion, longest
    first. The spec elides with "..." and inserts [clarifications]; a
    real quote must not be penalised for either."""
    parts = re.split(r"\.\.\.|\[[^\]]*\]|…", quote)
    frags = [words(p) for p in parts]
    return sorted((f for f in frags if len(f) >= 4), key=len, reverse=True)


def coverage(transcript, quote, ranges, pad=75.0):
    """How much of `quote` appears, IN ORDER, inside the cited window.

    Exact contiguous matching cannot verify this spec and it took a
    while to see why: the quotes are CLEANED COMPOSITES, not verbatim
    transcript. bias-2 t=1137 really says "Most times, your single
    candle liquidity, SINCE WE ARE STILL TALKING ABOUT LIQUIDITY, a
    single candle liquidity on your daily is going to be a structural
    liquidity ON YOUR FOUR-HOUR TIMEFRAME" -- and the spec renders that
    as one tidy sentence ending "[on the lower timeframe]". The claim is
    faithful; the punctuation is not. Demanding contiguity reported nine
    such quotes as NOT FOUND, which would have sent someone to re-cite
    claims that were right.

    So this asks the question that actually matters: are these words,
    in this order, in the passage the citation points at? A high score
    means the quote is a faithful compression of what was said there. A
    low one means it is not in that passage at all.

    `pad` is generous on purpose -- a citation is a pointer to a
    passage, not a frame-accurate index."""
    if not ranges:
        return 0.0, None
    lo = min(a for a, _ in ranges) - pad
    hi = max(b for _, b in ranges) + pad
    span = [w for a, b, text in transcript if b >= lo and a <= hi
            for w in words(text)]
    want = [w for w in words(quote) if len(w) > 2]
    if not want:
        return 0.0, None
    i = matched = 0
    first = last = None
    for w in span:
        if i < len(want) and w == want[i]:
            if first is None:
                first = w
            i += 1
            matched += 1
    return matched / len(want), (lo + pad, hi - pad)


def find(transcript, frag):
    """(start, end) of the first place `frag` appears, or None.

    The transcript is flattened to one word stream with each word's own
    time, so a quote spanning several caption lines still matches."""
    stream = []
    for a, b, text in transcript:
        for w in words(text):
            stream.append((w, a, b))
    flat = [w for w, _, _ in stream]
    n = len(frag)
    for i in range(len(flat) - n + 1):
        if flat[i:i + n] == frag:
            return stream[i][1], stream[i + n - 1][2]
    return None


def cited_range(cite):
    nums = re.findall(r"t[=≈](\d+)(?:-(\d+))?", cite)
    out = []
    for lo, hi in nums:
        lo = float(lo)
        out.append((lo, float(hi) if hi else lo))
    return out


def resolve(cite):
    m = re.search(r"video-(\d+)", cite)
    if m:
        return f"video-{int(m.group(1)):02d}"
    for key in sorted(SOURCES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", cite):
            return SOURCES[key]
    return None


def main():
    spec = open(SPEC).read()

    # Quotes first, citations second, and the citation may sit on EITHER
    # SIDE of the quote -- the spec writes both "...quote..." (src t=N)
    # and "Confirmed at src t=N: ...quote...". The first version of this
    # assumed quote-then-citation, so a leading citation made the match
    # run on to the NEXT quote's closing delimiter and report a false
    # NOT FOUND. Ten of them, which would have read as spec errors.
    quote_re = re.compile(r"\*\"(.+?)\"\*", re.S)
    cite_re = re.compile(r"\(?([A-Za-z0-9 ,;>\n-]*?t[=≈]\d[0-9 ,;=t≈-]*)\)?")
    WINDOW = 160

    found = []
    for m in quote_re.finditer(spec):
        quote = m.group(1)
        before = spec[max(0, m.start() - WINDOW):m.start()]
        after = spec[m.end():m.end() + WINDOW]
        # An operator correction is not a video citation and must not be
        # checked against one.
        if re.search(r"operator|Operator", before[-90:]):
            continue
        # SAME LINE FIRST, and before the quote before after it. The
        # targets table puts the citation in the LEFT cell and the quote
        # in the right one, so a naive "look after" grabs the NEXT row's
        # citation -- which mispaired every row of that table and
        # reported two false DRIFTs whose quotes were cited correctly.
        line_start = spec.rfind("\n", 0, m.start()) + 1
        line_end = spec.find("\n", m.end())
        line_end = line_end if line_end != -1 else len(spec)
        same_line_before = spec[line_start:m.start()]
        same_line_after = spec[m.end():line_end]

        # A TABLE ROW cites in its left cell; PROSE cites after the
        # quote, and that citation may wrap across lines -- the spec
        # contains "(routine\n> t=390-435)". So the table case must look
        # strictly left on its own line, and the prose case must look
        # right across lines. Getting either wrong pairs a quote with a
        # neighbour's citation and reports a drift that is not there.
        in_table = spec[line_start:line_end].lstrip().startswith("|")
        if in_table:
            order = [(same_line_before, -1)]
        else:
            order = [(after, 0), (before, -1)]

        cm = None
        for chunk, pick in order:
            hits = list(cite_re.finditer(chunk))
            if hits:
                cm = hits[pick]
                break
        if cm is None:
            continue
        found.append((quote, " ".join(cm.group(1).split())))

    print(f"SLK_SPEC.md: {len(found)} quote+citation pairs\n")

    cache = {}
    tally = {"OK": 0, "PARAPHRASE": 0, "DRIFT": 0, "NOT FOUND": 0,
             "NO TRANSCRIPT": 0}
    for quote, cite in found:
        cite = " ".join(cite.split())
        name = resolve(cite)
        label = quote.replace("\n", " ")[:58]
        if name is None:
            print(f"  ?  unresolved source   ({cite})\n     \"{label}...\"")
            tally["NO TRANSCRIPT"] += 1
            continue
        if name not in cache:
            cache[name] = load(name)
        tr = cache[name]
        if tr is None:
            print(f"  ?  no transcript: {name}   ({cite})")
            tally["NO TRANSCRIPT"] += 1
            continue

        ranges = cited_range(cite)

        # Contiguous first -- an exact hit also proves the timestamp.
        hit = None
        for frag in fragments(quote):
            hit = find(tr, frag)
            if hit:
                break

        if hit is not None:
            lo, hi = hit
            if any(not (hi < a - 15 or lo > b + 15) for a, b in ranges):
                tally["OK"] += 1
            else:
                tally["DRIFT"] += 1
                shown = ", ".join(f"{a:.0f}-{b:.0f}" for a, b in ranges)
                print(f"  !  DRIFT {name}: cited t={shown}, actually "
                      f"t={lo:.0f}-{hi:.0f}")
                print(f"     \"{label}...\"")
            continue

        # Not verbatim. Is it a faithful compression of the cited
        # passage, or is it not in that passage at all?
        score, _ = coverage(tr, quote, ranges)
        if score >= 0.75:
            tally["PARAPHRASE"] += 1
            print(f"  ~  PARAPHRASE {name} {cite}: {score:.0%} of the words "
                  f"are in that passage, in order, but not contiguously")
            print(f"     \"{label}...\"")
        else:
            tally["NOT FOUND"] += 1
            print(f"  X  NOT FOUND in {name}   ({cite})   best {score:.0%}")
            print(f"     \"{label}...\"")

    print()
    for k in ("OK", "PARAPHRASE", "DRIFT", "NOT FOUND", "NO TRANSCRIPT"):
        print(f"  {k:<14} {tally[k]}")
    return 1 if tally["NOT FOUND"] else 0


if __name__ == "__main__":
    sys.exit(main())
