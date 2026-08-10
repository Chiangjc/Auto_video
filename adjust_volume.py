"""獨立音量調整工具。

不依賴 main.py / webui 的產片流程,可直接對任何已完成的影片檔案調整音量。

用法範例:
    python adjust_volume.py in.mp4                      # 自動正規化到 -14 LUFS(YouTube 標準)
    python adjust_volume.py in.mp4 --gain 8              # 直接加大 8 dB
    python adjust_volume.py in.mp4 --factor 2.5           # 音量放大 2.5 倍
    python adjust_volume.py in.mp4 -o out.mp4 --gain 6
    python adjust_volume.py a.mp4 b.mp4 c.mp4             # 批次處理多個檔案
"""
import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subtool.ffmpeg_utils import find_ffmpeg  # noqa: E402


def detect_volume(ffmpeg: str, input_path: str) -> tuple[float, float]:
    """回傳 (mean_volume, max_volume),單位 dB。僅供顯示參考用。"""
    result = subprocess.run(
        [ffmpeg, "-i", input_path, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    mean = max_ = None
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            m = re.search(r"(-?\d+\.?\d*) dB", line)
            if m:
                mean = float(m.group(1))
        elif "max_volume:" in line:
            m = re.search(r"(-?\d+\.?\d*) dB", line)
            if m:
                max_ = float(m.group(1))
    if mean is None or max_ is None:
        raise RuntimeError("無法偵測音量,請確認檔案含有音訊軌。")
    return mean, max_


def build_output_path(input_path: str) -> str:
    p = Path(input_path)
    return str(p.with_name(f"{p.stem}_loud{p.suffix}"))


def adjust_one(ffmpeg: str, input_path: str, output_path: str, args) -> None:
    print(f"\n[{Path(input_path).name}]")
    mean_volume, max_volume = detect_volume(ffmpeg, input_path)
    print(f"  目前音量:平均 {mean_volume:.1f} dB,峰值 {max_volume:.1f} dB")

    if args.gain is not None:
        af = f"volume={args.gain}dB"
        print(f"  套用固定增益:{args.gain:+.1f} dB")
    elif args.factor is not None:
        gain_db = 20 * math.log10(args.factor)
        af = f"volume={args.factor}"
        print(f"  套用倍率:{args.factor}x(約 {gain_db:+.1f} dB)")
    else:
        target = args.target_lufs
        af = f"loudnorm=I={target}:TP=-1.5:LRA=11"
        print(f"  自動正規化至 {target} LUFS")

    cmd = [
        ffmpeg, "-y", "-i", input_path,
        "-af", af,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print("  ffmpeg 執行失敗:")
        print("  " + result.stderr[-1500:])
        sys.exit(1)
    print(f"  完成 -> {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="獨立音量調整工具,可直接對已完成的影片調整音量,不需重跑產片流程。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("inputs", nargs="+", help="輸入影片路徑(可多個,批次處理)")
    parser.add_argument("-o", "--output", help="輸出路徑(僅單一輸入檔時可用;預設在原檔名加上 _loud)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--gain", type=float, help="直接調整音量,單位 dB,正數放大、負數縮小")
    group.add_argument("--factor", type=float, help="音量倍率,例如 2.0 代表放大兩倍")
    parser.add_argument("--target-lufs", type=float, default=-14.0,
                         help="未指定 --gain/--factor 時,自動正規化到此響度(LUFS),預設 -14(YouTube 標準)")
    args = parser.parse_args()

    if args.output and len(args.inputs) > 1:
        print("錯誤:-o/--output 只能用於單一輸入檔,批次處理時請省略 -o。")
        sys.exit(1)

    ffmpeg = find_ffmpeg()

    for input_path in args.inputs:
        resolved = str(Path(input_path).resolve())
        if not Path(resolved).exists():
            print(f"找不到檔案:{resolved}")
            sys.exit(1)
        output_path = args.output if args.output else build_output_path(resolved)
        adjust_one(ffmpeg, resolved, output_path, args)


if __name__ == "__main__":
    main()
