"""下載步驟:給 YouTube 網址,下載影片(可指定只下載某段秒數區間),或讀取 YouTube 內建字幕(CC)。"""
import datetime
import subprocess
from pathlib import Path

import srt

from .ffmpeg_utils import find_ffmpeg

# YouTube 現在會用 JS 挑戰驗證影片連結,yt-dlp 需要一個 JS runtime(如 Deno)加上這個挑戰求解器
# 腳本才能正確解出來;沒有的話某些影片會直接被誤判成「不存在」(實測過,不是猜的)。
# remote_components 允許 yt-dlp 在需要時自動下載這個求解器腳本(下載一次後會快取,不會每次都重抓)。
_REMOTE_COMPONENTS = ["ejs:github"]

# Deno 裝好之後系統 PATH 有更新,但實測發現「重開終端機/VS Code」不保證會生效——Windows
# 這類環境變數更新常常要整個登出或重開機才會真的套用到新流程,不能只靠 PATH 找 deno。
# 所以直接把 deno.exe 的實際路徑寫死指給 yt-dlp,完全不依賴 PATH 有沒有生效。
_DENO_EXE = str(
    Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    / "DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe" / "deno.exe"
)
_JS_RUNTIMES = {"deno": {"path": _DENO_EXE}} if Path(_DENO_EXE).exists() else None


