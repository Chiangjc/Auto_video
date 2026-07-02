"""步驟 3:用 ffmpeg 把繁體中文字幕燒錄(硬字幕)進影片。

mp4 等影片 → 直接在畫面上壓字幕。
mp3 等純音訊 → 產生深色背景影片,再壓上字幕(輸出仍是 mp4)。
"""
import subprocess
from pathlib import Path

from .ffmpeg_utils import find_ffmpeg, escape_filter_path, is_audio_only

FONT = "Microsoft JhengHei"  # Windows 內建繁中字型(微軟正黑體)


def burn_subtitles(
    input_path: str,
    srt_path: str,
    output_dir: str,
    font_size: int = 22,
) -> str:
    ffmpeg = find_ffmpeg()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    out_path = str(out / f"{Path(input_path).stem}.zh-TW.mp4")

    style = f"FontName={FONT},FontSize={font_size},OutlineColour=&H80000000,BorderStyle=1,Outline=1,Shadow=1"
    sub_filter = f"subtitles='{escape_filter_path(srt_path)}':force_style='{style}'"

    if is_audio_only(input_path):
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", "color=c=0x1e1e2e:s=1280x720:r=25",
            "-i", input_path,
            "-vf", sub_filter,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_path,
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-i", input_path,
            "-vf", sub_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy",
            out_path,
        ]

    print(f"[burn] 執行: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 燒錄失敗:\n{result.stderr[-2000:]}")

    print(f"[burn] 輸出影片: {out_path}")
    return out_path
