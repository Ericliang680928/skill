#!/usr/bin/env python3
"""Join shot clips and mux the original audio -> final MV.

With --plan, each clip is trimmed / last-frame-held to its slot and missing shots become black,
so picture stays in sync with the song. The output always runs the full length of the audio.
"""
import argparse, glob, json, os, re, subprocess, sys

FPS = 30


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"] + (["-select_streams", stream] if stream else []) + \
          ["-show_entries", entries, "-of", "csv=p=0", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffprobe failed on {path}: {r.stderr}")
    return r.stdout.strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("clips_dir"); p.add_argument("--audio", required=True)
    p.add_argument("--plan", help="plan.json from plan_segments.py (recommended)")
    p.add_argument("-o", "--out", default="mv.mp4")
    a = p.parse_args()

    found = {}
    for f in sorted(glob.glob(os.path.join(a.clips_dir, "shot*"))):
        m = re.match(r"shot(\d+)_.*\.(mp4|webm|mov|mkv)$", os.path.basename(f), re.I)
        if m:
            found[int(m.group(1))] = f  # duplicates per shot: last (sorted) wins
    if not found:
        sys.exit(f"no shotNN_*.mp4/webm clips in {a.clips_dir}")
    audio_len = float(probe(a.audio, "format=duration"))
    w, h = probe(found[min(found)], "stream=width,height", "v:0").split(",")[:2]

    if a.plan:
        plan = json.load(open(a.plan))["shots"]
        slots = [(s["index"], s["span"]) for s in plan]
        missing = [i for i, _ in slots if i not in found]
        if missing:
            print(f"WARNING: missing shots {missing} -> black filler", file=sys.stderr)
    else:
        slots = [(i, None) for i in sorted(found)]

    inputs, chains = [], []
    for n, (i, span) in enumerate(slots):
        if i in found:
            inputs += ["-i", found[i]]
            f = (f"[{n}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                 f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}")
            if span:
                f += f",tpad=stop_mode=clone:stop_duration={span},trim=duration={span}"
            chains.append(f + f",setpts=PTS-STARTPTS[v{n}]")
        else:
            inputs += ["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d={span}:r={FPS}"]
            chains.append(f"[{n}:v]format=yuv420p,setpts=PTS-STARTPTS[v{n}]")
    count = len(slots)
    inputs += ["-i", a.audio]
    graph = ";".join(chains) + ";" + "".join(f"[v{n}]" for n in range(count)) + \
        f"concat=n={count}:v=1:a=0,tpad=stop_mode=clone:stop_duration={audio_len},format=yuv420p[v]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph,
           "-map", "[v]", "-map", f"{count}:a:0", "-t", f"{audio_len}",
           "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    print(f"wrote {a.out} ({audio_len:.1f}s, {count - len([1 for i, _ in slots if i not in found])}/{count} shots)")


if __name__ == "__main__":
    main()
