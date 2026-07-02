"""ffmpeg 定位工具:優先使用專案內 tools/ffmpeg,其次系統 PATH。"""
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_ffmpeg() -> str:
    local = list((PROJECT_ROOT / "tools").glob("ffmpeg*/bin/ffmpeg.exe"))
    if local:
        return str(local[0])
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError(
        "找不到 ffmpeg。請將 ffmpeg 解壓到 tools/ 資料夾,或安裝後加入 PATH。"
    )


def escape_filter_path(path: str) -> str:
    """將 Windows 路徑轉為 ffmpeg filter 可接受的格式。"""
    p = path.replace("\\", "/")
    p = p.replace(":", "\\:")
    return p


AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}


def is_audio_only(path: str) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTS
