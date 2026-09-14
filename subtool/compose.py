"""步驟 6:輸出固定 9:16 畫布——上方標題、中間影片置中裁切成正方形、下方疊留言卡片。

filter_complex 串接手法比照 VideoSubtitler/subtool/burn.py 的 _FilterGraph 概念。

版面配置(由上到下,標題文字位置與留言卡片位置為固定值,互不相依):
  標題文字固定貼在畫面上緣附近 → 正方形影片區(1080x1080,滿版寬,來源影片置中裁切成
  正方形)→ 留言卡片固定貼在畫面下方。影片區塊往上移到剛好貼齊留言卡片上緣(中間留
  CARD_GAP_BELOW_VIDEO 的間距),不會因為改變影片尺寸而擠壓到標題或留言的位置。
"""
import math
import subprocess
import uuid
from pathlib import Path

from .card_render import render_title_png
from .ffmpeg_utils import find_ffmpeg, find_ffprobe

# 疊加標題改用 HTML→PNG(見 card_render.render_title_png)再以 overlay 疊上,
# 不再依賴 ffmpeg 的 drawtext 濾鏡——精簡版 Homebrew ffmpeg 沒有把它編進去。
# 標題所用的饅頭黑體字型檔在 tools/fonts/,由 render_title_png 內嵌。

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
LAYOUT_Y_OFFSET = 100  # 整體版面(標題、影片、留言)一起往下位移的像素數(約 1 公分)。要微調就改這裡,0 = 不位移。


def video_duration(video_path: str) -> float:
    ffprobe = find_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return float(result.stdout.strip())


SELECTION_BUFFER = 5  # 篩選時多留幾則候選,讓使用者在正式數量之外還有挑選餘裕
MIN_TAIL_SECONDS = 3.0  # 影片尾端剩不到這麼多秒時,不再放新留言卡,改把最後一張延到片尾


def needed_comment_count(
    duration: float, card_duration: float, start_offset: float,
    min_tail: float = MIN_TAIL_SECONDS,
) -> int:
    """留言連續播放、每則固定 card_duration 秒,回傳要用幾則留言。

    規則:只要片尾還剩「超過 min_tail 秒」就再放一張新卡;剩下不到 min_tail 秒的零頭
    不放新卡(合成時會由最後一張留言卡延伸補到片尾)。至少 1 則。
    """
    usable = duration - start_offset
    if usable <= 0:
        return 0
    return max(1, math.ceil((usable - min_tail) / card_duration))


def compose_video(
    video_path: str,
    card_pngs: list[str],
    output_dir: str,
    card_duration: float = 3.0,
    gap: float = 0.0,
    start_offset: float = 1.0,
    title: str | None = None,
    title_font_file: str | None = None,
    min_tail: float = MIN_TAIL_SECONDS,
) -> str:
    """輸出固定 1080x1920(9:16)影片:來源影片置中裁切成正方形放在標題下方,
    留言卡片依序疊在影片區塊下緣(水平置中),每則顯示 card_duration 秒。gap 預設 0
    (連續播放、留言之間無間隔),需要留白時可自行調高。

    留言卡片排程:每放完一張,若片尾還剩「超過 min_tail 秒」就接著放下一張;
    剩下不到 min_tail 秒(或留言卡用完)就停手,並把最後一張留言卡的結束時間延伸到
    影片結尾,不讓片尾出現沒有留言卡的空白。
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
        remaining = duration - t
        if remaining <= 0:
            break
        # 已經放過卡、而且片尾剩不到 min_tail 秒:不再放新卡,交給下面把最後一張延到片尾
        if timeline and remaining <= min_tail:
            break
        timeline.append((png, t, min(t + card_duration, duration)))
        t += card_duration + gap

    # 最後一張留言卡一律延伸到影片結尾(片長剛好整除時是無變化;有零頭時補掉尾巴的空白)
    if timeline:
        last_png, last_start, _ = timeline[-1]
        timeline[-1] = (last_png, last_start, duration)

    title_margin = TITLE_MARGIN_WITH_TITLE if title else TITLE_MARGIN_NO_TITLE
    # 整體版面往下位移:card_y 加上位移量後,底下算出來的 video_y 會跟著往下,
    # 標題條的 box_y 另外也加同一個量,三者一起平移、相對位置不變。
    card_y = (CARD_Y_WITH_TITLE if title else CARD_Y_NO_TITLE) + LAYOUT_Y_OFFSET

    # 影片區塊往上移到剛好貼齊留言卡片上緣(留 CARD_GAP_BELOW_VIDEO 間距),
    # 不受 title_margin 影響,讓標題/留言的位置維持固定,只有影片本身跟著置中裁切尺寸移動。
    # 如果影片比留言位置容許的空間還高(貼到畫面頂端仍會超出),改成貼齊頂端,
    # 並把留言卡片往下推到影片下緣,確保兩者一定不會重疊。
    video_y = max(0, card_y - CARD_GAP_BELOW_VIDEO - VIDEO_BLOCK)
    card_y = max(card_y, video_y + VIDEO_BLOCK + CARD_GAP_BELOW_VIDEO)

    # 疊加標題:先用 HTML→PNG 產生「滿版黑底白字」的標題條(不用 ffmpeg 的 drawtext,
    # 因為精簡版 Homebrew ffmpeg 沒有編進 drawtext/freetype),稍後以 overlay 疊上去。
    title_png = None
    if title:
        title_png = out / f"_title_{uuid.uuid4().hex}.png"
        render_title_png(title, str(title_png), width=CANVAS_W, height=TITLE_BOX_H, font_size=56)

    cmd = [ffmpeg, "-y", "-i", video_path]
    for png, _, _ in timeline:
        cmd += ["-loop", "1", "-i", png]
    if title_png:
        cmd += ["-loop", "1", "-i", str(title_png)]

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

    if title_png:
        # 標題條 PNG 已是滿版寬、實心黑底,直接疊在原本 drawbox 的位置(垂直置中於標題區)。
        title_idx = len(timeline) + 1
        box_y = title_margin // 2 - TITLE_BOX_H // 2 + LAYOUT_Y_OFFSET
        filter_parts.append(f"[{cur}][{title_idx}:v]overlay=x=0:y={box_y}[titled]")
        cur = "titled"

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
        if title_png:
            title_png.unlink(missing_ok=True)

    print(f"[compose] 輸出影片: {out_path}")
    return out_path
