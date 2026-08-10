"""步驟 6:輸出固定 9:16 畫布——上方標題、中間影片置中裁切成正方形、下方疊留言卡片。

filter_complex 串接手法比照 VideoSubtitler/subtool/burn.py 的 _FilterGraph 概念。

版面配置(由上到下,標題文字位置與留言卡片位置為固定值,互不相依):
  標題文字固定貼在畫面上緣附近 → 正方形影片區(1080x1080,滿版寬,來源影片置中裁切成
  正方形)→ 留言卡片固定貼在畫面下方。影片區塊往上移到剛好貼齊留言卡片上緣(中間留
  CARD_GAP_BELOW_VIDEO 的間距),不會因為改變影片尺寸而擠壓到標題或留言的位置。
"""
import subprocess
import uuid
from pathlib import Path

from .ffmpeg_utils import escape_filter_path, find_ffmpeg, find_ffprobe

# 標題預設字型:饅頭黑體。ffmpeg drawtext 在這個環境沒有 fontconfig,只能吃 fontfile 路徑,
# 不能只給字型名稱。找不到時退回 Windows 內建的微軟正黑體(粗體)。
_DEFAULT_TITLE_FONTFILE = str(
    Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts" / "MantouSans-Regular.ttf"
)
_FALLBACK_TITLE_FONTFILE = r"C:\Windows\Fonts\msjhbd.ttc"

CANVAS_W, CANVAS_H = 1080, 1920
VIDEO_BLOCK = 1080  # 影片置中裁切成正方形後的邊長,滿版寬
VIDEO_X_OFFSET = (CANVAS_W - VIDEO_BLOCK) // 2
TITLE_MARGIN_WITH_TITLE = 520  # 有標題時,標題文字所在區塊的高度(只用來算標題文字 y 位置)
TITLE_MARGIN_NO_TITLE = 80  # 沒有標題時,標題區塊高度(此時沒有文字,純粹當作預留頂部留白)
CARD_GAP_BELOW_VIDEO = 10  # 留言卡片與影片區塊下緣的間距,盡量貼近影片
# 留言卡片固定貼在畫面的絕對位置,不隨 VIDEO_BLOCK 改變而跟著移動
# (數值取自先前版本 860px 影片時算出來的位置,維持留言在畫面上的視覺位置不變)。
CARD_Y_WITH_TITLE = TITLE_MARGIN_WITH_TITLE + 860 + CARD_GAP_BELOW_VIDEO
CARD_Y_NO_TITLE = TITLE_MARGIN_NO_TITLE + 860 + CARD_GAP_BELOW_VIDEO
TITLE_BOX_H = 200  # 標題底色實心黑底的高度,滿版寬(CANVAS_W),文字置中疊在上面


def default_title_font_file() -> str | None:
    if Path(_DEFAULT_TITLE_FONTFILE).exists():
        return _DEFAULT_TITLE_FONTFILE
    if Path(_FALLBACK_TITLE_FONTFILE).exists():
        return _FALLBACK_TITLE_FONTFILE
    return None


def video_duration(video_path: str) -> float:
    ffprobe = find_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return float(result.stdout.strip())


SELECTION_BUFFER = 5  # 篩選時多留幾則候選,讓使用者在正式數量之外還有挑選餘裕


