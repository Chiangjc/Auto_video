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

## 2026-07-23 新增本機網頁介面(webui/),以及順便修好一個潛藏的 CC 字幕轉檔 bug

使用者想要一個簡單的本機網頁介面,明確要求「不要修改原本的東西」。做法是整個放在新的 [webui/](webui) 資料夾,只從 `subtool/` 匯入既有函式(`download_youtube`、`download_youtube_captions`、`get_most_replayed_range`、`transcribe`、`translate_srt`、`build_bilingual_srt`、`burn_subtitles`),完全沒有動到 `main.py` 或 `subtool/*.py` 任何一行。

**依賴套件的處理**:因為不能改動原本的 `requirements.txt`,新增了獨立的 `webui/requirements.txt`(只有 `flask`),裝進同一個 `.venv`(不用另外開新的虛擬環境,不然要重裝一次 faster-whisper 這些又大又慢的套件)。

**介面設計**(依使用者三點需求):
1. 來源可以貼 YouTube 網址,或上傳本機檔案(兩者用圓點單選切換)。
2. 表單選項照使用者說的規則做:3 個以內的選項(來源模式、字幕來源、輸出畫面格式)用圓點單選;超過 3 個的(Whisper 模型、翻譯引擎、字幕位置、字型)用下拉式選單。字型下拉是使用者自己舉的例子,選項包含這個專案目前預設的 LXGW WenKai TC、原本的 Microsoft JhengHei,以及幾個常見 Windows 中文字型,另外留一個「自訂...」選項可以直接輸入任意字型名稱。
3. 燒錄前有一個校對畫面,三欄並排:左邊放影片(`<video>` 播放器)、中間原文字幕、右邊繁中字幕,都是可以直接編輯的文字框,編輯完按「儲存並燒錄」才會真的寫回 `.srt` 檔並執行燒錄。文字框內容就是原始 SRT 格式(含編號、時間軸),跟 README 原本就有教的「手動修正字幕」方式一致,沒有另外做逐句對照的複雜介面,保持簡單。

技術上是一個三步驟流程(表單 → 校對 → 完成),用 Flask 兩個 API(`/api/prepare` 處理下載/辨識/翻譯,`/api/burn` 處理儲存編輯內容+燒錄)+ 一個純 vanilla JS 的單頁 HTML(沒有用任何前端框架,符合「盡可能簡單」)。工作階段用記憶體裡的字典暫存(單人本機用途,不需要資料庫,重啟伺服器就會清空,可接受)。

**意外抓到的 bug**:實際在瀏覽器裡跑第一次完整測試(YouTube 網址 + 強制用 YouTube CC 字幕)時,`/api/prepare` 回傳 400 錯誤「找不到 YouTube 字幕(CC)」,但 log 顯示字幕明明有下載成功(`.vtt` 檔案存在)。查下去發現 `download_youtube_captions()`(上週寫的)裡用來把 `.vtt` 轉成 `.srt` 的 yt-dlp `FFmpegSubtitlesConvertor` postprocessor,在 `skip_download=True` 的情況下**根本不會被執行**(用 `verbose: True` confirmd 完全沒有任何 postprocess 相關的 log 輸出)。這個 bug 其實從字幕功能加入以來就一直潛藏著,只是先前都只用 mock 資料測試 `_pick_caption_language()` 這個純函式,沒有真的跑過完整下載+轉檔流程,這次因為要測 webui 才第一次真正跑到這條路徑,順便抓出來。

**修法**:改成自己呼叫 ffmpeg 轉檔(跟 `burn.py` 呼叫 ffmpeg 的方式一樣,用 `subprocess.run`),不要依賴 yt-dlp 的 postprocessor。下載完 `.vtt` 後直接 `ffmpeg -i xxx.vtt xxx.srt`,轉完把中間產物 `.vtt` 刪掉。

