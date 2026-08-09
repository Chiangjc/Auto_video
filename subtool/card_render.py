"""步驟 5:把留言資料套進 HTML 模板,用 Playwright 截圖成透明背景 PNG 留言卡片。"""
import base64
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .comments import Comment

TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def _avatar_data_uri(avatar_path: str) -> str:
    if not avatar_path or not Path(avatar_path).exists():
        return ""
    data = Path(avatar_path).read_bytes()
    mime = mimetypes.guess_type(avatar_path)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 1000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(n)


def _relative_time(published_at: str) -> str:
    """把 ISO 8601 時間轉成「n 天前」這類相對時間標籤,抓不到時間就回傳空字串。"""
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ""
    delta = datetime.now(timezone.utc) - dt
    seconds = delta.total_seconds()
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))} 分鐘前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小時前"
    if seconds < 86400 * 30:
        return f"{int(seconds // 86400)} 天前"
    if seconds < 86400 * 365:
        return f"{int(seconds // (86400 * 30))} 個月前"
    return f"{int(seconds // (86400 * 365))} 年前"


def render_comment_card(comment: Comment, out_png: str, bilingual: bool = False) -> str:
    """渲染單則留言卡片,輸出透明背景 PNG。bilingual=True 時原文會附在翻譯下方。"""
    template = _env.get_template("comment_card.html")
    html = template.render(
        author=comment.author,
        avatar_data_uri=_avatar_data_uri(comment.avatar_path),
        initial=(comment.author.strip()[:1].upper() if comment.author.strip() else "?"),
        text=comment.text_translated or comment.text,
        original_text=comment.text if (bilingual and comment.text_translated) else None,
        like_count=_format_count(comment.like_count),
        time_label=_relative_time(comment.published_at),
    )

    from playwright.sync_api import sync_playwright

    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 960, "height": 100})
        page.set_content(html)
        card = page.locator(".comment-card")
        card.screenshot(path=out_png, omit_background=True)
        browser.close()

    return out_png


def render_comment_cards(comments: list[Comment], out_dir: str, bilingual: bool = False) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for c in comments:
        png_path = out / f"{c.comment_id}.png"
        render_comment_card(c, str(png_path), bilingual=bilingual)
        paths.append(str(png_path))
    print(f"[card_render] 產生 {len(paths)} 張留言卡片")
    return paths