def needed_comment_count(duration: float, card_duration: float, start_offset: float) -> int:
    """留言連續播放、每則固定 card_duration 秒,回傳影片可以完整播完幾則(除不盡的零頭秒數捨棄不用)。"""
    usable = duration - start_offset
    if usable <= 0:
        return 0
    return int(usable // card_duration)


def compose_video(
    video_path: str,
    card_pngs: list[str],
    output_dir: str,
    card_duration: float = 3.0,
    gap: float = 0.0,
    start_offset: float = 1.0,
    title: str | None = None,
    title_font_file: str | None = None,
) -> str:
    """輸出固定 1080x1920(9:16)影片:來源影片置中裁切成正方形放在標題下方,
    留言卡片依序疊在影片區塊下緣(水平置中),每則顯示 card_duration 秒。gap 預設 0
    (連續播放、留言之間無間隔),需要留白時可自行調高。

    留言卡片時間軸超出影片長度時,超出的部分自然不會顯示出來(ffmpeg 只會播到影片結尾),
    可搭配 needed_comment_count() 事先算好要用幾則留言,除不盡的零頭秒數自然捨棄。
    """
    if not card_pngs:
        raise ValueError("card_pngs 不能是空清單")

    ffmpeg = find_ffmpeg()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    out_path = str(out / f"{Path(video_path).stem}.commented.mp4")

    duration = video_duration(video_path)
    timeline = []
    t = start_offset
    for png in card_pngs:
        if t >= duration:
            print(f"[compose] 影片長度不足,{png} 之後的留言卡片將不會顯示")
            break
        timeline.append((png, t, min(t + card_duration, duration)))
        t += card_duration + gap

    title_margin = TITLE_MARGIN_WITH_TITLE if title else TITLE_MARGIN_NO_TITLE
    card_y = CARD_Y_WITH_TITLE if title else CARD_Y_NO_TITLE

    # 影片區塊往上移到剛好貼齊留言卡片上緣(留 CARD_GAP_BELOW_VIDEO 間距),
    # 不受 title_margin 影響,讓標題/留言的位置維持固定,只有影片本身跟著置中裁切尺寸移動。
    # 如果影片比留言位置容許的空間還高(貼到畫面頂端仍會超出),改成貼齊頂端,
    # 並把留言卡片往下推到影片下緣,確保兩者一定不會重疊。
    video_y = max(0, card_y - CARD_GAP_BELOW_VIDEO - VIDEO_BLOCK)
    card_y = max(card_y, video_y + VIDEO_BLOCK + CARD_GAP_BELOW_VIDEO)

    cmd = [ffmpeg, "-y", "-i", video_path]
    for png, _, _ in timeline:
        cmd += ["-loop", "1", "-i", png]

    # 來源影片置中裁切成正方形(不論原本是橫式或直式,都取畫面正中間 min(iw,ih) 那塊),
    # 縮放到 VIDEO_BLOCK 邊長,水平置中、貼在 video_y 高度,再貼進 9:16 黑色畫布。
    filter_parts = [
        f"[0:v]crop=min(iw\\,ih):min(iw\\,ih),"
        f"scale={VIDEO_BLOCK}:{VIDEO_BLOCK},"
        f"pad={CANVAS_W}:{CANVAS_H}:{VIDEO_X_OFFSET}:{video_y}:color=black[base]"
    ]
    cur = "base"
    for i, (_, t_start, t_end) in enumerate(timeline):
        input_idx = i + 1
        label = f"c{i}"
        filter_parts.append(
            f"[{cur}][{input_idx}:v]overlay="
            f"x=(main_w-overlay_w)/2:y={card_y}:"
            f"enable='between(t,{t_start:.3f},{t_end:.3f})'[{label}]"
        )
        cur = label

    title_textfile = None
    if title:
        font_file = title_font_file or default_title_font_file()
        if not font_file:
            raise ValueError("找不到可用的標題字型檔,請透過 title_font_file 指定")
        title_textfile = out / f"_title_{uuid.uuid4().hex}.txt"
        title_textfile.write_text(title, encoding="utf-8")

        # 標題底色改成滿版寬(CANVAS_W)、不透明的實心黑底,而不是 drawtext 自己那種
        # 只貼合文字寬度的半透明底框,所以先畫一塊獨立的實心黑色矩形,文字再置中疊上去。
        box_y = title_margin // 2 - TITLE_BOX_H // 2
        box_label = "titlebox"
        filter_parts.append(f"[{cur}]drawbox=x=0:y={box_y}:w={CANVAS_W}:h={TITLE_BOX_H}:color=black@1.0:t=fill[{box_label}]")
        cur = box_label

        label = "title"
        filter_parts.append(
            f"[{cur}]drawtext=fontfile='{escape_filter_path(font_file)}':"
            f"textfile='{escape_filter_path(str(title_textfile))}':"
            "fontcolor=white:fontsize=56:"
            f"text_align=center:line_spacing=8:x=(w-text_w)/2:y={title_margin}/2-text_h/2[{label}]"
        )
        cur = label

    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{cur}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        "-shortest",
        out_path,
    ]

    try:
        print(f"[compose] 執行: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 合成失敗:\n{result.stderr[-2000:]}")
    finally:
        if title_textfile:
            title_textfile.unlink(missing_ok=True)

    print(f"[compose] 輸出影片: {out_path}")
    return out_path
