"""VideoSubtitler — 本地影片/音訊 → 字幕 → 繁體中文 → 燒錄字幕影片

用法:
  python main.py <影片或音訊檔> [選項]

選項:
  --model  tiny|base|small|medium|large-v3   Whisper 模型大小 (預設 small)
  --engine auto|google|claude|opencc          翻譯引擎 (預設 auto)
  --language <code>                           強制指定來源語言 (如 en, ja, zh)
  --steps  transcribe,translate,burn          要執行的步驟 (預設全部)
  --output-dir <dir>                          輸出資料夾 (預設 output)
  --font-size <n>                             燒錄字幕字級 (預設 16)
  --font <name>                                燒錄字幕字型 (預設 Microsoft JhengHei)
  --font-color <hex>                           燒錄字幕顏色,6碼十六進位 (預設 FFFFFF 白色)
  --position top|middle|bottom|2/3             燒錄字幕位置 (預設 bottom;middle約2/3高、2/3更低,適合直式上下留黑)
  --bold                                       燒錄字幕是否加粗
  --start <秒>                                  YouTube 下載區間起點(秒)
  --end <秒>                                    YouTube 下載區間終點(秒)
  --most-replayed                               自動抓 YouTube「最多人重播」熱度最高的區間(會覆蓋 --start/--end)
  --captions auto|youtube|whisper              字幕來源 (預設 auto)
  --orientation horizontal|vertical-fill|vertical-pad  輸出畫面格式 (預設 horizontal)
  --bilingual                                   輸出雙語字幕(原文+繁中)
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from subtool.download import download_youtube, download_youtube_captions, get_most_replayed_range, is_url
from subtool.transcribe import transcribe
from subtool.translate import translate_srt, build_bilingual_srt
from subtool.burn import burn_subtitles


def main() -> int:
    parser = argparse.ArgumentParser(description="影片轉字幕 + 繁中翻譯 + 字幕燒錄")
    parser.add_argument("input", help="輸入影片或音訊檔 (mp4/mp3/...),或 YouTube 網址")
    parser.add_argument("--model", default="small")
    parser.add_argument("--engine", default="auto", choices=["auto", "google", "claude", "opencc"])
    parser.add_argument("--language", default=None)
    parser.add_argument("--steps", default="transcribe,translate,burn")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--font-size", type=int, default=16)
    parser.add_argument("--font", default="LXGW WenKai TC")
    parser.add_argument("--font-color", default="FFFFFF")
    parser.add_argument(
        "--position",
        default="bottom",
        choices=["top", "middle", "bottom", "2/3"],
        help="字幕垂直位置: top / middle(約畫面2/3高) / bottom(預設) / 2/3(比middle更低,適合直式上下留黑避免擋住畫面內容)",
    )
    parser.add_argument("--bold", action="store_true")
    parser.add_argument("--start", type=float, default=None, help="YouTube 下載區間起點(秒)")
    parser.add_argument("--end", type=float, default=None, help="YouTube 下載區間終點(秒)")
    parser.add_argument(
        "--most-replayed",
        action="store_true",
        help="自動抓 YouTube「最多人重播」熱度最高的區間下載(只對YouTube網址有效,會覆蓋 --start/--end)",
    )
    parser.add_argument(
        "--captions",
        default="auto",
        choices=["auto", "youtube", "whisper"],
        help="字幕來源: auto=優先用YouTube CC,沒有再用Whisper辨識 / youtube=強制用YouTube CC / whisper=強制用Whisper辨識",
    )
    parser.add_argument(
        "--orientation",
        default="horizontal",
        choices=["horizontal", "vertical-fill", "vertical-pad"],
        help="輸出畫面格式: horizontal=橫式(預設) / vertical-fill=直式滿版裁切 / vertical-pad=直式上下留黑",
    )
    parser.add_argument("--bilingual", action="store_true", help="輸出雙語字幕(原文在上、繁中在下)")
    args = parser.parse_args()

    youtube_url = args.input if is_url(args.input) else None
    start, end = args.start, args.end

    if youtube_url:
        if args.most_replayed:
            peak = get_most_replayed_range(youtube_url)
            if peak:
                start, end = peak
                print(f"[main] 使用最多人重播區間: {start:.0f}s ~ {end:.0f}s")
            else:
                print("[main] 這部影片沒有「最多人重播」熱度圖資料,改用 --start/--end 或下載完整影片")
        input_path = download_youtube(args.input, args.output_dir, start=start, end=end)
    else:
        if args.start is not None or args.end is not None or args.most_replayed:
            print("[main] 提醒: --start/--end/--most-replayed 只對 YouTube 網址有效,本地檔案會忽略此設定")
        input_path = str(Path(args.input).resolve())
        if not Path(input_path).exists():
            print(f"找不到輸入檔: {input_path}")
            return 1

    steps = [s.strip() for s in args.steps.split(",")]
    out_dir = args.output_dir
    stem = Path(input_path).stem

    srt_path = str(Path(out_dir) / f"{stem}.srt")
    zh_srt_path = str(Path(out_dir) / f"{stem}.zh-TW.srt")

    if "transcribe" in steps:
        cc_path = None
        if youtube_url and args.captions in ("auto", "youtube"):
            cc_path = download_youtube_captions(
                youtube_url, out_dir, stem, language=args.language, start=start, end=end
            )
            if not cc_path and args.captions == "youtube":
                print("[main] 找不到 YouTube 字幕(CC),請改用 --captions auto 或 whisper")
                return 1

        if cc_path:
            srt_path = cc_path
        else:
            srt_path, _ = transcribe(input_path, out_dir, model_size=args.model, language=args.language)

    if "translate" in steps:
        if not Path(srt_path).exists():
            print(f"找不到字幕檔 {srt_path},請先執行 transcribe 步驟")
            return 1
        zh_srt_path = translate_srt(srt_path, out_dir, engine=args.engine)

    if "burn" in steps:
        if not Path(zh_srt_path).exists():
            print(f"找不到繁中字幕 {zh_srt_path},請先執行 translate 步驟")
            return 1

        burn_srt_path = zh_srt_path
        if args.bilingual:
            if not Path(srt_path).exists():
                print(f"雙語字幕需要原文字幕 {srt_path},請先執行 transcribe 步驟(或用 YouTube CC)")
                return 1
            burn_srt_path = build_bilingual_srt(srt_path, zh_srt_path, out_dir)

        burn_subtitles(
            input_path,
            burn_srt_path,
            out_dir,
            font_size=args.font_size,
            font=args.font,
            font_color=args.font_color,
            position=args.position,
            bold=args.bold,
            orientation=args.orientation,
            bilingual=args.bilingual,
        )

    print("\n完成!輸出檔案都在", Path(out_dir).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
