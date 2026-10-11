#!/usr/bin/env python3
"""Vision pass over extracted frames: pixel metrics + BLIP VQA.
Output: knowledge-base/frame-analysis/pixel/annotations.jsonl
Run:  python3 knowledge-base/frame-analysis/vision_pass.py [--videos bishop]
"""
import argparse, glob, json, os, time
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # knowledge-base/
OUT = os.path.join(ROOT, 'frame-analysis', 'pixel', 'annotations.jsonl')

def pixel_metrics(f):
    im = Image.open(f).convert('RGB'); a = np.asarray(im).astype(int)
    h, w, _ = a.shape; R,G,B = a[...,0],a[...,1],a[...,2]
    pct = lambda m: round(100*int(m.sum())/(h*w), 3)
    return dict(green=pct((G>R+25)&(G>B+25)), red=pct((R>G+40)&(R>B+20)),
                yellow=pct((R>180)&(G>150)&(B<100)), magenta=pct((R>150)&(B>150)&(G<100)),
                cyan=pct((G>150)&(B>150)&(R<100)), blue=pct((B>150)&(R<100)&(G<160)))

QUERIES = [
    ("Is there a candlestick chart in this image?", "chart"),
    ("What is drawn on the chart?", "drawn"),
    ("Is there a horizontal line on this image?", "hline"),
    ("What color are the lines drawn on the chart?", "color"),
]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--videos', default='')
    ap.add_argument('--max-per-video', type=int, default=6)
    args = ap.parse_args()
    from transformers import pipeline
    pipe = pipeline("visual-question-answering", model="Salesforce/blip-vqa-base")
    files = sorted(glob.glob(os.path.join(ROOT,'frames','*','sheets','*.jpg')) +
                   glob.glob(os.path.join(ROOT,'frames','*','t_*.png')))
    if args.videos:
        files = [f for f in files if args.videos in f]
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['file'] for l in open(OUT)}
    t0=time.time(); n=0
    with open(OUT,'a') as fh:
        byvid={}
        for f in files:
            v=f.split('frames/')[1].split('/')[0]
            byvid.setdefault(v,[]).append(f)
        for v,lst in sorted(byvid.items()):
            picks = lst[:args.max_per_video]
            for f in picks:
                if f in done: continue
                rec = {"file": f, "video": v, "pixels": pixel_metrics(f), "vqa": {}}
                for q,k in QUERIES:
                    try: rec["vqa"][k] = pipe(f, question=q)[0]['answer']
                    except Exception as e: rec["vqa"][k] = f"ERR:{type(e).__name__}"
                fh.write(json.dumps(rec)+"\n"); fh.flush(); n+=1
                print(v, os.path.basename(f), rec["vqa"], flush=True)
    print(f"{n} new records in {time.time()-t0:.0f}s -> {OUT}")

if __name__ == '__main__':
    main()
