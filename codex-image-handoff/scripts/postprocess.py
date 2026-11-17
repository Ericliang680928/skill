#!/usr/bin/env python3
"""Inspect and post-process images that Codex saved into the shared folder.

  inspect DIR [--palette "#000,#fff,#8b5a2b"] [--tol 60]
      Objective checks per image: size, transparency, background type, share of off-palette pixels.
      (Visual checks such as glasses, hairstyle or stray text are done by Claude looking at each image.)

  process DIR --out final/ [--remove-bg auto|rembg|white|none] [--trim] [--pad 16]
          [--max-size 2048] [--rename-map map.json] [--white-tol 18]
      Remove background → trim to content → pad → downscale → save PNG → write manifest.json.

Requires Pillow. `rembg` is optional (pip install "rembg[cpu]") and gives better edges than the
white flood-fill fallback.
"""
import argparse
import json
import shutil
import sys
from collections import deque
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 Pillow：pip install pillow")

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def images(d):
    return sorted(p for p in Path(d).iterdir() if p.suffix.lower() in IMG_EXT and not p.name.startswith("."))


def has_real_alpha(im):
    if im.mode not in ("RGBA", "LA") and "transparency" not in im.info:
        return False
    a = im.convert("RGBA").getchannel("A")
    lo, _ = a.getextrema()
    return lo < 250


def corner_bg(im):
    rgb = im.convert("RGB")
    w, h = rgb.size
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    cols = [rgb.getpixel(p) for p in pts]
    near_white = sum(1 for c in cols if min(c) >= 235)
    return "white" if near_white >= 6 else ("uniform" if max(max(abs(a - b) for a, b in zip(c, cols[0])) for c in cols) < 20 else "scene")


def hex2rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def off_palette_ratio(im, palette, tol):
    small = im.convert("RGBA")
    small.thumbnail((256, 256))
    n = off = 0
    data = small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()
    for r, g, b, a in data:
        if a < 128:
            continue
        if min(r, g, b) >= 235:  # background / highlights
            continue
        n += 1
        if min(((r - p[0]) ** 2 + (g - p[1]) ** 2 + (b - p[2]) ** 2) ** 0.5 for p in palette) > tol:
            off += 1
    return off / n if n else 0.0


def cmd_inspect(a):
    palette = [hex2rgb(x) for x in a.palette.split(",")] if a.palette else None
    rows = []
    for p in images(a.dir):
        with Image.open(p) as im:
            im.load()
            row = {"file": p.name, "size": f"{im.width}x{im.height}", "mode": im.mode,
                   "transparent": has_real_alpha(im), "background": corner_bg(im)}
            warn = []
            if max(im.size) < a.min_size:
                warn.append(f"長邊<{a.min_size}")
            if not row["transparent"] and row["background"] == "scene":
                warn.append("背景不是純色（可能畫了場景）")
            if palette:
                r = off_palette_ratio(im, palette, a.tol)
                row["off_palette"] = round(r, 3)
                if r > a.max_off:
                    warn.append(f"非指定色 {r:.0%}（檢查雜色）")
            row["warnings"] = warn
            rows.append(row)
    for r in rows:
        flag = "⚠️ " if r["warnings"] else "✅"
        extra = f" off={r['off_palette']}" if "off_palette" in r else ""
        print(f"{flag} {r['file']}: {r['size']} {r['mode']} bg={'透明' if r['transparent'] else r['background']}{extra}"
              + (f"  ← {'; '.join(r['warnings'])}" if r["warnings"] else ""))
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))


def remove_white(im, tol):
    """Flood-fill near-white pixels connected to the border and make them transparent."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    thr = 255 - tol
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0)); q.append((x, h - 1))
    for y in range(h):
        q.append((0, y)); q.append((w - 1, y))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        r, g, b, al = px[x, y]
        if al == 0 or min(r, g, b) >= thr:
            px[x, y] = (r, g, b, 0)
            if x > 0: q.append((x - 1, y))
            if x < w - 1: q.append((x + 1, y))
            if y > 0: q.append((x, y - 1))
            if y < h - 1: q.append((x, y + 1))
    return im


def remove_rembg(im):
    from rembg import remove  # type: ignore
    return remove(im.convert("RGBA"))


def cmd_process(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rename = json.loads(Path(a.rename_map).read_text(encoding="utf-8")) if a.rename_map else {}
    have_rembg = False
    if a.remove_bg in ("auto", "rembg"):
        try:
            import rembg  # noqa: F401
            have_rembg = True
        except ImportError:
            if a.remove_bg == "rembg":
                sys.exit('未安裝 rembg：pip install "rembg[cpu]"，或改用 --remove-bg white')
    manifest = []
    for p in images(a.dir):
        with Image.open(p) as im:
            im.load()
            src_mode = im.mode
            method = "none"
            if a.remove_bg != "none":
                if has_real_alpha(im):
                    method = "already-transparent"
                    im = im.convert("RGBA")
                elif a.remove_bg == "rembg" or (a.remove_bg == "auto" and have_rembg):
                    im, method = remove_rembg(im), "rembg"
                else:
                    im, method = remove_white(im, a.white_tol), "white-floodfill"
            im = im.convert("RGBA")
            if a.trim:
                bbox = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
                if bbox:
                    im = im.crop(bbox)
            if a.pad:
                canvas = Image.new("RGBA", (im.width + 2 * a.pad, im.height + 2 * a.pad), (0, 0, 0, 0))
                canvas.paste(im, (a.pad, a.pad))
                im = canvas
            if a.max_size and max(im.size) > a.max_size:
                im.thumbnail((a.max_size, a.max_size), Image.LANCZOS)
            name = rename.get(p.name, rename.get(p.stem, p.stem))
            name = Path(name).stem + ".png"
            dst = out / name
            im.save(dst, optimize=True)
            manifest.append({"src": str(p), "dst": str(dst), "size": f"{im.width}x{im.height}",
                             "src_mode": src_mode, "bg_removal": method})
            print(f"✅ {p.name} → {dst} ({im.width}x{im.height}, {method})")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(manifest)} 張 → {out}/manifest.json")
    if a.remove_bg == "auto" and not have_rembg and any(m["bg_removal"] == "white-floodfill" for m in manifest):
        print('提示：白底去背用的是簡易填色法；邊緣若有白邊，可安裝 rembg（pip install "rembg[cpu]"）後重跑。')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect")
    p.add_argument("dir")
    p.add_argument("--palette", help='允許的顏色，例如 "#000000,#ffffff,#3b2a1a"')
    p.add_argument("--tol", type=float, default=60, help="與允許色的最大 RGB 距離")
    p.add_argument("--max-off", type=float, default=0.03, help="非允許色比例超過此值就警告")
    p.add_argument("--min-size", type=int, default=1024)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("process")
    p.add_argument("dir")
    p.add_argument("--out", required=True)
    p.add_argument("--remove-bg", choices=["auto", "rembg", "white", "none"], default="auto")
    p.add_argument("--white-tol", type=int, default=18, help="白底判定容差（越大去越多）")
    p.add_argument("--trim", action="store_true")
    p.add_argument("--pad", type=int, default=0)
    p.add_argument("--max-size", type=int, default=0)
    p.add_argument("--rename-map", help='JSON：{"b1_kt_wave.png": "KT_揮手"}')
    a = ap.parse_args()
    {"inspect": cmd_inspect, "process": cmd_process}[a.cmd](a)


if __name__ == "__main__":
    main()
