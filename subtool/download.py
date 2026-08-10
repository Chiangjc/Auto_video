"""下載步驟:給 YouTube videoId 或網址,下載影片(可指定只下載某段秒數區間),回傳本機檔案路徑。

移植改寫自 VideoSubtitler/subtool/download.py,拿掉字幕擷取相關邏輯,保留剪輯區間下載。
"""
import subprocess
from pathlib import Path

from .ffmpeg_utils import find_ffmpeg

# YouTube 會用 JS 挑戰驗證影片連結,yt-dlp 需要一個 JS runtime(如 Deno)加上這個挑戰求解器
# 腳本才能正確解出來;remote_components 允許 yt-dlp 在需要時自動下載這個求解器腳本(下載一次後會快取)。
_REMOTE_COMPONENTS = ["ejs:github"]

# Deno 裝好之後系統 PATH 有更新,但 Windows 這類環境變數更新不保證立即生效,
# 直接把 deno.exe 的實際路徑寫死指給 yt-dlp,完全不依賴 PATH 有沒有生效。
_DENO_EXE = str(
    Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    / "DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe" / "deno.exe"
)
_JS_RUNTIMES = {"deno": {"path": _DENO_EXE}} if Path(_DENO_EXE).exists() else None


def is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def to_url(video_id_or_url: str) -> str:
    """把 videoId 或網址統一轉成完整 YouTube 網址。"""
    return video_id_or_url if is_url(video_id_or_url) else f"https://www.youtube.com/watch?v={video_id_or_url}"


def _base_ydl_opts() -> dict:
    # 不強制指定 player_client:YouTube 三不五時會對特定 client(過去是 tv/android_vr)跑
    # DRM 或簽章實驗,寫死清單反而容易在 YouTube 改變作法後卡住(實測過:寫死
    # ["tv","android_vr","web"] 時 tv client 撞上「這個工作階段的 DRM 實驗」,
    # 觸發下載 403;拿掉 extractor_args 整個交給 yt-dlp 自己選,同一支影片改用預設選擇
    # 就正常下載,而且 yt-dlp 本身會持續跟著 YouTube 的變動更新預設邏輯,比我們手動維護
    # 的清單更耐用。
    opts = {
        "noplaylist": True,
        "remote_components": _REMOTE_COMPONENTS,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
    }
    if _JS_RUNTIMES:
        opts["js_runtimes"] = _JS_RUNTIMES
    return opts


def _resolve_downloaded_path(ydl, info, fallback_ext: str | None = None) -> Path:
    """從 yt-dlp 下載結果推算實際輸出檔案路徑(優先看 requested_downloads)。"""
    requested = info.get("requested_downloads") or []
    if requested:
        return Path(requested[0]["filepath"])
    path = Path(ydl.prepare_filename(info))
    return path.with_suffix(fallback_ext) if fallback_ext else path


