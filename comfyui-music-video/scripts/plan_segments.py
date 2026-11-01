#!/usr/bin/env python3
"""Split a song into N shots with per-shot durations -> plan.json (prompts left blank)."""
import argparse, json, subprocess, sys


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    if out.returncode:
        sys.exit("ffprobe failed (is ffmpeg installed?): " + out.stderr)
    return float(out.stdout.strip())


def make_cuts(total, n, section_starts):
    """n+1 cut times. Section starts become anchors; remaining cuts are spread evenly between anchors."""
    anchors = {0: 0.0, n: total}
    for st in sorted(section_starts):
        if not 0 < st < total:
            continue
        free = [k for k in range(1, n) if k not in anchors]
        if not free:
            break
        k = min(free, key=lambda k: abs(k * total / n - st))
        anchors[k] = st
    idx = sorted(anchors)
    # drop anchors that would break ordering
    ok = [idx[0]]
    for k in idx[1:]:
        if anchors[k] > anchors[ok[-1]]:
            ok.append(k)
    cuts = [0.0] * (n + 1)
    for a, b in zip(ok, ok[1:]):
        for k in range(a, b + 1):
            cuts[k] = anchors[a] + (anchors[b] - anchors[a]) * (k - a) / (b - a)
    return [round(c, 2) for c in cuts]


def pick_duration(span, allowed, lo, hi):
    if allowed:  # model only accepts fixed lengths: smallest that covers the slot, else the longest
        return next((d for d in allowed if d >= span), allowed[-1])
    return round(min(max(span, lo), hi), 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("audio"); p.add_argument("--shots", type=int, default=12)
    p.add_argument("--min", type=float, default=5); p.add_argument("--max", type=float, default=10)
    p.add_argument("--allowed", help="comma list of durations the video node accepts, e.g. 6,10")
    p.add_argument("--sections", help="JSON [{name,start}] to align cuts to song sections")
    p.add_argument("-o", "--out", default="plan.json")
    a = p.parse_args()
    if a.shots < 1:
        sys.exit("--shots must be >= 1")
    allowed = sorted(float(x) for x in a.allowed.split(",")) if a.allowed else None
    total = probe_duration(a.audio)
    starts = [s["start"] for s in json.load(open(a.sections))] if a.sections else []
    cuts = make_cuts(total, a.shots, starts)
    shots, longest = [], (allowed[-1] if allowed else a.max)
    for i in range(a.shots):
        span = round(cuts[i + 1] - cuts[i], 2)
        d = pick_duration(span, allowed, a.min, a.max)
        if span > longest:
            print(f"WARNING shot {i+1}: slot {span}s > max clip {longest}s; "
                  f"last frame will be held. Raise --shots.", file=sys.stderr)
        shots.append({"index": i + 1, "start": cuts[i], "end": cuts[i + 1], "span": span,
                      "duration": int(d) if float(d).is_integer() else d,
                      "prompt": "", "seed": 1000 + i + 1})
    json.dump({"audio": a.audio, "total": round(total, 2), "shots": shots},
              open(a.out, "w"), indent=2, ensure_ascii=False)
    print(f"{total:.1f}s song -> {a.shots} shots, wrote {a.out}")


if __name__ == "__main__":
    main()
