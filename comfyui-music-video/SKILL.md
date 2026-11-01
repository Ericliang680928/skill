---
name: comfyui-music-video
description: Turn a song plus a singer's reference image into a music video via a running ComfyUI server (MiniMax Hailuo / H3 video nodes). Plans 12 storyboard shots with per-shot durations, separates vocals from the music, builds and submits the ComfyUI workflow through its HTTP API, then stitches the clips with the original audio. Use when the user gives an audio file + singer image + ComfyUI URL, or asks for an MV / 音樂影片 / 分鏡 workflow in ComfyUI.
---

# ComfyUI Music Video (MiniMax H3)

Inputs the user supplies: **audio file**, **singer image**, **ComfyUI API URL** (e.g. `http://127.0.0.1:8188`). Optional: song name, style notes, lyrics, shot count (default 12).

All helper scripts are in `scripts/` (Python 3 stdlib only; `ffmpeg`/`ffprobe` required for planning and assembly).

## Pipeline

1. **Check server** – `python3 scripts/comfy_client.py --url URL check`. Stop and tell the user if unreachable.
2. **Discover nodes** – never guess node names. Run `comfy_client.py --url URL nodes minimax` (also try `hailuo`, `video`, `demucs`, `separat`, `LoadAudio`, `LoadImage`, `SaveVideo`) and read inputs with `nodes --detail <ClassName>`. If no MiniMax/H3 node exists, tell the user which custom node / API node they must install; do not fake one.
3. **Analyse the song** – `python3 scripts/plan_segments.py AUDIO --shots 12 --min 5 --max 10 -o plan.json` gives total length and per-shot start/duration. Check the per-shot limits against the node's allowed durations (from step 2) and adjust `--min/--max`. Listen-free structure hints: if the user gave lyrics/sections, pass `--sections sections.json` (`[{"name":"verse1","start":0},…]`) so cuts land on section boundaries.
4. **Write storyboard** – fill `shots[i].prompt` in `plan.json`: 12 prompts, each = subject (the singer, described consistently from the image) + action + camera move + lighting/setting + mood matching that section of the song. Keep character description identical across shots for consistency. Show the storyboard to the user before spending credits unless they said to just run.
5. **Separate vocals** – prefer a ComfyUI demucs/separation node found in step 2 (feed the vocal stem to any lip-sync / audio-driven input). Otherwise: `python3 scripts/separate_vocals.py AUDIO -o stems/` (uses `demucs` if installed, else tells the user how to install it).
6. **Build a one-shot template** – assemble an *API-format* workflow JSON (`workflow_template.json`) for a single shot using the nodes from step 2, with these placeholders inside string values: `{{image}}` (uploaded image name), `{{audio}}` (uploaded vocal stem name), `{{prompt}}`, `{{duration}}`, `{{seed}}`, `{{index}}`, `{{prefix}}` (output filename prefix). Make sure each shot has its own SaveVideo/output node.
7. **Upload + fan out** – `comfy_client.py --url URL upload IMAGE` and `upload STEM`, then
   `comfy_client.py --url URL fanout workflow_template.json plan.json --image NAME --audio NAME --wait --out clips/`
   This queues one job per shot, polls `/history`, and downloads the outputs. Start with `--only 1` as a smoke test.
8. **Assemble** – `python3 scripts/assemble.py clips/ --audio AUDIO -o mv.mp4` concatenates clips in order, trims/pads to the song length, and muxes the **original** full mix.
9. **Report** – give the user the output path, the storyboard, and anything imperfect (shots that failed, drift in character look). Offer to regenerate single shots: `fanout … --only 5,7` with a revised prompt/seed.

## Rules
- Ask before running anything that costs API credits for more than the smoke-test shot if the user did not say to proceed.
- Never put API keys in files you commit.
- Failed shots: report the ComfyUI error text verbatim, then retry once with a new seed.
- Quality is "good, not perfect" – tell the user which knobs (prompt, seed, duration) to tweak rather than promising perfection.
