# 進度紀錄

## 2026-07-21 修好無法執行的問題

專案下載下來後執行 `main.py` 會直接沒有任何錯誤訊息就整個當掉
**查出來的原因**:

`requirements.txt` 原本沒有鎖定套件版本,`pip install` 會抓最新版的 `ctranslate2`(語音辨識引擎)和 `onnxruntime`(VAD 語音偵測用的)。這兩個套件在 Windows 上的最新版是用比較新的微軟 C++ Redistributable 工具鏈編譯的,跟這台電腦上已安裝的版本不相容,一載入模型就會直接讓整個程式當掉,連錯誤訊息都來不及印出來。

用 Windows 的錯誤紀錄(事件檢視器)查出當掉的地方是 `MSVCP140.dll`(微軟 C++ 執行環境),才確認是版本不相容,不是程式碼本身寫錯。

**怎麼修的**:

在專案的 `.venv` 虛擬環境裡,把幾個套件換成比較舊、相容性較好的版本:

- `numpy` 降到 1.x 版(原本裝到 2.x)
- `ctranslate2` 鎖定在 `4.4.0`(原本最新是 4.8.1,會在載入 Whisper 模型時當掉)
- `onnxruntime` 鎖定在 `1.17.3`(原本最新是 1.23.2,會在字幕辨識的語音偵測 VAD 步驟當掉)

## 2026-07-22 新增 YouTube 連結下載功能

新增 [subtool/download.py](subtool/download.py),用 `yt-dlp` 這個套件下載 YouTube 影片,並支援只下載指定的秒數區間(用 yt-dlp 的 `download_ranges` 功能,不用整支影片都下載完再剪,省時間也省流量)。下載時會沿用專案原本偵測 ffmpeg 的方式(`ffmpeg_utils.find_ffmpeg`),因為合併影音、剪片段都需要用到 ffmpeg。

同時修改了 [main.py](main.py):現在 `input` 參數除了本機檔案路徑,也可以直接丟 YouTube 網址進去,程式會自動判斷(用 `http://`/`https://` 開頭來判斷)並先下載再接著跑辨識/翻譯/燒錄。新增了 `--start` 和 `--end` 兩個秒數選項,只在網址輸入時有效,拿來指定要下載影片的哪一段;如果對本機檔案指定這兩個選項會印出提醒並忽略,不會噴錯。

`requirements.txt` 也加入 `yt-dlp>=2024.8.6`。

目前只做了程式碼層級的驗證(確認能正常 import、`--help` 顯示新選項正確),還沒有實際拿真的 YouTube 網址跑過下載流程,之後應該找一支影片實測看看下載、剪片段、接續辨識翻譯燒錄是否都正常。

## 2026-07-22 新增讀取 YouTube 內建字幕(CC)功能

使用者反應 Whisper 辨識品質不夠好,希望能直接讀取 YouTube 影片本身的 CC 字幕。在 [subtool/download.py](subtool/download.py) 新增 `download_youtube_captions()`:用 `yt-dlp` 查詢該影片有哪些字幕語言,優先選人工上傳的字幕,沒有的話才退而求其次選自動產生的字幕;下載下來的格式是 vtt,再用 ffmpeg 轉成 srt(跟專案原本的字幕格式一致)。

有個容易忽略的小細節:如果使用者用 `--start`/`--end` 只下載影片的某一段,YouTube 字幕的時間軸是對應「整支影片」的,不會自動對齊剪出來的片段。所以另外寫了 `_shift_and_clip_srt()`,把字幕依 start/end 篩選並平移時間軸,確保跟剪出來的片段對得上。

[main.py](main.py) 新增 `--captions auto|youtube|whisper` 選項(預設 `auto`):
- `auto`:網址輸入時優先抓 YouTube CC,抓不到才 fallback 用 Whisper 辨識
- `youtube`:強制要求用 YouTube CC,抓不到就直接報錯,不會偷偷改用 Whisper
- `whisper`:跟原本行為一樣,強制用 Whisper 辨識

`--language` 選項現在身兼兩用:對 Whisper 是強制指定辨識語言,對 YouTube CC 則是指定要抓哪個語言的字幕。

同樣還沒有拿真實 YouTube 影片實測(需要一支確實有 CC 字幕、以及一支只有自動字幕或完全沒字幕的影片來對照測試),之後應該找影片驗證抓字幕、時間軸剪裁對齊是否正確。

## 2026-07-22 新增輸出畫面格式(橫式/直式)與雙語字幕

