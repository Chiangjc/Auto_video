"""VideoSubtitler 本機網頁介面。

只呼叫 subtool/ 底下既有的函式,不修改任何原本的 CLI 程式碼(main.py / subtool/*.py)。
啟動方式:
    .venv\\Scripts\\python webui\\app.py
    瀏覽器開 http://127.0.0.1:5000
"""
import datetime
import subprocess
import sys
import uuid
from pathlib import Path

import srt
from flask import Flask, jsonify, request, send_file, render_template, abort
from werkzeug.utils import secure_filename

# subtool/* 裡的 print() 常常會印出辨識到的原文(可能是韓文、日文等非中文字元),
# Windows 主控台預設編碼(如 cp950)無法顯示這些字元會直接讓程式崩潰,跟 main.py 用一樣的作法修掉。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from subtool.download import (  # noqa: E402
    download_youtube,
    download_youtube_captions,
    get_most_replayed_range,
    is_url,
)
from subtool.ffmpeg_utils import find_ffmpeg, is_audio_only  # noqa: E402
from subtool.transcribe import transcribe  # noqa: E402
from subtool.translate import translate_srt, build_bilingual_srt  # noqa: E402
from subtool.burn import burn_subtitles  # noqa: E402

app = Flask(__name__)

OUT_DIR = PROJECT_ROOT / "output"
UPLOAD_DIR = OUT_DIR / "uploads"

# 標題預設字型:饅頭黑體(使用者本機已安裝,這裡直接指到實際字型檔,
# 因為 ffmpeg drawtext 在這個環境沒有 fontconfig,只能吃 fontfile 路徑,不能只給字型名稱)
DEFAULT_TITLE_FONTFILE = str(
    Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts" / "MantouSans-Regular.ttf"
)

# 記憶體暫存每個工作階段(單人本機使用,不需要資料庫;伺服器重啟就會清空)
JOBS: dict[str, dict] = {}


def _media_url(path: str) -> str:
    rel = Path(path).resolve().relative_to(OUT_DIR.resolve())
    return "/media/" + rel.as_posix()


def _trim_video(input_path: str, start: float, end: float, out_path: str) -> None:
    """把 input_path 剪出 [start, end] 這段,存到 out_path(重新編碼,確保剪得準)。"""
    ffmpeg = find_ffmpeg()
    duration = end - start
    cmd = [ffmpeg, "-y", "-ss", str(start), "-i", input_path, "-t", str(duration)]
    if is_audio_only(input_path):
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
    cmd.append(out_path)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 剪輯片段失敗:\n{result.stderr[-2000:]}")


def _trim_srt(srt_path: str, start: float, end: float, out_path: str) -> None:
    """把字幕時間軸裁切並平移,對齊 _trim_video 剪出來的 [start, end] 片段。"""
    offset = datetime.timedelta(seconds=start)
    range_end = datetime.timedelta(seconds=end)
    subs = list(srt.parse(Path(srt_path).read_text(encoding="utf-8")))
    kept = []
    for s in subs:
        if s.end <= offset or s.start >= range_end:
            continue
        s.start = max(s.start - offset, datetime.timedelta(0))
        s.end = min(s.end, range_end) - offset
        kept.append(s)
    for i, s in enumerate(kept, start=1):
        s.index = i
    Path(out_path).write_text(srt.compose(kept), encoding="utf-8")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/media/<path:relpath>")
def media(relpath):
    target = (OUT_DIR / relpath).resolve()
    if OUT_DIR.resolve() not in target.parents:
        abort(403)
    if not target.exists():
        abort(404)
    return send_file(target)


