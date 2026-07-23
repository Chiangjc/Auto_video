"""步驟 3:用 ffmpeg 把繁體中文字幕燒錄(硬字幕)進影片。

mp4 等影片 → 直接在畫面上壓字幕。
mp3 等純音訊 → 產生深色背景影片,再壓上字幕(輸出仍是 mp4)。

orientation 決定輸出畫面格式:
  horizontal    — 橫式,維持原始畫面尺寸(預設)
  vertical-fill — 直式滿版,裁切左右填滿 9:16 畫面
  vertical-pad  — 直式,維持完整畫面等比縮放,上下留黑

position 決定字幕垂直位置:top(上) / middle(約畫面 2/3 高處) / bottom(下) / 2/3(比 middle 更低,
用於 vertical-pad 直式上下留黑時避免字幕擋住畫面內容)
"""
import subprocess
from pathlib import Path

from .ffmpeg_utils import find_ffmpeg, escape_filter_path, is_audio_only

DEFAULT_FONT = "Microsoft JhengHei"  # Windows 內建繁中字型(微軟正黑體)

# 字幕垂直位置對應的 (Alignment, MarginV)。
#
# 重要細節:ffmpeg 把 SRT 轉成 ASS 時,不管實際影片解析度是多少,內部一律用固定的
# 384x288 script 座標系統(這是 ffmpeg 的內建預設,不是我們設的),渲染時再等比例縮放到
# 實際畫面大小。這表示 MarginV 這種座標值都要以 288(高度基準)為準去換算,不能直接套用
# 實際影片的像素高度,不然數值會被放大好幾倍,導致字幕被推到畫面外面完全看不到。
# 也因為是等比例縮放,MarginV 用 288 為基準算出來的值,不管最後輸出是橫式還是直式都適用,
# 不需要另外偵測實際影片解析度。
#
# 另外這個版本的 ffmpeg/libass,force_style 的 Alignment 欄位吃的是「舊版 SSA」數字
# (不是常見 ASS numpad 那種 1-9),實測結果:2=下置中、6=上置中、10=中置中。
#
# middle/2-3 兩個位置的 MarginV 都是實測調出來的(用 ffmpeg 燒出畫面、Pillow 逐像素量字幕
# 位置校準),不是公式算出來的:
#   middle(MarginV=96) 大約落在畫面 64% 高的地方。
#   2/3(MarginV=40)刻意比 middle 更低、更貼近底部——這是因為 vertical-pad(直式上下留黑)
#   把原始畫面等比縮小置中後,畫面內容大約只佔整個直式畫面 34%~66% 的範圍,MarginV=96 的字幕
#   會剛好疊在畫面內容的下緣附近;MarginV=40 才能確保字幕完全落在下方黑邊裡,不會擋到畫面。
POSITIONS = ("top", "middle", "bottom", "2/3")
_POSITION_STYLE = {
    "top": (6, 10),
    "middle": (2, 96),
    "bottom": (2, 10),
    "2/3": (2, 70),
}

VERTICAL_W, VERTICAL_H = 1080, 1920
HORIZONTAL_BG_W, HORIZONTAL_BG_H = 1280, 720

ORIENTATIONS = ("horizontal", "vertical-fill", "vertical-pad")


def _to_ass_color(hex_color: str) -> str:
    """將 RRGGBB(如 'FFFFFF'、'#FFFF00')轉成 ffmpeg ASS 樣式用的 &H00BBGGRR。"""
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"顏色格式錯誤,請用 6 碼十六進位(如 FFFFFF): {hex_color}")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}"


def _build_video_filter(orientation: str, sub_filter: str) -> str:
    """依 orientation 在 subtitles 濾鏡前加上縮放/裁切/留黑,順序要放在燒字幕之前。"""
    if orientation == "vertical-fill":
        return (
            f"scale={VERTICAL_W}:{VERTICAL_H}:force_original_aspect_ratio=increase,"
            f"crop={VERTICAL_W}:{VERTICAL_H},{sub_filter}"
        )
    if orientation == "vertical-pad":
        return (
            f"scale={VERTICAL_W}:{VERTICAL_H}:force_original_aspect_ratio=decrease,"
            f"pad={VERTICAL_W}:{VERTICAL_H}:(ow-iw)/2:(oh-ih)/2:color=black,{sub_filter}"
        )
    return sub_filter


def burn_subtitles(
    input_path: str,
    srt_path: str,
    output_dir: str,
    font_size: int = 22,
    font: str = DEFAULT_FONT,
    font_color: str = "FFFFFF",
    position: str = "bottom",
    bold: bool = False,
    orientation: str = "horizontal",
    bilingual: bool = False,
) -> str:
    ffmpeg = find_ffmpeg()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if position not in POSITIONS:
        raise ValueError(f"position 只能是 {list(POSITIONS)},收到: {position}")
    if orientation not in ORIENTATIONS:
        raise ValueError(f"orientation 只能是 {list(ORIENTATIONS)},收到: {orientation}")

    suffix_parts = []
    if orientation != "horizontal":
        suffix_parts.append(orientation)
    if bilingual:
        suffix_parts.append("bilingual")
    suffix = ("." + ".".join(suffix_parts)) if suffix_parts else ""
    out_path = str(out / f"{Path(input_path).stem}.zh-TW{suffix}.mp4")

    audio_only = is_audio_only(input_path)
    alignment, margin_v = _POSITION_STYLE[position]

    style = (
        f"FontName={font},FontSize={font_size},"
        f"PrimaryColour={_to_ass_color(font_color)},"
        f"OutlineColour=&H80000000,BorderStyle=1,Outline=1,Shadow=1,"
        f"Bold={-1 if bold else 0},"
        f"Alignment={alignment},MarginV={margin_v}"
    )
    sub_filter = f"subtitles='{escape_filter_path(srt_path)}':force_style='{style}'"

    if audio_only:
        bg_w, bg_h = (VERTICAL_W, VERTICAL_H) if orientation != "horizontal" else (HORIZONTAL_BG_W, HORIZONTAL_BG_H)
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", f"color=c=0x1e1e2e:s={bg_w}x{bg_h}:r=25",
            "-i", input_path,
            "-vf", sub_filter,  # 背景已經是目標尺寸,不用再縮放/留黑
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_path,
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-i", input_path,
            "-vf", _build_video_filter(orientation, sub_filter),
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
