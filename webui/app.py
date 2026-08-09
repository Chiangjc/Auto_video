"""auto_video 本機網頁介面。

只呼叫 subtool/ 底下既有的函式,不修改 main.py / subtool/*.py。
啟動方式:
    .venv\\Scripts\\python webui\\app.py
    瀏覽器開 http://127.0.0.1:5001
"""
import os
import sys
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from flask import Flask, abort, jsonify, render_template, request, send_file  # noqa: E402

from subtool.avatars import download_avatars  # noqa: E402
from subtool.card_render import render_comment_cards  # noqa: E402
from subtool.comments import Comment, fetch_comments  # noqa: E402
from subtool.compose import SELECTION_BUFFER, compose_video, needed_comment_count, video_duration  # noqa: E402
from subtool.download import download_youtube, fetch_video_info, is_url  # noqa: E402
from subtool.filter_comments import filter_comments  # noqa: E402
from subtool.translate_comments import translate_comments  # noqa: E402

app = Flask(__name__)

OUT_DIR = PROJECT_ROOT / "output"

# 記憶體暫存每個工作階段(單人本機使用,不需要資料庫;伺服器重啟就會清空)
JOBS: dict[str, dict] = {}


def _media_url(path: str) -> str:
    rel = Path(path).resolve().relative_to(OUT_DIR.resolve())
    return "/media/" + rel.as_posix()


def _comment_to_dict(c: Comment) -> dict:
    return {
        "comment_id": c.comment_id,
        "author": c.author,
        "avatar_url": _media_url(c.avatar_path) if c.avatar_path else "",
        "text": c.text,
        "text_translated": c.text_translated,
        "like_count": c.like_count,
        "published_at": c.published_at,
    }


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
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            return jsonify(error="伺服器沒有設定 YOUTUBE_API_KEY 環境變數,請先設定後重啟服務"), 500

        data = request.get_json(force=True)
        url = (data.get("url") or "").strip()
        if not url or not is_url(url):
            return jsonify(error="請輸入有效的 YouTube 網址(需以 http:// 或 https:// 開頭)"), 400

        max_comments = int(data.get("max_comments") or 100)
        min_likes = int(data.get("min_likes") or 0)
        min_chars = int(data.get("min_chars") or 5)
        max_chars = int(data.get("max_chars") or 120)
        engine = data.get("engine") or "auto"
        start = float(data["start"]) if data.get("start") not in (None, "") else None
        end = float(data["end"]) if data.get("end") not in (None, "") else None
        card_duration = float(data.get("card_duration") or 3.0)
        start_offset = float(data.get("start_offset") or 1.0)

        info = fetch_video_info(url)
        video_path = download_youtube(url, str(OUT_DIR), start=start, end=end)

        duration = video_duration(video_path)
        needed = needed_comment_count(duration, card_duration, start_offset)
        top_n = needed + SELECTION_BUFFER

        comments = fetch_comments(info["id"], api_key, max_results=max_comments)
        if not comments:
            return jsonify(error="沒有抓到任何留言(可能已關閉留言或影片留言數不足)"), 400

        selected = filter_comments(
            comments, top_n=top_n, min_likes=min_likes, min_chars=min_chars, max_chars=max_chars
        )
        if not selected:
            return jsonify(error="篩選後沒有留言符合條件,請放寬讚數/字數門檻"), 400

        selected = translate_comments(selected, engine=engine)
        selected = download_avatars(selected, str(OUT_DIR / "avatars"))

        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "video_path": video_path,
            "comments": selected,
            "title": info["title"],
            "card_duration": card_duration,
            "start_offset": start_offset,
        }

        return jsonify(
            job_id=job_id,
            video_url=_media_url(video_path),
            title=info["title"],
            comments=[_comment_to_dict(c) for c in selected],
            needed_count=needed,
            pool_count=len(selected),
        )
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route("/api/compose", methods=["POST"])
def api_compose():
    try:
        data = request.get_json(force=True)
        job = JOBS.get(data.get("job_id", ""))
        if not job:
            return jsonify(error="找不到這個工作階段,請重新開始(伺服器可能已重啟)"), 400

        edits = {c["comment_id"]: c for c in data.get("comments", [])}
        chosen: list[Comment] = []
        for c in job["comments"]:
            edit = edits.get(c.comment_id)
            if not edit or not edit.get("selected", True):
                continue
            c.text_translated = edit.get("text_translated", c.text_translated)
            chosen.append(c)

        if not chosen:
            return jsonify(error="至少要選擇一則留言才能合成影片"), 400

        bilingual = bool(data.get("bilingual"))
        title = (data.get("title") or "").strip() or None

        card_pngs = render_comment_cards(
            chosen, str(OUT_DIR / "cards" / data["job_id"]), bilingual=bilingual
        )

        output_path = compose_video(
            job["video_path"],
            card_pngs,
            str(OUT_DIR),
            card_duration=job["card_duration"],
            start_offset=job["start_offset"],
            title=title,
        )

        return jsonify(output_path=output_path, video_url=_media_url(output_path))
    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True, threaded=True)
