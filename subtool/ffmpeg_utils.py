"""ffmpeg 定位工具:優先使用專案內 tools/,其次系統 PATH。"""
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _find_local(name: str) -> str | None:
    """在 tools/ 底下找 name(ffmpeg / ffprobe),支援各平台的擺法:
    tools/ffmpeg、tools/bin/ffmpeg、tools/ffmpeg-*/bin/ffmpeg(.exe 亦可)。
    """
    tools = PROJECT_ROOT / "tools"
    patterns = [name, f"{name}.exe", f"bin/{name}", f"bin/{name}.exe",
                f"*/bin/{name}", f"*/bin/{name}.exe"]
    for pat in patterns:
        for hit in sorted(tools.glob(pat)):
            if hit.is_file():
                return str(hit)
    return None


def find_ffmpeg() -> str:
    return _find_local("ffmpeg") or shutil.which("ffmpeg") or _raise("ffmpeg")


def find_ffprobe() -> str:
    return _find_local("ffprobe") or shutil.which("ffprobe") or _raise("ffprobe")


def _raise(name: str):
    raise FileNotFoundError(
        f"找不到 {name}。請將 ffmpeg 解壓到 tools/ 資料夾,或安裝後加入 PATH。"
    )


def escape_filter_path(path: str) -> str:
    """將 Windows 路徑轉為 ffmpeg filter 可接受的格式。"""
    p = path.replace("\\", "/")
    p = p.replace(":", "\\:")
    return p
