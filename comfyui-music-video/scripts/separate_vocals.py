#!/usr/bin/env python3
"""Separate vocals from music with demucs (two-stem). Outputs vocals.* and no_vocals.*"""
import argparse, glob, os, shutil, subprocess, sys

p = argparse.ArgumentParser()
p.add_argument("audio"); p.add_argument("-o", "--out", default="stems")
a = p.parse_args()
if not shutil.which("demucs"):
    sys.exit("demucs not found. Install: pip install demucs   (or use a separation node inside ComfyUI)")
subprocess.run(["demucs", "--two-stems=vocals", "-o", a.out, a.audio], check=True)
name = os.path.splitext(os.path.basename(a.audio))[0]
for f in glob.glob(os.path.join(a.out, "*", name, "*")):
    dst = os.path.join(a.out, os.path.basename(f))
    shutil.copy(f, dst)
    print(dst)