**畫面格式**:在 [subtool/burn.py](subtool/burn.py) 新增 `--orientation` 選項,燒錄前用 ffmpeg 的 scale/crop/pad 濾鏡把畫面轉成指定格式,燒字幕的濾鏡放在最後面,確保字幕是壓在轉換後的最終畫面上(不然字幕位置/大小會跑掉):

- `horizontal`(預設):維持原始橫式畫面,不做任何轉換
- `vertical-fill`(直式滿版):等比放大到蓋滿 1080x1920,再裁掉左右多出來的部分
- `vertical-pad`(直式上下留黑):等比縮小到完整放進 1080x1920 內,上下用黑色補滿

mp3 等純音訊輸入原本就是用純色背景假造一支影片,直式模式時背景直接用 1080x1920 產生,不用再多套一層縮放。

**雙語字幕**:在 [subtool/translate.py](subtool/translate.py) 新增 `build_bilingual_srt()`,把原文字幕跟繁中字幕依相同時間軸合併成一句兩行(上面原文、下面繁中)。[main.py](main.py) 新增 `--bilingual` 旗標,有加的話會先合併雙語字幕再燒錄;沒加就跟以前一樣只燒繁中單語字幕。

注意:雙語字幕目前兩行共用同一種字型樣式(大小、顏色都一樣),還沒有做「原文較小、譯文較大」這種差異化樣式,如果覺得不好看可以再跟我說,要做的話需要改用完整的 ASS 字幕格式才能讓兩行套用不同樣式。

輸出檔名會依選項自動加後綴,避免蓋掉舊檔,例如 `demo.zh-TW.vertical-pad.bilingual.mp4`;維持預設(橫式+單語)時檔名不變,跟舊版行為一致。

已經拿 `samples/test_video.mp4` 實測 `--orientation vertical-pad --bilingual` 組合,用 ffprobe 確認輸出影片解析度正確是 1080x1920,雙語字幕檔內容也確認一句兩行對得上。`vertical-fill` 邏輯相同,理論上沒問題,但還沒有實際跑過這個選項的輸出來看裁切效果。

## 2026-07-22 字幕位置新增「中」與「2/3」

原本 `--position` 只有 top/bottom。使用者提到把橫式影片轉成直式(尤其是 `vertical-fill` 滿版裁切)時,字幕貼在畫面最底部容易被裁掉的邊緣擋到,所以在 [subtool/burn.py](subtool/burn.py) 新增兩個選項:

- `middle`:垂直置中(ASS Alignment=5),這個不需要知道畫面高度,直接置中即可。
- `2/3`:貼在畫面下三分之一的分隔線上(不是貼死畫面最底部),用 ASS 的 Alignment=2(下緣對齊)搭配算出來的 `MarginV`(=畫面高度 ÷ 3)往上推。

`2/3` 需要知道最終輸出畫面的實際高度才能算 MarginV:直式模式(`vertical-fill`/`vertical-pad`)畫面高度固定是 1920,直接用常數;橫式模式因為每支來源影片解析度不同,新增了 `_probe_height()` 用 ffprobe 讀取實際影片高度。只有選 `2/3` 時才會多跑這次 ffprobe,其他位置選項不受影響。

已實測三種情境確認 MarginV 算對了:
- `--orientation vertical-fill --position 2/3` → MarginV=640(1920÷3)
- `--position middle`(預設橫式)→ Alignment=5,不需要 MarginV
- `--position 2/3`(預設橫式,`test_video.mp4` 是 720p)→ MarginV=240(720÷3),確認 ffprobe 有正確讀到來源影片高度

## 2026-07-22 修正 YouTube CC 字幕語言選擇的 bug

使用者問「有原文 CC 字幕時,翻譯用的是原文還是英文?」,一查發現[subtool/download.py](subtool/download.py) 原本的邏輯(`download_youtube_captions`)有問題:沒有指定 `--language` 時,直接抓 `subtitles`/`automatic_captions` 字典裡的第一個語言,但那個「第一個」只是 YouTube API 回傳的順序,不代表是影片的原始語言。

拿使用者之前測試過的 `BOhBOZCRpwM` 這支影片實際查 yt-dlp 回傳的資料證實了這個問題:這支影片其實是韓文(`language: ko`),但人工上傳字幕只有 `['en', 'ja', 'es', 'th', 'live_chat']`(沒有韓文),原本的邏輯會直接抓第一個 `en`,等於把英文翻譯字幕當「原文」拿去翻成繁中,而不是真正的韓文原音字幕。

