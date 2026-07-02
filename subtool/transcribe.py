"""步驟 1:用 faster-whisper 將影片/音訊轉成字幕 (.srt) 與純文字 (.txt)。"""
import datetime
from pathlib import Path

import srt


def transcribe(
    input_path: str,
    output_dir: str,
    model_size: str = "small",
    language: str | None = None,
) -> tuple[str, str]:
    """回傳 (srt_path, txt_path)。"""
    from faster_whisper import WhisperModel

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(input_path).stem

    print(f"[transcribe] 載入 Whisper 模型 ({model_size}) ...")
    model = WhisperModel(model_size, device="auto", compute_type="auto")

    print(f"[transcribe] 辨識中: {input_path}")
    segments, info = model.transcribe(
        input_path,
        beam_size=5,
        vad_filter=True,
        language=language,
    )
    print(f"[transcribe] 偵測語言: {info.language} (信心 {info.language_probability:.2f})")

    subs = []
    lines = []
    for i, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        if not text:
            continue
        subs.append(
            srt.Subtitle(
                index=i,
                start=datetime.timedelta(seconds=seg.start),
                end=datetime.timedelta(seconds=seg.end),
                content=text,
            )
        )
        lines.append(text)
        print(f"  [{seg.start:7.2f} → {seg.end:7.2f}] {text}")

    srt_path = str(out / f"{stem}.srt")
    txt_path = str(out / f"{stem}.txt")
    Path(srt_path).write_text(srt.compose(subs), encoding="utf-8")
    Path(txt_path).write_text("\n".join(lines), encoding="utf-8")

    print(f"[transcribe] 字幕檔: {srt_path}")
    print(f"[transcribe] 文字檔: {txt_path}")
    return srt_path, txt_path
