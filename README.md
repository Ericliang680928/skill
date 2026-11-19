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

## second-brain

把零散的筆記、連結、逐字稿、想法、任務整理成存在檔案裡的知識庫,找出關聯、轉成下一步行動。所有寫入都先提案,你同意才存;你的回饋會累積成一份規則檔,下次照著做。

### 事前準備(只做一次)
1. 安裝 `python3`(輔助腳本只用標準函式庫)。
2. 把 `second-brain/` 複製到 `~/.claude/skills/`(全域)或 `<專案>/.claude/skills/`。
3. 選一個要放知識庫的資料夾(建議是 git repo,才有版本紀錄與備份),在該資料夾執行 `claude`。

### 使用
- 第一次:說「用 second-brain 建立我的第二大腦」。它會建立 `brain/`,並問你的目標、進行中專案、慣用工具、可用時間。
- 收件:貼上筆記、連結、逐字稿,說「幫我存到大腦」。它會列出存入提案,你同意後才寫入。
- 查詢:「你存了什麼關於 X」「把這幾則筆記轉成下週的待辦」。
- 回饋:直接說哪裡要改。它會提議寫成一條規則,先試行,之後由你決定保留或撤回。
- 回顧:說「週回顧」,清理收件箱、更新任務狀態、檢視試行中的規則。

### 知識庫結構
`brain/` 下有 `rules.md`(規則檔)、`profile.md`(你的目標與偏好)、`index.md`(筆記總表)、`changelog.md`(變更紀錄)、`sources/`(原文)、以及 `0-inbox`、`1-projects`、`2-areas`、`3-resources`、`4-archive` 五個資料夾。

### 注意
- 記憶就是這些檔案。沒寫進檔案的內容,下一次對話不會存在;在雲端環境使用時要 commit 並 push 才會保留。
- 「會變好」指的是規則檔累積你的回饋,模型本身不會改變。
- 帳號密碼與金鑰不會被存入。

### 手動指令(進階)
```
python3 second-brain/scripts/brain.py init  [--dir brain]
python3 second-brain/scripts/brain.py check [--dir brain] [--stale 7]
```