**修法**:新增 `_pick_caption_language()`,語言選擇優先序改成:
1. 使用者用 `--language` 指定的語言
2. yt-dlp 回傳的 `info['language']`(YouTube 偵測到的影片原始語言)——先找人工字幕、再找自動字幕
3. 都沒有的話才退回「隨便挑一個有的」(人工優先於自動),跟舊行為一樣

另外把 `live_chat`(直播聊天室回放,會被 YouTube 誤列在字幕語言清單裡)排除,避免誤選。

現在每次選定字幕後都會印出訊息,例如選到的語言跟偵測到的原始語言不同時會多印一行 `影片偵測原始語言: ko`,方便使用者一眼看出是不是抓到自己要的。

用 `BOhBOZCRpwM` 實際跑過 `_pick_caption_language()`,確認修好後會正確選到 `ko`(自動字幕),而不是英文。

**第二個問題「如果只有英文字幕,雙語字幕上排會是原文還是英文?」**:雙語字幕的「原文」那一行,本來就是直接沿用被抓下來/辨識出來的那份字幕(不管是 CC 還是 Whisper 結果),所以如果影片真的只有英文字幕可抓,雙語字幕上排就會是英文,這是設計上就如此,不是 bug。

## 2026-07-22 修正字幕位置的嚴重 bug(2/3 完全沒顯示、top/middle 位置錯誤)

使用者回報 `--position 2/3` 完全看不到字幕,另外想要一個「正中間」的位置選項(結果發現原本的 `middle` 也是錯的)。這次用「拿 ffmpeg 實際燒出畫面、再用 Python 逐像素找字幕文字的位置」的方式抓出兩個疊在一起的 bug,不是單純看 code 猜的:

**bug 1 — Alignment 數字不是想像中的 ASS numpad(1-9)方位**:實測這個 ffmpeg/libass 版本的 `force_style` 的 `Alignment` 欄位其實吃的是舊版 SSA 的編號,跟一般常見的九宮格編號(1-9,4=中左、5=正中、8=上中)對不起來。實測結果:`2`=下置中(這個剛好兩種編號都一樣,所以之前沒發現)、`6`=上置中(不是 8)、`10`=中置中(不是 5)。原本 `top` 用 8、`middle` 用 5,兩個都是錯的位置,只是画面剛好還有東西可以看,沒有完全消失,所以感覺「大概有效」,但其實位置是錯的。

**bug 2 — MarginV 的座標基準跟實際影片解析度無關,是 ffmpeg 內部固定的 288**:ffmpeg 把 SRT 轉成 ASS 時,不管輸出影片是多高,內部一律先用固定的 384x288 座標系統算位置,最後才等比例縮放到實際畫面。`2/3` 位置原本的算法是拿 ffprobe 量到的實際影片高度去除以 3(例如 1920÷3=640)當作 MarginV,但 MarginV 其實要用 288 這個基準去算(288÷3=96),不能直接套用實際像素高度。把 640 當成 MarginV 送進一個等比例縮放到 1920 高的畫面,實際換算後的位移量遠遠超過畫面本身高度,字幕整個被推到看不見的地方 ——這就是「2/3 完全沒顯示」的真正原因。

**修法**:在 [subtool/burn.py](subtool/burn.py) 把四個位置選項的 (Alignment, MarginV) 改成寫死的對照表,MarginV 一律用 288 這個固定基準去算,不用再另外 `ffprobe` 偵測影片解析度(等比例縮放,橫式直式都通用):

- `top`: Alignment=6, MarginV=10
- `middle`: Alignment=10, MarginV=0
- `bottom`: Alignment=2, MarginV=10(沒變)
- `2/3`: Alignment=2, MarginV=96(288÷3)

因為不用再偵測解析度,原本加的 `_probe_height()`(用 ffprobe 查影片高度)整個刪掉了,程式碼反而變簡單。

**驗證方式**:寫了一段 Python 腳本,拿 Pillow 讀燒錄後的影片截圖,找出白色字幕文字的像素範圍算出中心點座標(佔畫面寬高的比例),不是用肉眼看猜的。四個位置實測結果:top=(0.50, 0.06)、middle=(0.50, 0.50)、bottom=(0.50, 0.94)、2/3=(0.50, 0.64),都符合預期(2/3 的 0.64 很接近理論值 0.667,誤差是文字本身高度造成的,可接受)。另外也驗證了 `--orientation vertical-fill` 搭配 `--position 2/3` 在 1080x1920 的輸出上一樣正確(0.58,比橫式的 0.64 稍微低一點,同樣是文字高度佔比不同造成的正常誤差)。