def is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def download_youtube(
    url: str,
    output_dir: str,
    start: float | None = None,
    end: float | None = None,
) -> str:
    """下載 YouTube 影片,回傳下載後的本機檔案路徑。

    start/end:指定只下載的秒數區間(如 start=30, end=60 只下載 00:30~01:00)。
    """
    import yt_dlp

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = find_ffmpeg()

    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out / "%(id)s.%(ext)s"),
        "ffmpeg_location": str(Path(ffmpeg_path).parent),
        "noplaylist": True,
        "remote_components": _REMOTE_COMPONENTS,
    }
    if _JS_RUNTIMES:
        ydl_opts["js_runtimes"] = _JS_RUNTIMES

    if start is not None or end is not None:
        from yt_dlp.utils import download_range_func

        range_start = start or 0
        range_end = end if end is not None else float("inf")
        if range_end <= range_start:
            raise ValueError(f"--end ({end}) 必須大於 --start ({start})")
        ydl_opts["download_ranges"] = download_range_func(None, [(range_start, range_end)])
        ydl_opts["force_keyframes_at_cuts"] = True
        end_label = f"{range_end:.0f}" if range_end != float("inf") else "結尾"
        print(f"[download] 只下載 {range_start:.0f}s ~ {end_label}s 區間")

    print(f"[download] 下載中: {url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    requested = info.get("requested_downloads") or []
    if requested:
        video_path = Path(requested[0]["filepath"])
    else:
        video_path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")

    if not video_path.exists():
        raise RuntimeError(f"下載完成但找不到輸出檔案: {video_path}")

    print(f"[download] 下載完成: {video_path}")
    return str(video_path)


def get_most_replayed_range(url: str) -> tuple[float, float] | None:
    """讀取 YouTube 影片下方「最多人重播」熱度圖,回傳熱度最高那一段的 (start, end) 秒數。

    YouTube 只對有足夠觀看數的影片才會產生這份資料,沒有的話回傳 None
    (呼叫端應該退回完整下載,或提示使用者自己指定 --start/--end)。
    """
    import yt_dlp

    opts = {"skip_download": True, "quiet": True, "remote_components": _REMOTE_COMPONENTS}
    if _JS_RUNTIMES:
        opts["js_runtimes"] = _JS_RUNTIMES
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    heatmap = info.get("heatmap")
    if not heatmap:
        return None

    best = max(heatmap, key=lambda seg: seg["value"])
    return best["start_time"], best["end_time"]


def _shift_and_clip_srt(srt_path: str, start: float | None, end: float | None) -> None:
    """把字幕時間軸裁切並平移,對齊 download_youtube 用 --start/--end 剪出來的片段。"""
    offset = datetime.timedelta(seconds=start or 0)
    range_end = datetime.timedelta(seconds=end) if end is not None else None

    subs = list(srt.parse(Path(srt_path).read_text(encoding="utf-8")))
    kept = []
    for s in subs:
        if s.end <= offset:
            continue
        if range_end is not None and s.start >= range_end:
            continue
        s.start = max(s.start - offset, datetime.timedelta(0))
        s.end = (min(s.end, range_end) if range_end is not None else s.end) - offset
        kept.append(s)

    for i, s in enumerate(kept, start=1):
        s.index = i

    Path(srt_path).write_text(srt.compose(kept), encoding="utf-8")


_NON_LANGUAGE_KEYS = {"live_chat"}  # YouTube 有時會把「直播聊天室回放」也列在字幕語言清單裡,要排除


def _pick_caption_language(
    manual: dict, auto: dict, language: str | None, original_lang: str | None
) -> tuple[str, str] | None:
    """決定要抓哪個語言/來源的字幕。

    優先序:1) 指定的 --language;2) 影片偵測到的原始語言(manual 優先於 auto);
    3) 都沒有的話,退回「隨便挑一個有的」(manual 優先於 auto)。
    """
    manual = {k: v for k, v in manual.items() if k not in _NON_LANGUAGE_KEYS}
    auto = {k: v for k, v in auto.items() if k not in _NON_LANGUAGE_KEYS}

    if language:
        if language in manual:
            return language, "manual"
        if language in auto:
            return language, "auto"
        return None

    if original_lang:
        if original_lang in manual:
            return original_lang, "manual"
        if original_lang in auto:
            return original_lang, "auto"

    if manual:
        return next(iter(manual)), "manual"
    if auto:
        return next(iter(auto)), "auto"
    return None


def download_youtube_captions(
    url: str,
    output_dir: str,
    stem: str,
    language: str | None = None,
    start: float | None = None,
    end: float | None = None,
) -> str | None:
    """嘗試下載 YouTube 內建字幕(CC)。

    語言選擇優先序:--language 指定的語言 > 影片本身的原始語言(避免抓到英文等其他語言的翻譯字幕) > 隨便挑一個有的。
    人工上傳字幕優先於自動產生字幕。找不到任何字幕時回傳 None(呼叫端應該改跑 Whisper 辨識)。
    start/end 用來對齊 download_youtube 剪出來的秒數區間。
    """
    import yt_dlp

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    opts = {"skip_download": True, "quiet": True, "remote_components": _REMOTE_COMPONENTS}
    if _JS_RUNTIMES:
        opts["js_runtimes"] = _JS_RUNTIMES
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    original_lang = info.get("language")

    picked = _pick_caption_language(manual, auto, language, original_lang)
    if not picked:
        if language:
            print(f"[download] 找不到語言 {language} 的 YouTube 字幕")
        else:
            print("[download] 這部影片沒有 YouTube 字幕(CC)")
        return None
    lang, source = picked

    origin_note = f",影片偵測原始語言: {original_lang}" if original_lang and original_lang != lang else ""
    print(f"[download] 找到 YouTube 字幕: {lang} ({'人工上傳' if source == 'manual' else '自動產生'}){origin_note}")

    ffmpeg_path = find_ffmpeg()
    video_id = info["id"]
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": source == "manual",
        "writeautomaticsub": source == "auto",
        "subtitleslangs": [lang],
        "subtitlesformat": "vtt",
        "outtmpl": str(out / "%(id)s.%(ext)s"),
        "remote_components": _REMOTE_COMPONENTS,
    }
    if _JS_RUNTIMES:
        ydl_opts["js_runtimes"] = _JS_RUNTIMES
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    downloaded_vtt = out / f"{video_id}.{lang}.vtt"
    if not downloaded_vtt.exists():
        print(f"[download] 字幕下載後找不到檔案: {downloaded_vtt}")
        return None

    # 注意:不能靠 yt-dlp 的 FFmpegSubtitlesConvertor postprocessor 轉檔,
    # 因為 skip_download=True 時 yt-dlp 根本不會跑 postprocessor(實測確認,不是猜的),
    # 所以字幕檔會停在 .vtt,轉檔這步要自己呼叫 ffmpeg。
    srt_path = out / f"{stem}.srt"
    result = subprocess.run(
        [ffmpeg_path, "-y", "-i", str(downloaded_vtt), str(srt_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    downloaded_vtt.unlink(missing_ok=True)
    if result.returncode != 0 or not srt_path.exists():
        print(f"[download] 字幕轉檔(vtt→srt)失敗:\n{result.stderr[-500:]}")
        return None

    if start is not None or end is not None:
        _shift_and_clip_srt(str(srt_path), start, end)

    print(f"[download] 字幕檔: {srt_path}")
    return str(srt_path)
