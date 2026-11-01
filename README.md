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

## claude-account-switch

不重開視窗、不丟上下文,把正在跑的 Claude Code 換成另一個登入帳號(以軟鏈 `~/.claude/.credentials.json` 原子切換),並逐個進程驗證是否真的切換。

安裝:把 `claude-account-switch/` 複製到 `~/.claude/skills/`。注意:啟動時帶了 `CLAUDE_CONFIG_DIR` 的進程無法熱切,只能重開。
