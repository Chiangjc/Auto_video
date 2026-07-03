# VideoSubtitler — 影片轉字幕 + 繁體中文翻譯 + 字幕燒錄

讀取本地影片或音訊檔(mp4 / mp3 / wav / m4a ...),自動完成三件事:

1. **產出字幕文字檔** — 用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 語音辨識,輸出 `.srt`(含時間軸)與 `.txt`(純文字)
2. **翻譯成繁體中文** — 輸出 `.zh-TW.srt` 與 `.zh-TW.txt`,並用 [OpenCC](https://github.com/BYVoid/OpenCC) `s2twp` 統一為台灣慣用語
3. **燒錄繁中字幕** — 用 ffmpeg 把字幕硬壓進影片,輸出 `.zh-TW.mp4`

> mp3 等純音訊檔也支援:會自動產生深色背景影片再壓上字幕。

目前僅在 **Windows** 上開發與測試(字幕燒錄預設使用 Windows 內建的「微軟正黑體」)。

## 環境需求

- Windows 10/11 + Python 3.10 以上(本專案以 3.12 開發)
- [ffmpeg](https://github.com/BtbN/FFmpeg-Builds/releases)(需自行下載,見下方安裝步驟——**不包含在本專案內**,因體積過大)

## 安裝

```powershell
git clone https://github.com/<your-username>/VideoSubtitler.git
cd VideoSubtitler

py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### 安裝 ffmpeg

1. 到 [BtbN/FFmpeg-Builds releases](https://github.com/BtbN/FFmpeg-Builds/releases) 下載 `ffmpeg-master-latest-win64-gpl.zip`
2. 解壓縮後,將整個資料夾(例如 `ffmpeg-master-latest-win64-gpl`)放到專案的 `tools/` 資料夾下,使 `tools/ffmpeg-*/bin/ffmpeg.exe` 存在

   或者,直接把 ffmpeg 安裝到系統並加入 `PATH`,程式會自動偵測。

## 快速試用

不想準備自己的影片?專案內附兩個合成測試素材(純語音朗讀 + 純色背景,無版權疑慮),可以直接跑一次看效果:

```powershell
.venv\Scripts\python main.py samples\test_video.mp4
```

執行完成後,`output/` 資料夾會出現 `test_video.zh-TW.mp4`(已燒錄繁中字幕的影片)。

## 使用方式

```powershell
# 一鍵完成三步驟(辨識 → 翻譯 → 燒錄)
.venv\Scripts\python main.py "D:\影片\demo.mp4"

# mp3 也可以
.venv\Scripts\python main.py "D:\音樂\podcast.mp3"

# 只做某幾步
.venv\Scripts\python main.py demo.mp4 --steps transcribe
.venv\Scripts\python main.py demo.mp4 --steps translate,burn
```

### 常用選項

| 選項 | 說明 | 預設 |
|---|---|---|
| `--model` | Whisper 模型:`tiny` / `base` / `small` / `medium` / `large-v3`,越大越準但越慢 | `small` |
| `--engine` | 翻譯引擎:`auto` / `google` / `claude` / `opencc` | `auto` |
| `--language` | 強制指定來源語言(如 `en`、`ja`、`zh`),不指定則自動偵測 | 自動 |
| `--steps` | 要執行的步驟,逗號分隔 | 全部 |
| `--output-dir` | 輸出資料夾 | `output` |
| `--font-size` | 燒錄字幕的字級 | `22` |
| `--font` | 燒錄字幕的字型名稱(需系統已安裝該字型) | `Microsoft JhengHei` |
| `--font-color` | 燒錄字幕的顏色,6 碼十六進位色碼(如 `FFFF00` 為黃色) | `FFFFFF`(白色) |
| `--position` | 燒錄字幕的位置:`top` / `bottom` | `bottom` |
| `--bold` | 加上此旗標讓字幕變粗體 | 不加粗 |

範例:黃色粗體字幕、字級 28、顯示在畫面上方

```powershell
.venv\Scripts\python main.py demo.mp4 --font-color FFFF00 --bold --font-size 28 --position top
```

### 翻譯引擎說明

- **`google`** — 免費 Google 翻譯,再經 OpenCC `s2twp` 統一為台灣正體用語,免金鑰
- **`claude`** — 用 [Anthropic Claude API](https://www.anthropic.com)(`claude-opus-4-8`)翻譯,品質最佳,能理解上下文與口語語氣。需自行申請並設定環境變數 `ANTHROPIC_API_KEY`
- **`opencc`** — 純簡轉繁,只適合來源本來就是簡體中文的影片
- **`auto`** — 有設定 `ANTHROPIC_API_KEY` 時自動用 claude,否則用 google

## 輸出檔案

以 `demo.mp4` 為例,輸出到 `output/`:

| 檔案 | 內容 |
|---|---|
| `demo.srt` | 原文字幕(含時間軸) |
| `demo.txt` | 原文純文字 |
| `demo.zh-TW.srt` | 繁體中文字幕 |
| `demo.zh-TW.txt` | 繁體中文純文字 |
| `demo.zh-TW.mp4` | 已燒錄繁中字幕的影片 |

## 修正錯誤的字幕內容

Whisper 辨識或翻譯偶爾會出錯(聽錯字、翻譯不通順)。`output/` 資料夾裡的字幕檔就是**純文字檔**,可以直接編輯修正,不需要重新跑整個流程。

1. 用文字編輯器(記事本、VS Code 皆可)打開 `output/影片名.zh-TW.srt`,內容格式如下:

   ```
   2
   00:00:08,480 --> 00:00:16,640
   人工智慧使這個過程變得非常簡單。感謝您的觀看，我們下次再見。
   ```

   數字下一行是**時間軸**(`開始 --> 結束`),再下一行才是字幕文字。找到涵蓋你要修正時間點的那一段,直接改文字、存檔。

2. 只重新執行燒錄步驟,不用重跑辨識與翻譯:

   ```powershell
   .venv\Scripts\python main.py demo.mp4 --steps burn
   ```

   這會直接讀取你剛剛手動修正的 `demo.zh-TW.srt` 重新燒錄,速度比整套重跑快很多。

> 如果錯字是**辨識階段**聽錯(原文就錯了),要修正的是 `demo.srt`,改完後執行 `--steps translate,burn` 讓翻譯跟著重新產生;如果只是**翻譯用詞**不通順、原文沒問題,直接改 `demo.zh-TW.srt` 再 `--steps burn` 即可。
>
> 想要有時間軸拖拉介面而不是純文字編輯,可以用免費的 [Aegisub](http://www.aegisub.org/) 或 [Subtitle Edit](https://www.nikse.dk/subtitleedit) 開啟 SRT 檔案。

## 專案結構

```
VideoSubtitler/
├── main.py              # 命令列進入點,串接三個步驟
├── subtool/
│   ├── transcribe.py    # 步驟 1:faster-whisper 語音辨識
│   ├── translate.py     # 步驟 2:翻譯成繁體中文
│   ├── burn.py          # 步驟 3:ffmpeg 燒錄字幕
│   └── ffmpeg_utils.py  # ffmpeg 執行檔偵測
├── samples/              # 合成測試素材(無版權疑慮)
├── requirements.txt
└── tools/                # 放置自行下載的 ffmpeg(已加入 .gitignore)
```

## 已知限制

- 目前一次只能處理一個檔案,沒有批次處理功能
- 字幕斷句直接沿用 Whisper 原始分段,長句可能單行字幕偏長
- 只支援硬字幕(燒錄進畫面),沒有輸出可開關的軟字幕選項
- 未做配音/口譯功能
- 僅在 Windows 上驗證過

如果需要更完整的功能(YouTube 下載、批次處理、智慧斷句、配音等),可以參考 [VideoLingo](https://github.com/Huanshere/VideoLingo) 或 [subsai](https://github.com/absadiki/subsai)。

## 授權與注意事項

- 本專案採用 [MIT License](LICENSE)
- ffmpeg 本身採用 GPL/LGPL 授權,請依 [ffmpeg 授權條款](https://ffmpeg.org/legal.html)自行下載使用,不包含在本專案內
- **請確保你有權處理輸入的影片內容。** 本工具只是自動化字幕流程,轉譯、翻譯、燒錄產生的檔案版權歸屬仍取決於原始影片內容的授權狀態,使用者需自行負責

## 致謝

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 語音辨識
- [OpenCC](https://github.com/BYVoid/OpenCC) — 簡繁轉換
- [deep-translator](https://github.com/nidhaloff/deep-translator) — 翻譯介接
- [FFmpeg](https://ffmpeg.org/) — 影音處理與字幕燒錄