**驗證**:
- 直接呼叫修好後的 `download_youtube_captions()`(用 `BOhBOZCRpwM` 這支影片、韓文字幕),確認能正確產生 `.srt` 檔,內容是正常的韓文字幕。
- 在瀏覽器裡實際跑一次 webui 完整流程:YouTube 網址(`BOhBOZCRpwM`)+ 自動抓最多人重播區間 + 強制用 YouTube CC + google 翻譯引擎 → 成功進到校對畫面(影片可播放、原文韓文字幕與繁中字幕都正確顯示)→ 手動編輯繁中字幕其中一句 → 按「儲存並燒錄」→ 確認編輯內容有寫回 `.srt` 檔 → 成功燒出最終影片,完整跑完三步驟。

**啟動方式**:
```powershell
.venv\Scripts\python -m pip install -r webui\requirements.txt   # 只需要裝一次
.venv\Scripts\python webui\app.py
# 瀏覽器開 http://127.0.0.1:5000
```

## 2026-07-23 校對頁面新增「只燒錄片段」與「取消」按鈕

使用者確認了兩個細節:「取消」是放棄校對回到第一步(不需要中斷正在跑的 ffmpeg);「選擇時間區間段」是指只燒錄已經準備好的影片其中一段,不用整支重新下載/辨識。

**只燒錄片段**:在 [webui/app.py](webui/app.py) 新增 `_trim_video()`(呼叫 ffmpeg 剪片段,音訊檔跟有畫面的檔案分開處理,音訊檔不會加 `-c:v`)跟 `_trim_srt()`(裁切並平移字幕時間軸,邏輯跟 `subtool/download.py` 裡處理 YouTube `--start`/`--end` 的方式一樣,但獨立寫一份在 webui 這邊,避免去依賴 subtool 裡面那個底線開頭的私有函式)。`/api/burn` 收到 `clip_start`/`clip_end` 時,會先剪出片段(檔名 `clip_<job_id>.mp4` / `.srt` / `.zh-TW.srt`),再用剪好的片段去跑原本的 `burn_subtitles()`,沒有動到 `subtool/burn.py`。

**取消按鈕**:校對頁面(影片/原文/繁中三欄那頁)新增「取消」按鈕,跟完成頁面的「重新開始」共用同一個重置函式,直接丟掉目前的工作階段回到第一步的表單。

前端在校對頁面新增「起始(秒)」「結束(秒)」兩個輸入框(留空就燒錄整段,行為不變),影片載入後會顯示影片總長度當參考。

**驗證**:在瀏覽器實際跑過:1) 校對頁面按「取消」,確認正確回到第一步、表單清空;2) 重新跑一次 → 校對頁面設定起始 2 秒、結束 8 秒 → 燒錄 → 用 ffprobe 確認輸出影片長度是 6.006 秒(符合 8-2=6 秒的預期),字幕檔時間軸也從 00:00:00 開始,確認剪輯跟字幕平移都正確對齊。

## 2026-07-23 校對頁面新增「加上標題」選項

使用者要求:放在校對階段、可自行選擇要不要加、位置預設約畫面 1/3 高、字型預設饅頭黑體、內容手動輸入。

**字型檔位置**:「饅頭黑體」是使用者自己裝的字型,查 Windows 登錄檔(`HKCU\...\Fonts`)確認實際字型檔在 `C:\Users\sandy\AppData\Local\Microsoft\Windows\Fonts\MantouSans-Regular.ttf`。這裡不能只給字型名稱,因為 ffmpeg 的 `drawtext` 濾鏡跟燒字幕用的 `subtitles` 濾鏡不一樣——`subtitles` 底層用 libass,在 Windows 上可以透過系統的字型服務直接用名稱找到字型;但 `drawtext` 在這個 ffmpeg 版本沒有 fontconfig 可用(先前測試就有看到 fontconfig 讀取失敗的警告),只能直接指定字型檔案路徑(`fontfile=`),所以把這個路徑寫死在 [webui/app.py](webui/app.py) 的 `DEFAULT_TITLE_FONTFILE`。

**實作方式**:標題不是跟字幕同一次燒錄,而是在 `burn_subtitles()` 燒完字幕、拿到輸出影片之後,再用新的 `_add_title()` 多跑一次 ffmpeg(`drawtext` 濾鏡疊字),做法跟稍早的剪片段功能一樣,完全寫在 webui/app.py 裡,沒有動到 `subtool/burn.py`。標題文字用 `textfile=` 讀取暫存的 txt 檔(而不是直接把文字塞進濾鏡字串),這樣可以完全避開使用者輸入裡的特殊字元(冒號、單引號等)造成濾鏡字串解析錯誤的問題,轉完就把暫存 txt 刪掉。