@app.route("/api/prepare", methods=["POST"])
def api_prepare():
    try:
        form = request.form
        mode = form.get("mode")
        captions = form.get("captions", "auto")
        model = form.get("model", "small")
        engine = form.get("engine", "auto")
        language = (form.get("language") or "").strip() or None

        youtube_url = None
        if mode == "url":
            url = (form.get("url") or "").strip()
            if not url or not is_url(url):
                return jsonify(error="請輸入有效的網址(需以 http:// 或 https:// 開頭)"), 400
            youtube_url = url

            start = form.get("start")
            end = form.get("end")
            start = float(start) if start else None
            end = float(end) if end else None

            if form.get("most_replayed") == "1":
                peak = get_most_replayed_range(url)
                if peak:
                    start, end = peak
                else:
                    print("[webui] 這部影片沒有「最多人重播」熱度圖資料")

            input_path = download_youtube(url, str(OUT_DIR), start=start, end=end)
        else:
            uploaded = request.files.get("file")
            if not uploaded or not uploaded.filename:
                return jsonify(error="請選擇要上傳的影片/音訊檔"), 400
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = secure_filename(uploaded.filename)
            input_path = str(UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}")
            uploaded.save(input_path)

        stem = Path(input_path).stem

        cc_path = None
        if youtube_url and captions in ("auto", "youtube"):
            cc_path = download_youtube_captions(
                youtube_url, str(OUT_DIR), stem, language=language,
                start=start if youtube_url else None, end=end if youtube_url else None,
            )
            if not cc_path and captions == "youtube":
                return jsonify(error="找不到 YouTube 字幕(CC),請改用「auto」或「whisper」字幕來源"), 400

        if cc_path:
            srt_path = cc_path
        else:
            srt_path, _ = transcribe(input_path, str(OUT_DIR), model_size=model, language=language)

        zh_srt_path = translate_srt(srt_path, str(OUT_DIR), engine=engine)

        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "input_path": input_path,
            "srt_path": srt_path,
            "zh_srt_path": zh_srt_path,
        }

        return jsonify(
            job_id=job_id,
            video_url=_media_url(input_path),
            original_text=Path(srt_path).read_text(encoding="utf-8"),
            zh_text=Path(zh_srt_path).read_text(encoding="utf-8"),
        )
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route("/api/burn", methods=["POST"])
def api_burn():
    try:
        data = request.get_json(force=True)
        job = JOBS.get(data.get("job_id", ""))
        if not job:
            return jsonify(error="找不到這個工作階段,請重新開始(伺服器可能已重啟)"), 400

        Path(job["srt_path"]).write_text(data.get("original_text", ""), encoding="utf-8")
        Path(job["zh_srt_path"]).write_text(data.get("zh_text", ""), encoding="utf-8")

        burn_input_path = job["input_path"]
        burn_orig_srt = job["srt_path"]
        burn_zh_srt = job["zh_srt_path"]

        clip_start = data.get("clip_start")
        clip_end = data.get("clip_end")
        if clip_start not in (None, "") and clip_end not in (None, ""):
            clip_start, clip_end = float(clip_start), float(clip_end)
            if clip_end <= clip_start:
                return jsonify(error="片段結束時間必須大於起始時間"), 400

            job_id = data["job_id"]
            suffix = Path(job["input_path"]).suffix
            burn_input_path = str(OUT_DIR / f"clip_{job_id}{suffix}")
            burn_orig_srt = str(OUT_DIR / f"clip_{job_id}.srt")
            burn_zh_srt = str(OUT_DIR / f"clip_{job_id}.zh-TW.srt")

            _trim_video(job["input_path"], clip_start, clip_end, burn_input_path)
            _trim_srt(job["srt_path"], clip_start, clip_end, burn_orig_srt)
            _trim_srt(job["zh_srt_path"], clip_start, clip_end, burn_zh_srt)

        bilingual = bool(data.get("bilingual"))
        burn_srt_path = burn_zh_srt
        if bilingual:
            burn_srt_path = build_bilingual_srt(burn_orig_srt, burn_zh_srt, str(OUT_DIR))

        title_text = (data.get("title") or "").strip()

        output_path = burn_subtitles(
            burn_input_path,
            burn_srt_path,
            str(OUT_DIR),
            font_size=int(data.get("font_size", 16)),
            font=data.get("font") or "Microsoft JhengHei",
            font_color=(data.get("font_color") or "FFFFFF").lstrip("#"),
            position=data.get("position", "bottom"),
            bold=bool(data.get("bold")),
            orientation=data.get("orientation", "horizontal"),
            bilingual=bilingual,
            title=title_text or None,
            title_font_file=DEFAULT_TITLE_FONTFILE if title_text else None,
        )

        return jsonify(output_path=output_path, video_url=_media_url(output_path))
    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