def download_youtube(
    video_id_or_url: str,
    output_dir: str,
    start: float | None = None,
    end: float | None = None,
) -> str:
    """下載 YouTube 影片,回傳下載後的本機檔案路徑。

    start/end:指定只下載的秒數區間(如 start=30, end=60 只下載 00:30~01:00)。不指定則下載完整影片。

    有指定 start/end 時,畫面跟音訊分開處理:畫面靠 download_ranges 讓 ffmpeg 直連 YouTube
    伺服器剪出秒數區間(這段容易受網路狀況影響但實測畫面通常完整);音訊改成用 yt-dlp 原生
    下載器抓「整條」(受 retries/fragment_retries/socket_timeout 保護,不會被 ffmpeg 直連讀取
    遠端中斷),下載完再用本機 ffmpeg 剪出同樣的秒數區間,最後兩軌合併。
    """
    import yt_dlp

    url = to_url(video_id_or_url)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = find_ffmpeg()

    base_opts = {
        **_base_ydl_opts(),
        "merge_output_format": "mp4",
        "ffmpeg_location": str(Path(ffmpeg_path).parent),
        # 強制每次都重新下載,不能因為同名檔案存在就跳過(否則影片更新後不會抓到新版)。
        "overwrites": True,
    }

    if start is None and end is None:
        ydl_opts = {**base_opts, "format": "bv*+ba/b", "outtmpl": str(out / "%(id)s.%(ext)s")}
        print(f"[download] 下載中: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        video_path = _resolve_downloaded_path(ydl, info, fallback_ext=".mp4")
        if not video_path.exists():
            raise RuntimeError(f"下載完成但找不到輸出檔案: {video_path}")
        print(f"[download] 下載完成: {video_path}")
        return str(video_path)

    from yt_dlp.utils import download_range_func

    range_start = start or 0
    range_end = end if end is not None else float("inf")
    if range_end <= range_start:
        raise ValueError(f"end ({end}) 必須大於 start ({start})")
    end_label = f"{range_end:.0f}" if range_end != float("inf") else "end"
    label = f"{range_start:.0f}-{end_label}"
    print(f"[download] 只下載 {range_start:.0f}s ~ {end_label}s 區間(畫面剪輯、音訊抓整條後本機剪)")

    video_opts = {
        **base_opts,
        "format": "bv*/b",
        "outtmpl": str(out / f"%(id)s_{label}.video.%(ext)s"),
        "download_ranges": download_range_func(None, [(range_start, range_end)]),
        "force_keyframes_at_cuts": True,
    }
    with yt_dlp.YoutubeDL(video_opts) as ydl:
        video_info = ydl.extract_info(url, download=True)
    video_clip_path = _resolve_downloaded_path(ydl, video_info)
    video_id = video_info["id"]

    audio_opts = {**base_opts, "format": "ba/b", "outtmpl": str(out / "%(id)s.audio_full.%(ext)s")}
    print(f"[download] 下載完整音訊中(受重試保護): {url}")
    with yt_dlp.YoutubeDL(audio_opts) as ydl:
        audio_info = ydl.extract_info(url, download=True)
    full_audio_path = _resolve_downloaded_path(ydl, audio_info)

    audio_clip_path = out / f"{video_id}_{label}.audio.m4a"
    duration = None if range_end == float("inf") else range_end - range_start
    trim_cmd = [ffmpeg_path, "-y", "-ss", str(range_start)]
    if duration is not None:
        trim_cmd += ["-t", str(duration)]
    trim_cmd += ["-i", str(full_audio_path), "-vn", "-c:a", "aac", "-b:a", "192k", str(audio_clip_path)]
    result = subprocess.run(trim_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"音訊剪輯失敗:\n{result.stderr[-2000:]}")

    out_path = out / f"{video_id}_{label}.mp4"
    merge_cmd = [
        ffmpeg_path, "-y",
        "-i", str(video_clip_path), "-i", str(audio_clip_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "copy",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(merge_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"畫面音訊合併失敗:\n{result.stderr[-2000:]}")

    for p in (video_clip_path, full_audio_path, audio_clip_path):
        Path(p).unlink(missing_ok=True)

    if not out_path.exists():
        raise RuntimeError(f"下載完成但找不到輸出檔案: {out_path}")

    print(f"[download] 下載完成: {out_path}")
    return str(out_path)


def fetch_video_info(video_id_or_url: str) -> dict:
    """只讀取影片中繼資料(不下載),回傳 {id, title, channel, description}。

    這裡是 yt-dlp 自己的 extract_info,不是 YouTube Data API,不會額外消耗
    YOUTUBE_API_KEY 的每日配額(配額只有 comments.py 呼叫 commentThreads.list 時才會用到)。
    channel/description 就是這次 extract_info 順便回傳的欄位,不需要多打一次請求。
    """
    import yt_dlp

    url = to_url(video_id_or_url)
    opts = {**_base_ydl_opts(), "skip_download": True, "quiet": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "id": info["id"],
        "title": info.get("title", info["id"]),
        "channel": info.get("channel") or info.get("uploader") or "",
        "description": info.get("description") or "",
    }
