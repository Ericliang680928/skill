#!/usr/bin/env python3
"""Dispatch image batches from a handoff checklist to OpenAI Codex CLI and wait for the files.

Subcommands:
  preflight  --workdir DIR                      Codex draws one test image; verifies the file appears.
  list       --handoff MD                       Show batches, expected output files and reference images.
  run        --handoff MD --batch N --workdir DIR [--only a.png,b.png] [--note TEXT] [--timeout S]

Conventions read from the handoff markdown:
  * A batch is a heading like "## 批次 1：..." or "## Batch 1: ...".
  * Inside a batch, backticked image paths under --out-dir (default "raw/") are expected outputs;
    other backticked image paths that exist on disk are reference images to attach.

Exit codes: 0 all expected files present, 1 some missing, 2 usage / codex not found, 3 preflight failed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
BATCH_RE = re.compile(r"^#{2,3}\s*(?:批次|Batch)\s*(\d+)\s*[:：]?\s*(.*)$", re.I)
TICK_RE = re.compile(r"`([^`\s]+)`")
WRITE_ERR_RE = re.compile(
    r"read-only|permission denied|operation not permitted|EACCES|EROFS|sandbox.*(denied|blocked)|not allowed to write",
    re.I,
)


def die(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def codex_bin():
    b = shutil.which("codex")
    if not b:
        die("找不到 codex 指令。安裝：npm install -g @openai/codex（或 macOS: brew install --cask codex），再執行 codex login。")
    return b


def parse_batches(md_path, out_dir="raw/"):
    text = Path(md_path).read_text(encoding="utf-8")
    base = Path(md_path).resolve().parent
    out_prefix = out_dir.rstrip("/") + "/"
    batches, cur = {}, None
    for line in text.splitlines():
        m = BATCH_RE.match(line.strip())
        if m:
            cur = int(m.group(1))
            batches[cur] = {"n": cur, "title": m.group(2).strip(), "outputs": [], "refs": [], "text": [line]}
            continue
        if cur is not None and re.match(r"^#{1,2}\s", line) and not BATCH_RE.match(line.strip()):
            cur = None  # a non-batch heading of the same or higher level ends the batch
            continue
        if cur is None:
            continue
        b = batches[cur]
        b["text"].append(line)
        for tok in TICK_RE.findall(line):
            if not tok.lower().endswith(IMG_EXT):
                continue
            norm = tok.lstrip("./")
            if norm.startswith(out_prefix):
                if norm not in b["outputs"]:
                    b["outputs"].append(norm)
            elif norm not in b["refs"]:
                b["refs"].append(norm)
    for b in batches.values():
        b["text"] = "\n".join(b["text"]).strip()
        # keep refs that exist relative to the handoff file
        b["refs"] = [r for r in b["refs"] if (base / r).exists()]
    return batches


def valid_image(p):
    try:
        from PIL import Image
        with Image.open(p) as im:
            im.verify()
        return True
    except ImportError:
        return p.stat().st_size > 1000
    except Exception:
        return False


def check_outputs(workdir, outputs, since=None):
    ok, missing, bad, stale = [], [], [], []
    for o in outputs:
        p = Path(workdir) / o
        if not p.exists():
            missing.append(o)
        elif not valid_image(p):
            bad.append(o)
        elif since and p.stat().st_mtime < since:
            stale.append(o)
        else:
            ok.append(o)
    return ok, missing, bad, stale


def run_codex(prompt, workdir, images, log_path, last_path, timeout, extra_args, add_dir=None):
    cmd = [codex_bin(), "exec", "--sandbox", "workspace-write", "--skip-git-repo-check",
           "-C", str(workdir), "-o", str(last_path)]
    if add_dir:
        cmd += ["--add-dir", str(add_dir)]
    for img in images:
        cmd += ["-i", str(img)]
    cmd += extra_args
    cmd.append(prompt)
    print("▶ " + " ".join(c if len(c) < 80 else c[:77] + "..." for c in cmd), flush=True)
    t0 = time.time()
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n===== {time.ctime()} =====\n$ {' '.join(cmd[:-1])} <prompt>\n")
        log.flush()
        try:
            r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout,
                               stdin=subprocess.DEVNULL)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n[dispatch] TIMEOUT after {timeout}s\n")
            rc = 124
    print(f"  codex exit {rc} in {time.time() - t0:.0f}s", flush=True)
    return rc


def tail(path, n=40):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except FileNotFoundError:
        return ""


def build_prompt(md_rel, batch, only, note, out_dir):
    targets = only or batch["outputs"]
    lines = [
        f"讀「{md_rel}」這份交接清單，完整讀完後照做。",
        f"這次**只執行「批次 {batch['n']}」**，其他批次不要做。",
        "先做清單裡的「開工前檢查」；畫圖功能不能用或無法寫檔，就在最後訊息寫 PREFLIGHT_FAIL: 原因 並停止。",
        f"必須產生以下檔案（路徑相對於目前工作資料夾，資料夾不存在就建立 {out_dir}）：",
        *[f"- {t}" for t in targets],
        "每張圖照清單的「畫完怎麼檢查」自我檢查，不合格重畫一次；還是不合格就保留最後一版並在最後訊息說明。",
        "只寫入上述檔案，不要修改其他任何檔案。附上的圖片是參考圖。",
        "最後一則訊息照清單「完成時」的格式回報。",
    ]
    if only:
        lines.insert(2, "這是重畫：只重畫上面列出的檔案，覆蓋舊檔。")
    if note:
        lines.append(f"本次特別注意：{note}")
    return "\n".join(lines)


def cmd_list(a):
    batches = parse_batches(a.handoff, a.out_dir)
    if not batches:
        die("清單裡找不到「## 批次 N」標題。")
    total = 0
    for n in sorted(batches):
        b = batches[n]
        total += len(b["outputs"])
        print(f"批次 {n}：{b['title']}  ({len(b['outputs'])} 張)")
        for o in b["outputs"]:
            print(f"   → {o}")
        if b["refs"]:
            print(f"   參考圖：{', '.join(b['refs'])}")
    print(f"共 {len(batches)} 批、{total} 張")
    if a.json:
        print(json.dumps({n: {k: v for k, v in b.items() if k != 'text'} for n, b in batches.items()},
                         ensure_ascii=False, indent=2))


def cmd_preflight(a):
    wd = Path(a.workdir).resolve()
    hd = wd / ".handoff"
    hd.mkdir(parents=True, exist_ok=True)
    target = hd / "preflight.png"
    if target.exists():
        target.unlink()
    v = subprocess.run([codex_bin(), "--version"], capture_output=True, text=True)
    print("codex:", (v.stdout or v.stderr).strip())
    prompt = ("開工前檢查：用你的畫圖（生圖）功能畫一張 256x256 左右的簡單圖：白底上一個紅色圓形。"
              f"存成 .handoff/preflight.png。畫圖功能不能用或無法寫檔，就回覆 PREFLIGHT_FAIL: 原因。")
    rc = run_codex(prompt, wd, [], hd / "preflight.log", hd / "preflight.last.txt", a.timeout, a.codex_args)
    last = tail(hd / "preflight.last.txt", 10)
    if target.exists() and valid_image(target):
        print(f"✅ PREFLIGHT OK：Codex 能畫圖並寫入 {target}")
        return
    print("❌ PREFLIGHT FAIL：Codex 沒有產生測試圖。")
    print("Codex 最後訊息：\n" + (last or "(無)"))
    print("log 尾端：\n" + tail(hd / "preflight.log", 25))
    if rc != 0 and "login" in tail(hd / "preflight.log", 80).lower():
        print("看起來尚未登入：請執行 codex login。")
    sys.exit(3)


def cmd_run(a):
    md = Path(a.handoff).resolve()
    wd = Path(a.workdir).resolve() if a.workdir else md.parent
    batches = parse_batches(md, a.out_dir)
    if a.batch not in batches:
        die(f"找不到批次 {a.batch}；有的批次：{sorted(batches)}")
    b = batches[a.batch]
    if not b["outputs"]:
        die(f"批次 {a.batch} 沒有列出任何 `{a.out_dir}...png` 輸出檔名。")
    only = None
    if a.only:
        wanted = [x.strip() for x in a.only.split(",") if x.strip()]
        only = [o for o in b["outputs"] if o in wanted or Path(o).name in wanted]
        if not only:
            die(f"--only 的檔名不在批次 {a.batch} 裡：{wanted}")
    targets = only or b["outputs"]
    (wd / a.out_dir).mkdir(parents=True, exist_ok=True)
    hd = wd / ".handoff"
    hd.mkdir(exist_ok=True)
    log_path, last_path = hd / f"batch_{a.batch}.log", hd / f"batch_{a.batch}.last.txt"
    try:
        md_rel = os.path.relpath(md, wd)
    except ValueError:
        md_rel = str(md)
    refs = [md.parent / r for r in b["refs"]]
    prompt = build_prompt(md_rel, b, only, a.note, a.out_dir)
    started = time.time() - 1 if only else None  # redraws must produce fresh files

    rc = run_codex(prompt, wd, refs, log_path, last_path, a.timeout, a.codex_args)
    ok, missing, bad, stale = check_outputs(wd, targets, started)

    if (missing or bad) and WRITE_ERR_RE.search(tail(log_path, 200)):
        print("  偵測到寫檔/沙盒錯誤 → 以「可寫入工作資料夾」模式重跑缺少的檔案", flush=True)
        retry = [o for o in targets if o in missing or o in bad]
        prompt2 = build_prompt(md_rel, b, retry, a.note, a.out_dir)
        rc = run_codex(prompt2, wd, refs, log_path, last_path, a.timeout, a.codex_args,
                       add_dir=wd / a.out_dir)
        ok, missing, bad, stale = check_outputs(wd, targets, started)

    last = tail(last_path, 60)
    report = {"batch": a.batch, "title": b["title"], "codex_exit": rc, "ok": ok, "missing": missing,
              "invalid": bad, "not_updated": stale, "codex_last_message": last,
              "preflight_fail": "PREFLIGHT_FAIL" in last}
    (hd / f"batch_{a.batch}.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    print(f"\n批次 {a.batch}：{len(ok)}/{len(targets)} 張到位")
    for o in ok:
        print(f"  ✅ {o}")
    for o in missing:
        print(f"  ❌ 缺檔 {o}")
    for o in bad:
        print(f"  ❌ 壞檔 {o}")
    for o in stale:
        print(f"  ⚠️  未更新（仍是舊檔）{o}")
    if last:
        print("\nCodex 最後訊息：\n" + last)
    if report["preflight_fail"]:
        print("\nCodex 回報 PREFLIGHT_FAIL：停止，請把原因告訴使用者。")
        sys.exit(3)
    if missing or bad or stale:
        print(f"\nlog：{log_path}\n" + tail(log_path, 20))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--out-dir", default="raw/", help="Codex 輸出資料夾（相對 workdir），預設 raw/")
        p.add_argument("--timeout", type=int, default=1800, help="每次 codex exec 的逾時秒數")
        p.add_argument("--codex-args", nargs=argparse.REMAINDER, default=[],
                       help="其餘參數原樣傳給 codex exec（放在最後），例如 --codex-args -m gpt-5")

    p = sub.add_parser("preflight")
    p.add_argument("--workdir", default=".")
    common(p)
    p = sub.add_parser("list")
    p.add_argument("--handoff", required=True)
    p.add_argument("--json", action="store_true")
    common(p)
    p = sub.add_parser("run")
    p.add_argument("--handoff", required=True)
    p.add_argument("--batch", type=int, required=True)
    p.add_argument("--workdir", help="Codex 的工作資料夾，預設為清單所在資料夾")
    p.add_argument("--only", help="只重畫這些檔名（逗號分隔）")
    p.add_argument("--note", help="這次額外交代的修正重點")
    common(p)
    a = ap.parse_args()
    {"preflight": cmd_preflight, "list": cmd_list, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
