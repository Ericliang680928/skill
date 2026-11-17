# skill

Claude Code skills.

## comfyui-music-video

給 Claude Code 一首歌、一張主唱圖和 ComfyUI 網址,它會規劃 12 段分鏡與秒數、分離人聲、透過 ComfyUI API 送出 MiniMax H3 影片工作流,最後合併成配上原曲的 MV。

### 事前準備(只做一次)
1. 安裝 `python3`、`ffmpeg`(含 `ffprobe`);要自行分離人聲再裝 `pip install demucs`。
2. 把 `comfyui-music-video/` 複製到 `~/.claude/skills/`(全域)或 `<專案>/.claude/skills/`。
3. 啟動 ComfyUI(預設 `http://127.0.0.1:8188`),並裝好 MiniMax Hailuo / H3 影片節點(可能需登入或點數)。
4. 請在**你自己的電腦**執行 Claude Code。雲端環境連不到你的 `127.0.0.1`;若 ComfyUI 在遠端,用它的公開網址(並注意存取保護)。

### 使用
1. 建一個資料夾,放入歌曲(mp3/wav)與主唱圖(png/jpg),在該資料夾執行 `claude`。
2. 下指令,例如:

   > 用 comfyui-music-video 幫我做 MV。音樂是 `PeachOnTheSill.mp3`,主唱圖是 `singer.png`,ComfyUI 網址是 `http://127.0.0.1:8188`。風格:復古拍立得、夏日、溫暖。

   可補充歌詞、段落時間、分鏡數(預設 12)。
3. Claude 會:檢查連線與節點 → 切段 → 寫分鏡提示詞(請你確認)→ 分離人聲 → 建 workflow → 先試跑第 1 段 → 全部送出 → 合併 `mv.mp4`。

### 事後調整
直接說:「第 5、7 段重跑,鏡頭改慢慢推近」、「角色外貌描述再具體一點」。只會重跑指定分鏡並重新合併。

### 輸出
`plan.json`(分鏡與提示詞)、`clips/`(各段影片)、`mv.mp4`(成品)。

### 注意
- 先試跑 1 段再全部送出,避免白花點數。
- 尚未對真實 ComfyUI / H3 節點實測,首次建立 workflow 可能需要來回調整;可先用 `--dry-run` 檢查。
- 成品不保證完美,可調提示詞、seed、秒數。

### 手動指令(進階)
```
python3 comfyui-music-video/scripts/comfy_client.py --url URL check
python3 comfyui-music-video/scripts/plan_segments.py song.mp3 --shots 12 [--allowed 6,10] -o plan.json
python3 comfyui-music-video/scripts/comfy_client.py --url URL fanout workflow_template.json plan.json --image singer.png --audio vocals.wav --wait --out clips/
python3 comfyui-music-video/scripts/assemble.py clips/ --audio song.mp3 --plan plan.json -o mv.mp4
```

## codex-image-handoff

Claude 寫「交接清單」，派 Codex（用你的 ChatGPT 帳號）畫圖，畫完存進共用資料夾；Claude 等 Codex 交件後照清單檢查、去背、裁切、歸檔，最後跳通知。不用再在兩個 AI 之間複製貼上。

### 事前準備（只做一次，在你自己的電腦）
1. 把 `codex-image-handoff/` 複製到 `~/.claude/skills/`。
2. 在 Claude 桌面版「Code」分頁說：「幫我裝好 Codex，用我的 ChatGPT 帳號登入」。（= `npm install -g @openai/codex` + `codex login`，在跳出的網頁登入）
3. `pip install pillow`；想要更乾淨的去背再裝 `pip install "rembg[cpu]"`（選用）。

### 使用
1. 講需求，最後加一句：「用 codex-image-handoff 寫成給另一個 AI 照著執行的交接清單」。Claude 會先問你不確定的設定（例如眼鏡黑框還金框），再以 `templates/handoff_template.md` 為底寫好清單與開工指令。
2. 貼上開工指令（範本見 `templates/kickoff_prompt.md`）：
   > 開工 版面互動素材：用 codex-image-handoff skill，讀「KT火柴人與黑糖_動畫角色/版面互動素材_生圖與後製指令.md」並照做……全部完成後跳 Mac 通知給我，並回報結果。
3. 之後想多畫一批：在清單裡加一列，再說一次「照做」。

### 流程
開工前檢查（Codex 試畫一張）→ 每批 `codex exec` 背景執行並等待 → 確認檔案到位（存檔失敗自動換可寫入模式重跑）→ Claude 逐張看圖 QC，不合格重畫一次、還不行就停下回報 → 去背／裁切／命名到 `final/` → 系統通知。

### 手動指令（進階）
```
python3 codex-image-handoff/scripts/dispatch.py preflight --workdir 專案
python3 codex-image-handoff/scripts/dispatch.py list --handoff 清單.md
python3 codex-image-handoff/scripts/dispatch.py run --handoff 清單.md --batch 1 [--only a.png --note "眼鏡改黑框"]
python3 codex-image-handoff/scripts/postprocess.py inspect raw/ [--palette "#000000,#ffffff"]
python3 codex-image-handoff/scripts/postprocess.py process raw/ --out final/ --trim --pad 16
python3 codex-image-handoff/scripts/notify.py "素材完成" "32 件"
```

### 注意
- Codex 必須在你的電腦上執行並登入；雲端環境做不到。
- 已用模擬的 codex 測過派工、重跑、去背流程；真實 Codex 的生圖能力依你的方案與版本而定，所以第一步一定先跑開工前檢查。
