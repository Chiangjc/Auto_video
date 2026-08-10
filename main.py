"""YouTube 留言影片自動化流程 — 批次命令列入口。

用法:
  python main.py --video-ids ID1,ID2,...  [選項]
  python main.py --input-file ids.txt      # 每行一個 videoId 或完整網址,# 開頭視為註解

選項:
  --max-comments <n>    每支影片最多抓幾則留言(供篩選用的候選池) (預設 100)
  --top-n <n>           篩選後最終選用幾則留言做成卡片;不指定則自動算(見下方說明)
  --min-likes <n>       留言讚數門檻 (預設 0)
  --min-chars <n>       留言最短字數 (預設 5)
  --max-chars <n>       留言最長字數 (預設 120)
  --engine auto|google|claude   翻譯引擎 (預設 auto)。claude 透過本機 Claude Code CLI
                                  執行,需先 `claude login`;偵測不到 CLI 時 auto 會退回 google
  --start <秒>            YouTube 下載區間起點,只對本次批次所有影片套用同一區間
  --end <秒>              YouTube 下載區間終點
  --bilingual / --no-bilingual   卡片同時顯示原文(較小字體附在翻譯下方) (預設開啟)
  --card-duration <秒>   每則留言卡片顯示秒數,留言連續播放無間隔 (預設 3)
  --start-offset <秒>     第一則留言卡片出現的時間點 (預設 1)
  --title <文字>          疊加在影片上方的標題文字,不指定則不加標題
  --normalize-audio / --no-normalize-audio  合成完後把音量正規化到 YouTube 標準響度 (預設開啟)
  --target-lufs <n>      --normalize-audio 開啟時的目標響度 (預設 -14)
  --output-dir <dir>      輸出資料夾 (預設 output)

留言連續播放,每則固定 --card-duration 秒,不指定 --top-n 時會依影片長度自動計算剛好
填滿的則數(除不盡的零頭秒數捨棄),篩選時再多留 5 則候選供事後複查。
"""
import argparse
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from subtool.audio import DEFAULT_TARGET_LUFS, normalize_audio
from subtool.avatars import download_avatars
from subtool.card_render import render_comment_cards
from subtool.comments import fetch_comments
from subtool.compose import SELECTION_BUFFER, compose_video, needed_comment_count, video_duration
from subtool.download import download_youtube, fetch_video_info
from subtool.filter_comments import filter_comments
from subtool.translate_comments import translate_comments


def _load_video_ids(args) -> list[str]:
    if args.video_ids:
        return [v.strip() for v in args.video_ids.split(",") if v.strip()]
    if args.input_file:
        lines = Path(args.input_file).read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    return []


def process_video(video_id: str, args, api_key: str) -> str:
    out_dir = args.output_dir

    info = fetch_video_info(video_id)
    real_id = info["id"]
    overlay_title = args.title or (info["title"] if args.auto_title else None)

    video_path = download_youtube(video_id, out_dir, start=args.start, end=args.end)

    if args.top_n is not None:
        top_n = args.top_n
    else:
        duration = video_duration(video_path)
        needed = needed_comment_count(duration, args.card_duration, args.start_offset)
        top_n = needed + SELECTION_BUFFER
        print(
            f"[main] 影片長度 {duration:.1f}s,每則 {args.card_duration:.1f}s 連續播放,"
            f"剛好可播完 {needed} 則,篩選時多留 {SELECTION_BUFFER} 則候選 (top_n={top_n})"
        )

    comments = fetch_comments(real_id, api_key, max_results=args.max_comments)
    if not comments:
        raise RuntimeError("沒有抓到任何留言(可能已關閉留言或影片留言數不足)")

    selected = filter_comments(
        comments,
        top_n=top_n,
        min_likes=args.min_likes,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
    )
    if not selected:
        raise RuntimeError("篩選後沒有留言符合條件,請放寬 --min-likes/--min-chars/--max-chars")

    selected = translate_comments(selected, engine=args.engine)
    selected = download_avatars(selected, str(Path(out_dir) / "avatars"))

    card_pngs = render_comment_cards(selected, str(Path(out_dir) / "cards" / real_id), bilingual=args.bilingual)

    output_path = compose_video(
        video_path,
        card_pngs,
        out_dir,
        card_duration=args.card_duration,
        start_offset=args.start_offset,
        title=overlay_title,
    )

    if args.normalize_audio:
        normalize_audio(output_path, target_lufs=args.target_lufs)

    print(f"[main] 頻道: {info['channel'] or '(未知)'}")
    description = info["description"].strip()
    if description:
        preview = description if len(description) <= 300 else description[:300] + "..."
        print(f"[main] 影片簡介:\n{preview}")

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube 留言影片自動化流程")
    parser.add_argument("--video-ids", default=None, help="逗號分隔的 videoId 或完整網址清單")
    parser.add_argument("--input-file", default=None, help="每行一個 videoId 或網址的清單檔")
    parser.add_argument("--max-comments", type=int, default=100)
    parser.add_argument(
        "--top-n", type=int, default=None,
        help="篩選後最終選用幾則留言;不指定則依影片長度自動計算(填滿所需則數 + 5 則候選)",
    )
    parser.add_argument("--min-likes", type=int, default=0)
    parser.add_argument("--min-chars", type=int, default=5)
    parser.add_argument("--max-chars", type=int, default=120)
    parser.add_argument("--engine", default="auto", choices=["auto", "google", "claude"])
    parser.add_argument("--start", type=float, default=None, help="YouTube 下載區間起點(秒)")
    parser.add_argument("--end", type=float, default=None, help="YouTube 下載區間終點(秒)")
    parser.add_argument(
        "--bilingual", action=argparse.BooleanOptionalAction, default=True,
        help="卡片同時顯示原文(較小字體附在翻譯下方) (預設開啟)",
    )
    parser.add_argument("--card-duration", type=float, default=3.0)
    parser.add_argument("--start-offset", type=float, default=1.0)
    parser.add_argument("--title", default=None, help="疊加標題文字;不指定則不加標題")
    parser.add_argument(
        "--auto-title", action="store_true",
        help="不指定 --title 時,改用影片原始標題當作疊加標題(預設不加標題)",
    )
    parser.add_argument(
        "--normalize-audio", action=argparse.BooleanOptionalAction, default=True,
        help="合成完後把音量正規化到 YouTube 標準響度 (預設開啟)",
    )
    parser.add_argument("--target-lufs", type=float, default=DEFAULT_TARGET_LUFS)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    video_ids = _load_video_ids(args)
    if not video_ids:
        print("請用 --video-ids 或 --input-file 指定至少一個 videoId")
        return 1

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("找不到環境變數 YOUTUBE_API_KEY,請先設定(見 .env.example)")
        return 1

    failures = []
    for video_id in video_ids:
        print(f"\n=== 處理 {video_id} ===")
        try:
            output_path = process_video(video_id, args, api_key)
            print(f"[main] 完成: {output_path}")
        except Exception as e:
            print(f"[main] {video_id} 處理失敗: {e}")
            failures.append(video_id)

    print(f"\n批次完成,共 {len(video_ids)} 支,失敗 {len(failures)} 支。")
    if failures:
        print("失敗清單:", ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
