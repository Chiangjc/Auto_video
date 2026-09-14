"""步驟 5:把留言資料套進 HTML 模板,用 Playwright 截圖成透明背景 PNG 留言卡片。

疊加標題也在這裡一起用 HTML→PNG 產生(render_title_png),這樣就不必依賴 ffmpeg
是否編進 drawtext/freetype——精簡版的 Homebrew ffmpeg 沒有 drawtext 濾鏡。
"""
import base64
import mimetypes
from datetime import datetime, timezone
from html import escape as _html_escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .comments import Comment

TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

_FONT_DIR = Path(__file__).parent.parent / "tools" / "fonts"

# 標題字型優先序:把想用的字型檔丟進 tools/fonts/,排前面的先用。
# 想換字型就換這個清單、或直接在 tools/fonts/ 放檔案即可。
_TITLE_FONT_CANDIDATES = [
    "TaipeiSansTCBeta-Bold.ttf",      # 台北黑體(粗)——有就優先
    "TaipeiSansTCBeta-Regular.ttf",   # 台北黑體(標準)
    "MantouSans-Regular.ttf",         # 饅頭黑體(較粗、較有個性)
]


def _title_font_css() -> tuple[str, str]:
    """回傳 (@font-face 區塊, font-family 值)。在 tools/fonts/ 找到第一個候選字型就嵌進去,
    都沒有就退回系統中文字型名稱。"""
    for name in _TITLE_FONT_CANDIDATES:
        ttf = _FONT_DIR / name
        if ttf.exists():
            b64 = base64.b64encode(ttf.read_bytes()).decode()
            face = (
                "@font-face{font-family:'TitleFont';"
                f"src:url(data:font/ttf;base64,{b64}) format('truetype');}}"
            )
            return face, "'TitleFont', sans-serif"
    return "", "'PingFang TC', 'Noto Sans TC', 'Microsoft JhengHei', sans-serif"


TITLE_SECOND_LINE_COLOR = "#ffd400"  # 第二行(含)之後改用黃字


def render_title_png(title: str, out_png: str, width: int = 1080, height: int = 200,
                     font_size: int = 56) -> str:
    """把疊加標題渲染成「滿版寬、實心黑底、置中」的 PNG(取代舊的 drawbox+drawtext)。

    字級固定 font_size(預設 56,與舊版 drawtext 一致);第一行白字,第二行起黃字。
    以 \\n 手動斷行,單行過長會在黑條寬度內自動折行(折行部分仍算同一「行」、同一顏色)。
    """
    face_css, family = _title_font_css()

    logical_lines = title.split("\n")
    line_divs = "".join(
        f'<div class="{"l1" if i == 0 else "ln"}">{_html_escape(line) or "&nbsp;"}</div>'
        for i, line in enumerate(logical_lines)
    )

    html = (
        '<meta charset="utf-8"><style>'
        f"{face_css}"
        "html,body{margin:0;padding:0}"
        f".title-bar{{width:{width}px;height:{height}px;background:#000;"
        "display:flex;flex-direction:column;align-items:center;justify-content:center;"
        "box-sizing:border-box;padding:0 48px}"
        f".title-bar>div{{font-family:{family};font-size:{font_size}px;font-weight:400;"
        "line-height:1.2;letter-spacing:.03em;white-space:pre-wrap;text-align:center}"
        ".title-bar .l1{color:#fff}"
        f".title-bar .ln{{color:{TITLE_SECOND_LINE_COLOR}}}"
        "</style>"
        f'<div class="title-bar">{line_divs}</div>'
    )

    from playwright.sync_api import sync_playwright

    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html)
        page.locator(".title-bar").screenshot(path=out_png)
        browser.close()

    return out_png


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
