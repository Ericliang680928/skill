#!/usr/bin/env python3
"""Split a song into N shots with per-shot durations -> plan.json (prompts left blank)."""
import argparse, json, subprocess, sys


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed (is ffmpeg installed?): " + out.stderr)
    return float(out.stdout.strip())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("audio"); p.add_argument("--shots", type=int, default=12)
    p.add_argument("--min", type=float, default=5); p.add_argument("--max", type=float, default=10)
    p.add_argument("--sections", help="JSON [{name,start}] to align cuts to song sections")
    p.add_argument("-o", "--out", default="plan.json")
    a = p.parse_args()
    total = duration(a.audio)
    n = a.shots
    base = total / n
    if base > a.max:
        print(f"WARNING: {total:.1f}s / {n} shots = {base:.1f}s > max {a.max}s; "
              f"clips will be shorter than the song. Raise --shots or --max.", file=sys.stderr)
    # even split, then snap each cut to nearest section start (if given)
    cuts = [round(i * base, 2) for i in range(n + 1)]
    if a.sections:
        starts = sorted(s["start"] for s in json.load(open(a.sections)) if 0 < s["start"] < total)
        for st in starts:
            j = min(range(1, n), key=lambda k: abs(cuts[k] - st))
            cuts[j] = round(st, 2)
        cuts = sorted(set(cuts))
        if len(cuts) != n + 1:
            sys.exit("Section snapping collided; pass fewer/farther sections.")
    shots = []
    for i in range(n):
        start, end = cuts[i], cuts[i + 1]
        d = min(max(end - start, a.min), a.max)  # what we ask the model to generate
        shots.append({"index": i + 1, "start": start, "end": end,
                      "span": round(end - start, 2), "duration": round(d, 2),
                      "prompt": "", "seed": 1000 + i + 1})
    json.dump({"audio": a.audio, "total": round(total, 2), "shots": shots},
              open(a.out, "w"), indent=2, ensure_ascii=False)
    print(f"{total:.1f}s song -> {n} shots, wrote {a.out}")


if __name__ == "__main__":
    main()