位置用 ffmpeg 內建的 `w`/`h`/`text_w`/`text_h` 變數算 `x=(w-text_w)/2:y=h/3-text_h/2`,直接用「這次實際輸出畫面」的真實尺寸置中定位,不像字幕位置那樣要處理 288 基準座標系統的換算問題(`drawtext` 跟 `subtitles` 濾鏡的座標系統不一樣,`drawtext` 就是直接用真實像素)。文字加白色底黑框(`box=1:boxcolor=black@0.5`)確保疊在任何畫面內容上都看得清楚。

前端:校對頁面新增「加上標題」核取方塊 + 文字輸入框(勾選後才顯示),勾選但沒填內容時會擋下不送出並提示。

**驗證**:瀏覽器實測完整跑一次(YouTube 網址 → CC 字幕 → 校對頁面勾選加上標題、輸入「測試標題文字」→ 燒錄),抓輸出影片的畫面確認標題文字有正確疊上去,位置大約在畫面 1/3 高、水平置中,字體也正確套用饅頭黑體(帶黑色半透明底,清晰可讀)。

## 2026-07-23 標題改成跟燒字幕合併成同一次編碼

使用者反應標題功能雖然選項留在校對頁面沒問題,但希望燒錄本身合併成一次,不要多一次重新編碼。這次改成直接動 [subtool/burn.py](subtool/burn.py)(先前的限制是「不要動原本的東西」,這次使用者明確同意改這部分)。

**改法**:`burn_subtitles()` 新增 `title`/`title_font_file` 兩個參數。原本字幕燒錄用的 `-vf` 濾鏡字串,現在改成一個 list,字幕濾鏡跟標題的 `drawtext` 濾鏡都放進同一個 list 用逗號串接,一次丟給 ffmpeg,只跑一次編碼。`_build_video_filter()` 也跟著改成接受濾鏡 list 而不是單一字串,縮放/裁切/留黑一樣放最前面,確保字幕跟標題都疊在轉換後的最終畫面上。標題文字暫存檔案用 `try/finally` 包起來,不管燒錄成功或失敗都會清掉。

`title_font_file` 沒有寫死在 `subtool/burn.py` 裡(那樣會綁死這台機器的路徑,不利於 CLI 的可攜性),維持由呼叫端(webui)傳入實際字型檔路徑,`subtool/burn.py` 只負責組 ffmpeg 指令。main.py(CLI)沒有改動,因為 `title`/`title_font_file` 都是新的選填參數,預設 `None`,舊的呼叫方式完全不受影響。

[webui/app.py](webui/app.py) 對應拿掉原本額外多跑一次 ffmpeg 的 `_add_title()`,改成直接把 `title`/`title_font_file` 傳進 `burn_subtitles()` 一次呼叫完成。

**驗證**:瀏覽器實測完整跑一次(YouTube CC 字幕 → 校對頁面勾選標題輸入「測試標題文字二」→ 燒錄),確認輸出檔在很短時間內就出現(相較於前一版兩次編碼要等將近一分鐘,合併後明顯快很多),抓輸出畫面確認同一格畫面裡標題跟字幕同時正確顯示,標題位置一樣在約 1/3 高、置中。

## 2026-07-24 修好 yt-dlp「No supported JavaScript runtime」警告,順帶修掉一個會讓正常影片被誤判成「不存在」的 bug

使用者反映每次執行都會跳出 `No supported JavaScript runtime could be found` 這個警告。一開始以為只是「有點吵但無害」的訊息,後來使用者提供了實際失敗的例子(`https://www.youtube.com/watch?v=F9c8E5KfE8k`,一支正常存在的兒童數數兒歌影片),用 yt-dlp 直接測試發現真的會報錯 `This video is not available`——查證這支影片在 YouTube 上其實完全正常可以看,證實這個警告不只是吵,而是會讓部分影片誤判成無法下載。

