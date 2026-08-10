# auto_video — YouTube 留言影片自動化流程

輸入一批 YouTube `videoId`(使用者自有素材影片),自動完成:

```
下載影片 → 抓留言 → 篩選留言 → 翻譯留言 → 下載頭像 → 產生留言卡片圖 → 合成到影片 → 正規化音量 → 批次輸出
```

輸出固定 1080x1920(9:16)短影片:上方黑底標題、來源影片置中裁切成正方形、下方連續播放仿 YouTube 留言卡片樣式的圖片(黑底、頭像、帳號、時間、內文、讚數)。留言連續播放、每則固定秒數,依影片長度自動算出剛好播完的則數。

下載影片的部分參考了姊妹專案 VideoSubtitler 的 yt-dlp 下載邏輯(重試/剪輯區間下載)。

## 環境需求

- Windows + Python 3.10 以上
- [ffmpeg](https://github.com/BtbN/FFmpeg-Builds/releases):下載 `ffmpeg-master-latest-win64-gpl-shared.zip`,解壓後整個資料夾放到 `tools/` 下,使 `tools/ffmpeg-*/bin/ffmpeg.exe` 存在;或直接安裝到系統並加入 PATH
- YouTube 下載需要 JS runtime(建議裝 [Deno](https://deno.com/):`winget install DenoLand.Deno`),沒裝也能跑,少數影片可能失敗

## 安裝

```powershell
py -3.12 -m venv .venv   # 沒有 3.12 的話用你本機有的 3.10 以上版本即可
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
```

## 設定金鑰

把 `.env.example` 複製一份成 `.env`(放在專案根目錄,跟 `main.py` 同一層),填入你的金鑰。
`main.py` 和 `webui/app.py` 啟動時都會自動讀取這個 `.env` 檔,不需要額外在終端機下 `$env:` 設定。

```powershell
copy .env.example .env
notepad .env
```

- **YOUTUBE_API_KEY**(必要):到 [Google Cloud Console](https://console.cloud.google.com/) 建立專案 → 啟用「YouTube Data API v3」→ 憑證頁面建立 API 金鑰。免費配額每日 10,000 單位,`commentThreads.list` 每次呼叫僅耗 1 單位,一般批次用量很低。
- `--engine claude`(翻譯品質較佳,能處理語氣詞、表情符號、迷因梗)透過本機安裝的 [Claude Code](https://docs.claude.com/claude-code) CLI(`claude -p`)執行,不需要 API 金鑰,但要先安裝並執行 `claude login` 登入。偵測不到本機 `claude` 指令時,`--engine auto` 會自動退回免登入的 Google 翻譯。

## 本機網頁介面

比起命令列,網頁介面可以直接貼上 YouTube 網址、一鍵跑完下載+抓留言+翻譯,並在合成前檢視/勾選/修改每則留言的翻譯,適合不想每次都調 CLI 參數的情境。

```powershell
.venv\Scripts\python -m pip install -r webui\requirements.txt
.venv\Scripts\python webui\app.py
```

啟動後瀏覽器開 <http://127.0.0.1:5001>,依序完成:

1. **貼上網址** — 可選填下載區間起訖秒數(留空則下載完整影片)、每則留言顯示秒數、篩選門檻(讚數/字數)、翻譯引擎,送出後會自動下載影片、依影片長度算出剛好連續播完的留言則數(多留 5 則候選)、抓留言、翻譯
2. **檢視留言** — 可取消勾選不想用的留言、直接修改翻譯文字、設定標題,頁面上會顯示「建議保留幾則」的提示
3. **完成** — 預覽合成好的影片,可返回上一步調整選項重新合成

## 命令列使用方式

```powershell
# 單支或多支影片(逗號分隔 videoId 或完整網址)
.venv\Scripts\python main.py --video-ids dQw4w9WgXcQ,another_id

# 用清單檔批次處理(每行一個 videoId 或網址,# 開頭視為註解)
.venv\Scripts\python main.py --input-file ids.txt

# 只下載/使用影片 30~90 秒這段區間(整批影片套用同一區間)
.venv\Scripts\python main.py --video-ids dQw4w9WgXcQ --start 30 --end 90

# 常用調整:每則顯示 6 秒、加標題、關閉雙語卡片
.venv\Scripts\python main.py --video-ids dQw4w9WgXcQ --card-duration 6 --title "外國人看到這個都笑瘋" --no-bilingual
```

### 常用選項

| 選項 | 說明 | 預設 |
|---|---|---|
| `--start` / `--end` | YouTube 下載區間起訖秒數,只對本次批次所有影片套用同一區間;不指定則下載完整影片 | 無(完整影片) |
| `--max-comments` | 每支影片最多抓幾則留言(篩選前的候選池) | 100 |
| `--top-n` | 篩選後最終選用幾則留言做成卡片;不指定則依影片長度自動計算(填滿所需則數 + 5 則候選) | 自動 |
| `--min-likes` | 留言讚數門檻 | 0 |
| `--min-chars` / `--max-chars` | 留言字數範圍 | 5 / 120 |
| `--engine` | 翻譯引擎:`auto` / `google` / `claude` | `auto` |
| `--bilingual` / `--no-bilingual` | 卡片同時顯示原文(較小字體附在翻譯下方) | 開啟 |
| `--card-duration` | 每則留言卡片顯示秒數,留言連續播放無間隔 | 3 |
| `--start-offset` | 第一則留言卡片出現的時間點(秒) | 1 |
| `--title` | 疊加在影片上方的標題文字 | 無 |
| `--auto-title` | 不指定 `--title` 時,改用影片原始標題當標題疊字 | 關閉 |
| `--normalize-audio` / `--no-normalize-audio` | 合成完後把音量正規化到 YouTube 標準響度 | 開啟 |
| `--target-lufs` | `--normalize-audio` 開啟時的目標響度 | -14 |
| `--output-dir` | 輸出資料夾 | `output` |

留言固定連續播放、無間隔,不指定 `--top-n` 時會依 `--card-duration` 跟影片長度自動算出剛好連續播完的則數(除不盡的零頭秒數自動捨棄),篩選時再多留 5 則候選。

批次處理時,單支影片失敗(例如留言已關閉、篩選後留言數為 0)不會中斷整批,會記錄下來並繼續處理下一支,最後印出失敗清單。

## 輸出檔案

以 `output/` 為例:

```
output/
├── {video_id}.mp4                   # 下載的原始影片
├── avatars/{comment_id}.jpg         # 下載的頭像
├── cards/{video_id}/{comment_id}.png # 留言卡片透明 PNG
└── {video_id}.commented.mp4         # 最終合成影片
```

## 篩選規則

`subtool/filter_comments.py` 依序套用:讚數門檻 → 字數範圍 → 關鍵字排除(內建中/英/韓基本髒話、廣告、劇透關鍵字清單)→ 依讚數排序取前 `top_n` 則。關鍵字清單不追求完整覆蓋,漏網的建議事後人工複查。

## 版面與播放邏輯

`subtool/compose.py` 固定輸出 1080x1920(9:16):上方黑底標題(滿版寬實心黑底、文字置中)→ 來源影片置中裁切成正方形(1080x1080)→ 下方留言卡片區。標題文字位置與留言卡片位置是固定值,互不相依;影片區塊會往上移到剛好貼齊留言卡片上緣、不會重疊。留言卡片連續播放、每則固定 `card_duration` 秒、無間隔,超出影片長度的部分自動不會顯示(`needed_comment_count()` 用來事先算出剛好填滿的則數)。

## 音量正規化

合成完成後,預設會呼叫 `subtool/audio.py` 的 `normalize_audio()` 把最終影片音量正規化到 -14 LUFS(YouTube 標準響度),直接原地覆蓋輸出檔案,不需要另外執行。用 `--no-normalize-audio`(CLI)或取消網頁介面的對應勾選可以關閉。

想手動微調某支已完成影片的音量(不想重跑整條流程),可以用根目錄的 `adjust_volume.py`:

```powershell
.venv\Scripts\python adjust_volume.py output\demo.commented.mp4              # 自動正規化到 -14 LUFS
.venv\Scripts\python adjust_volume.py output\demo.commented.mp4 --gain 8     # 直接加大 8 dB
.venv\Scripts\python adjust_volume.py output\demo.commented.mp4 --factor 2.5 # 音量放大 2.5 倍
```

這個工具預設不會覆蓋原檔案(輸出檔名會加上 `_loud`),跟主流程「原地覆蓋」的行為不同,適合想保留原檔案比對的情境。

## 留言卡片樣式

`subtool/templates/comment_card.html` 是 Jinja2 模板,黑底圓角卡片(頭像、帳號、相對時間、留言內容、讚數、回覆圖示),用 Playwright 截圖成透明背景 PNG。想調整樣式(顏色、字級、版面)直接改這個檔案即可,不需要改 Python 程式碼。

## 已知限制

- 目前每支影片一次只產生一支合成影片
- 關鍵字排除清單為基礎版本,建議依實際素材語言(韓文為主)持續補充
- 僅在 Windows 上驗證過
