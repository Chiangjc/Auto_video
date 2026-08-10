"""步驟 7(選用):把合成好的影片音量正規化到 YouTube 標準響度(-14 LUFS)。

核心邏輯跟根目錄的 adjust_volume.py 自動正規化模式相同(loudnorm 濾鏡),這裡抽成
main.py / webui 產片流程最後一步可以直接呼叫的版本:原地覆蓋輸出檔案(先寫暫存檔
再替換,避免同一個檔案同時讀寫)。adjust_volume.py 本身維持獨立不變,供事後想手動
調整 --gain/--factor 或看 detect_volume 診斷數字時使用。
"""
import os
import subprocess
from pathlib import Path

from .ffmpeg_utils import find_ffmpeg

DEFAULT_TARGET_LUFS = -14.0


def normalize_audio(video_path: str, target_lufs: float = DEFAULT_TARGET_LUFS) -> str:
    """把 video_path 的音量正規化到 target_lufs,原地覆蓋,回傳同一個路徑。"""
    ffmpeg = find_ffmpeg()
    p = Path(video_path)
    tmp_path = str(p.with_name(f"{p.stem}._normalizing{p.suffix}"))

    cmd = [
        ffmpeg, "-y", "-i", video_path,
        "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        tmp_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        Path(tmp_path).unlink(missing_ok=True)
        raise RuntimeError(f"音量正規化失敗:\n{result.stderr[-2000:]}")

    os.replace(tmp_path, video_path)
    print(f"[audio] 音量已正規化至 {target_lufs} LUFS: {video_path}")
    return video_path
