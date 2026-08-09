"""步驟 4:下載留言作者頭像圖片,供留言卡片圖使用。"""
from pathlib import Path

import requests

from .comments import Comment


def download_avatars(comments: list[Comment], avatar_dir: str) -> list[Comment]:
    """下載每則留言的頭像,補上 avatar_path 欄位。單則下載失敗不中斷,留空路徑讓卡片改用預設頭像。"""
    out = Path(avatar_dir)
    out.mkdir(parents=True, exist_ok=True)

    for c in comments:
        if not c.avatar_url:
            continue
        ext = Path(c.avatar_url.split("?")[0]).suffix or ".jpg"
        avatar_path = out / f"{c.comment_id}{ext}"
        try:
            resp = requests.get(c.avatar_url, timeout=15)
            resp.raise_for_status()
            avatar_path.write_bytes(resp.content)
            c.avatar_path = str(avatar_path)
        except Exception as e:
            print(f"[avatars] 下載頭像失敗 ({c.author}): {e}")

    return comments
