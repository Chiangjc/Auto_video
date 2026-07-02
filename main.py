"""VideoSubtitler — 本地影片/音訊 → 字幕 → 繁體中文 → 燒錄字幕影片

用法:
  python main.py <影片或音訊檔> [選項]

選項:
  --model  tiny|base|small|medium|large-v3   Whisper 模型大小 (預設 small)
  --engine auto|google|claude|opencc          翻譯引擎 (預設 auto)
  --language <code>                           強制指定來源語言 (如 en, ja, zh)
  --steps  transcribe,translate,burn          要執行的步驟 (預設全部)
  --output-dir <dir>                          輸出資料夾 (預設 output)
  --font-size <n>                             燒錄字幕字級 (預設 22)
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from subtool.transcribe import transcribe
from subtool.translate import translate_srt
from subtool.burn import burn_subtitles


def main() -> int:
    parser = argparse.ArgumentParser(description="影片轉字幕 + 繁中翻譯 + 字幕燒錄")
    parser.add_argument("input", help="輸入影片或音訊檔 (mp4/mp3/...)")
    parser.add_argument("--model", default="small")
    parser.add_argument("--engine", default="auto", choices=["auto", "google", "claude", "opencc"])
    parser.add_argument("--language", default=None)
    parser.add_argument("--steps", default="transcribe,translate,burn")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--font-size", type=int, default=22)
    args = parser.parse_args()

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
        burn_subtitles(input_path, zh_srt_path, out_dir, font_size=args.font_size)

    print("\n完成!輸出檔案都在", Path(out_dir).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