## 2026-07-22 調整 middle/2-3 位置:middle 改成約 2/3 高度,2/3 再更低避免擋住直式留黑的畫面內容

使用者測完後提出兩個調整:
1. 把 `middle` 改成原本 `2/3` 的位置(Alignment=2, MarginV=96)。
2. `2/3` 要比原本更低一點,理由是用 `vertical-pad`(直式,等比縮放完整保留畫面、上下留黑)時,字幕如果貼在原本 `2/3` 的高度,會剛好疊到畫面內容的下緣。

先用算術確認問題:`test_video.mp4` 是 1280x720(16:9),縮放進 1080 寬的直式畫面後,畫面內容高度約 608px,置中後上下各留約 656px 黑邊,換算下來畫面內容大概只佔整個直式畫面 34.2%~65.8% 的範圍。原本 `2/3` 位置(MarginV=96)算出來的文字中心大概在 64% 高,幾乎正好卡在畫面內容下緣(65.8%)附近,難怪會擋到。

**調整方式**:在 [subtool/burn.py](subtool/burn.py) 直接實測校準(用 `vertical-pad` 實際燒出畫面,Pillow 量字幕文字上緣的實際位置,不是用公式推算),測了 MarginV=40/50/60/70 四組:

| MarginV | 文字上緣位置 | 是否清楚避開畫面內容(65.8%)|
|---|---|---|
| 40 | 70.4% | 是,有約 4.6% 緩衝 |
| 50 | 66.9% | 太貼近,幾乎沒有緩衝 |
| 60 | 63.4% | 否,疊到畫面內容 |
| 70 | 60.0% | 否,明顯疊到畫面內容 |

最後選 `MarginV=40` 作為新的 `2/3`,`middle` 則直接沿用原本 `2/3` 的 `MarginV=96`。

修改後對照表:
- `top`: Alignment=6, MarginV=10(不變)
- `middle`: Alignment=2, MarginV=96(原本 2/3 的位置)
- `bottom`: Alignment=2, MarginV=10(不變)
- `2/3`: Alignment=2, MarginV=40(比 middle 更低)

**驗證**:實際跑 `--orientation vertical-pad --position middle` 跟 `--position 2/3`,量測文字位置:`middle` 文字上緣剛好落在 65.8%(跟畫面內容下緣齊平,不重疊但很貼近);`2/3` 文字上緣落在 70.4%,明顯低於畫面內容下緣,不會擋到畫面。

## 2026-07-22 新增自動抓 YouTube「最多人重播」熱度區間下載

使用者問「yt-dlp 能不能自動讀取最多人播放的區間下載」,查了一下 yt-dlp 回傳的 info 字典裡確實有 `heatmap` 欄位——這是 YouTube 影片下方那條「最多人重播」灰色熱度圖的原始資料,格式是 100 段等長區間,每段有 `start_time`/`end_time`/`value`(熱度 0~1)。拿使用者之前測過的 `BOhBOZCRpwM` 驗證,熱度最高的區間是 799.8s~825.6s(約 13:20~13:46),剛好跟使用者更早之前手動指定的 13:25~13:43 幾乎重疊,滿有趣的巧合。

不是每支影片都有這份資料(要有足夠觀看數 YouTube 才會產生),所以有處理「查不到」的情況。

**實作**:在 [subtool/download.py](subtool/download.py) 新增 `get_most_replayed_range()`,抓熱度圖裡 `value` 最高的那一段,回傳 `(start_time, end_time)`;沒有熱度圖資料就回傳 `None`。

[main.py](main.py) 新增 `--most-replayed` 旗標(只對 YouTube 網址有效):有加的話會先查熱度圖,查到就蓋掉 `--start`/`--end` 改用熱度最高的區間;查不到就印提示訊息,改成用原本的 `--start`/`--end`(或沒指定就下載完整影片)。順便把 `download_youtube_captions()` 用到的 start/end 也改成引用同一個「解析後」的變數,確保字幕裁切跟實際下載的影片區間永遠是同一組數字,不會各用各的。

目前只驗證了 `get_most_replayed_range()` 本身能正確查到熱度資料、main.py 的 import 跟參數解析邏輯沒問題,還沒有實際跑過 `--most-replayed` 完整下載一次(這會真的連網下載影片,還沒經使用者同意執行)。