**根本原因**:YouTube 現在會用 JavaScript 挑戰(簽章驗證)保護影片下載連結。沒有 JS runtime(如 Deno)時,yt-dlp 會退回用一個叫「android vr player」的備用擷取管道,這個管道對某些影片不穩定,有時會誤判成「不存在」。

**修法分兩步**:
1. 用 `winget install DenoLand.Deno` 幫使用者裝了 Deno(JavaScript runtime)。裝完只解決一半——實測發現光裝 Deno 還不夠,yt-dlp 還需要另外下載一個「挑戰求解器腳本」(EJS solver script)才能真正解開 YouTube 的簽章驗證,不然還是會顯示「Signature solving failed」然後一樣報錯「video not available」。
2. 在 [subtool/download.py](subtool/download.py) 幫所有呼叫 yt-dlp 的地方(`download_youtube`、`get_most_replayed_range`、`download_youtube_captions` 用到的三個 `YoutubeDL` 實例)都加上 `"remote_components": ["ejs:github"]` 這個選項,讓 yt-dlp 在需要時自動去 GitHub 下載求解器腳本(下載一次後會快取,不會每次都重抓)。這樣使用者不用自己記得加任何額外的命令列參數。

**驗證**:直接呼叫專案裡的 `download_youtube()` 下載先前失敗的那支影片(`F9c8E5KfE8k`),確認能正常下載成功,不用手動加任何 CLI 參數,警告訊息也消失了。

**小提醒**:winget 安裝 Deno 後有更新系統的 PATH 環境變數,但**目前已經開著的終端機視窗不會自動生效**,需要開一個新的終端機視窗(或重新啟動現有的)才能讓 `main.py`/`webui/app.py` 正常找到 `deno`。

## 2026-07-25 改成直接指定 deno.exe 路徑,不再依賴 PATH

上面那個「重開終端機」的提醒後來證實不夠:使用者把 VS Code 整個關掉重開後,`deno --version` 在新開的終端機裡還是顯示「找不到指令」。這是 Windows 的已知行為——winget/系統層級改 PATH 之後,理論上要整個登出重新登入(或重開機)才能保證新流程一定拿到最新的環境變數,只重開應用程式不保證有效,因為應用程式本身(或它的上層流程,例如啟動它的 explorer.exe)可能也還是沿用舊的快取。

與其要求使用者登出/重開機,改成讓程式碼完全不依賴 PATH:在 [subtool/download.py](subtool/download.py) 新增 `_JS_RUNTIMES`,直接寫死指到先前 `winget install` 裝好的 `deno.exe` 實際路徑(`C:\Users\sandy\AppData\Local\Microsoft\WinGet\Packages\DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe\deno.exe`),透過 yt-dlp 的 `js_runtimes` 選項(對應 CLI 的 `--js-runtimes deno:路徑`)直接告訴 yt-dlp 去哪裡找 deno,完全跳過「有沒有在 PATH 裡」這個問題。三個呼叫 yt-dlp 的地方(`download_youtube`、`get_most_replayed_range`、`download_youtube_captions`)都加上這個選項,而且做了防呆:如果那個路徑不存在(例如換一台電腦、或 Deno 版本更新後資料夾名稱變了),`_JS_RUNTIMES` 會是 `None`,不會硬塞一個錯的路徑進去讓程式掛掉,只是會退回原本「沒有 JS runtime」的行為。

同一時間也發現另一個獨立問題:因為先前修 bug 時對 YouTube 做了不少次測試請求,疊加上使用者自己的嘗試,觸發了 YouTube 對這個 IP 的暫時限流(`This content isn't available... rate-limited... up to an hour`)。這個純粹是 YouTube 那邊的流量保護機制,跟 Deno/PATH 是兩個獨立問題,只能等待冷卻,沒有辦法用程式修掉;限流時使用者持續遇到同樣的錯誤訊息,一度誤以為是同一個 bug 沒修好,實際上是 Deno 路徑問題(已修)疊加限流問題(需要等待)同時存在。

**驗證**:程式碼已確認能正常 import,`_JS_RUNTIMES` 正確解析出 deno.exe 路徑。因為使用者的 IP 目前還在限流中,還沒有實際跑一次完整下載來確認修好(避免在限流期間再發送請求延長限流時間),等限流解除後應該找一支影片實測確認。
