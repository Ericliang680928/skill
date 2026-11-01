#!/usr/bin/env python3
"""Concatenate shot clips in order and mux the original audio -> final MV."""
import argparse, glob, os, re, subprocess, sys, tempfile

p = argparse.ArgumentParser()
p.add_argument("clips_dir"); p.add_argument("--audio", required=True)
p.add_argument("-o", "--out", default="mv.mp4")
a = p.parse_args()
clips = sorted(glob.glob(os.path.join(a.clips_dir, "shot*.mp4")) + glob.glob(os.path.join(a.clips_dir, "shot*.webm")),
               key=lambda f: int(re.search(r"shot(\d+)", os.path.basename(f)).group(1)))
if not clips:
    sys.exit("no shotNN_* clips found")
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as lst:
    for c in clips:
        lst.write(f"file '{os.path.abspath(c)}'\n")
# re-encode so clips with different codecs/params concat cleanly; drop clip audio, use original song
subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst.name, "-i", a.audio,
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", a.out], check=True)
print("wrote", a.out)
