---
name: codex-image-handoff
description: Let Claude Code delegate image generation to OpenAI Codex (ChatGPT) without copy-pasting. Claude writes a handoff checklist (交接清單) for another AI, dispatches each batch to `codex exec` in the background, waits for Codex to save the images into a shared folder, then QC-checks them against the checklist, removes backgrounds, trims, renames and archives, and finally sends a desktop notification. Use when the user wants ChatGPT/Codex to draw while Claude does the rest, mentions 交接清單 / 給另一個 AI 照著執行 / 叫 Codex 畫圖 / 不想再複製貼上, or asks for a batch of character poses, expressions, props or stickers drawn for an existing character IP.
---

# Codex Image Handoff (Claude 派工、Codex 畫圖、共用資料夾交件)

**How the two AIs talk:** Claude starts Codex with one command and waits for it to finish. When the command returns, Codex is done. Both sides read and write the same folder. Nothing else is needed: no bridge program, no MCP server, no copy-pasting.

```
user ──需求──▶ Claude ──寫──▶ handoff.md (交接清單)
                 │
                 ├─ codex exec "讀 handoff.md，只做第 N 批" ──▶ Codex 畫圖 ──存檔──▶ raw/
                 │        (Claude 等指令結束 = Codex 交件)
                 ├─ 檢查 raw/ 檔案 → 照清單 QC → 不合格重派一次 → 還不行就停下回報
                 └─ 去背 / 裁切 / 命名 / 歸檔 final/ → 系統通知 → 回報結果
```

Scripts in `scripts/` (Python 3 + Pillow; `rembg` optional for background removal). Templates in `templates/`.

## 0. Setup (first time only, on the user's own computer)

Codex must run on the user's machine, logged in with **their** ChatGPT account. A cloud sandbox cannot do this; say so if you are not on their machine.

1. `codex --version`. If it is missing: `npm install -g @openai/codex` (needs Node 18+), or on macOS `brew install --cask codex`.
2. `codex login status`. If not logged in, run `codex login`: a browser page opens and the user signs in with ChatGPT. Wait for them; never ask for passwords or API keys in chat.
3. `python3 scripts/dispatch.py preflight --workdir <project>`: asks Codex to draw one small test image and checks that the file actually appears. If it fails, **stop and tell the user** (image generation may be unavailable on their plan or Codex version). Do not continue with anything else.

## 1. Write the handoff checklist

Copy `templates/handoff_template.md` into the project, e.g. `<角色>/<主題>_生圖與後製指令.md`, and fill it in from the user's request. It is written **for another AI**, like handing work to a colleague. It must contain:

- **先確認的事 (Confirm first):** any visual fact you are not sure of (e.g. glasses black or gold frame, hair parting, colour of a prop). **Ask the user these questions now**, record the answers in the file, and only then dispatch. Codex runs non-interactively and cannot ask.
- **開工前檢查 (Preflight):** the image tool works and the output folder is writable; otherwise stop and report.
- **角色設定 (Character sheet):** fixed traits plus paths to reference images.
- **批次 (Batches):** `## 批次 N：標題` sections. Each item gives pose / expression / prop, the reference image to follow, and an exact output filename in backticks (`` `raw/b1_kt_wave.png` ``). `dispatch.py` reads these backticked filenames to know what to expect. Keep each batch to 4–8 images.
- **畫完怎麼檢查 (QC list):** concrete yes/no checks (glasses correct, hairstyle correct, no stray colours on 黑糖, **no text or watermark**, plain or transparent background, full body not cropped).
- **不合格怎麼辦 (On failure):** redraw once; if it still fails, stop and write the reason into the batch report.
- **檔案放哪、怎麼命名 (Files):** `raw/` for Codex output, `final/` for processed output, naming rule, size and format.

If the user wants AI to decide "what image goes here", read their script, storyboard or layout first, propose the list of images as batches, and get a yes before dispatching.

## 2. Kickoff

Write `templates/kickoff_prompt.md` (filled in) for the user, so that next time they can paste one line into Claude Code: "開工 <主題>：讀「<path>.md」並照做…". When you receive that line, run steps 3–6.

## 3. Dispatch each batch to Codex

```
python3 scripts/dispatch.py list   --handoff <md>                    # batches + expected files
python3 scripts/dispatch.py run    --handoff <md> --batch 1 --workdir <project> --timeout 1800
```

- Run each batch **in the background or with the longest Bash timeout** (image batches take minutes). Wait for it to exit; do not poll in a busy loop.
- `run` calls `codex exec` in `--sandbox workspace-write` mode inside `--workdir`, attaches the reference images listed in the batch, and asks Codex to work **only on that batch**. It then checks that every expected file exists and is a valid image.
- If files are missing and the log shows a write or sandbox error, `run` automatically retries once in a mode with an extra writable directory (`--add-dir`). If it still fails, report the log tail. Do not use `--dangerously-bypass-approvals-and-sandbox` unless the user explicitly agrees.
- Batch logs go to `<workdir>/.handoff/batch_N.log`; Codex's final message goes to `.handoff/batch_N.last.txt`.
- Re-run only some files: `--only b1_kt_wave.png,b1_kt_jump.png` (Codex is told to redraw just those).

## 4. QC (Claude does this, by looking)

Open **every** image with the Read tool and go through the QC list in the handoff file item by item. Also run `python3 scripts/postprocess.py inspect raw/` for objective checks (size, alpha, near-white background, unexpected colours if `--palette` is given).
- Failed item → `dispatch.py run … --only <files>` with a short `--note "眼鏡要黑框，不要金框"`. **Max one redraw per file.**
- Still failing → do not loop; mark it ❌ and report it with the reason.

## 5. Post-process and archive

```
python3 scripts/postprocess.py process raw/ --out final/ [--remove-bg auto|rembg|white|none] [--trim] [--pad 16] [--max-size 2048] [--rename-map map.json]
```
- `auto` keeps images that already have transparency, otherwise uses `rembg` if installed, else flood-fills a near-white background from the corners.
- After processing, open a few results to confirm edges are clean (white fringes around hair or glasses are a common defect).
- Write `final/manifest.json` (the script does this) and summarise.

## 6. Notify and report

`python3 scripts/notify.py "素材完成" "32 件完成，2 件需人工確認"` (macOS notification; prints to stdout elsewhere). Then report to the user: counts per batch, ✅/❌ list with reasons, output folder, and what to edit in the checklist to run another batch ("改清單裡的一行，再說一次『照做』").

## Rules
- Never put API keys or passwords in files. Login is Codex's own browser flow.
- Ask the 先確認的事 questions before dispatching. Never guess a character trait.
- One redraw per failed file, then stop and report. Do not burn the user's quota in loops.
- Preflight failure means stop. Do not fake images or draw them yourself as a substitute.
- Do not overwrite the user's existing reference images; Codex writes only to `raw/`.
