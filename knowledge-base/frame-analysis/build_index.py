#!/usr/bin/env python3
"""Build frame-index.md: every 'pointing' moment in the transcripts paired with
the exact contact-sheet image that shows it, plus a machine-readable rules table.

Sheet layout: 25 frames per sheet (5x5), one frame per 15s, reading order.
frame N (0-based second = N*15) lives in sheet (N//25)+1 at slot (N%25).
"""
import csv, re, os, json
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))          # knowledge-base/frame-analysis
FRAMES = os.path.join(ROOT, '..', 'frames')                # knowledge-base/frames
DEIXIS = re.compile(r'(this level|this point|right here|this zone|you can see|look at|as you see|marked|circle|drawn|this setup|this is what)', re.I)
CORE = [  # (video, topic) - the modules STRATEGY.md is built from
 ('kevin-story-line','M0 Storyline'), ('kevin-basic-ms','M1 Basic MS'),
 ('kevin-basic-ms-pt2','M1 Basic MS'), ('kevin-basic-ms-pt3','M1 Basic MS'),
 ('kevin-advance-market-sturcture','M2 Advanced MS'), ('kevin-advance-market-sturcture-pt2','M2 Advanced MS'),
 ('kevin-advance-market-sturcture-pt3','M2 Advanced MS'),
 ('kevin-liquidity','M3 Liquidity'), ('kevin-liquidity-pt2','M3 Liquidity'), ('kevin-liquidity-pt3','M3 Liquidity'),
 ('kevin-key-levels-pt1','M4 Key Levels'), ('kevin-key-levels-pt3','M4 Key Levels'), ('kevin-key-levels-pt4','M4 Key Levels'),
 ('kevin-introduction-to-entry','M5 Entries'), ('kevin-entry-2','M5 Entries'), ('kevin-entry3','M5 Entries'), ('kevin-entry-4','M5 Entries'),
 ('kevin-cadjpy-bd','Worked breakdown'), ('kevin-eurgbp-bd','Worked breakdown'),
 ('bishop-bias-entries','Bishop bias->entry'), ('plug-and-play','Plug & Play'),
]
def sheet_for(sec):
    n = sec // 15                       # frame index
    return n // 25 + 1, n % 25          # (sheet number, slot 0-24) rows-first in 5x5

rows = list(csv.DictReader(open(os.path.join(FRAMES, '..', 'frame-analysis', 'annotations.csv'))))
by_video = defaultdict(list)
for r in rows: by_video[r['video']].append(r)

out_md = ['# Frame Index — visual cross-reference for STRATEGY.md', '',
 'Every transcript moment where Kevin/Bishop points at the chart ("this level", "right here", "you can see"), mapped to the contact sheet that shows it.',
 'Sheets hold 25 frames @15s spacing, row-major. Slot numbers below are 1-based within the sheet.', '']
rules = []
for v, topic in CORE:
    pts = sorted(((int(r['sec']), r['speech']) for r in by_video.get(v, []) if DEIXIS.search(r['speech'])))
    kept, last = [], -999
    for s, sp in pts:
        if s - last >= 60: kept.append((s, sp)); last = s
    sheetdir = os.path.join(FRAMES, v, 'sheets')
    nsheets = len([f for f in os.listdir(sheetdir) if f.endswith('.jpg')]) if os.path.isdir(sheetdir) else 0
    out_md.append(f'\n## {v} — {topic} ({len(kept)} pointing moments, {nsheets} sheets)')
    for s, sp in kept:
        sh, slot = sheet_for(s)
        img = f'frames/{v}/sheets/sheet_{sh:03d}.jpg' if sh <= nsheets else 'MISSING'
        out_md.append('- `%02d:%02d` slot %d of `sheet_%03d` 2192 %s — 201c%s201d' % (s//60, s%60, slot+1, sh, img, sp[:80]))
        rules.append({'video': v, 'topic': topic, 'sec': s, 'sheet': f'{v}/sheets/sheet_{sh:03d}.jpg', 'slot': slot+1, 'speech': sp})
open(os.path.join(ROOT, 'frame-index.md'), 'w').write('\n'.join(out_md) + '\n')
json.dump(rules, open(os.path.join(ROOT, 'frame-index.json'), 'w'), indent=1)
print('pointing moments indexed:', len(rules))
