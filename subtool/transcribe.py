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
        # 放寬 VAD 靈敏度(預設 threshold=0.5、min_silence_duration_ms=2000):
        # threshold 調低會讓比較小聲/不確定的片段也被判斷成語音,不會整段被當成靜音直接跳過不辨識;
        # min_silence_duration_ms 調低則減少把連續句子誤合併成一大段的情況。
        # 副作用是可能連帶抓進一些背景音/雜音,如果反而出現變多的雜訊句子,可以再往回調。
        vad_parameters={"threshold": 0.35, "min_silence_duration_ms": 1000},
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
