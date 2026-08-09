"""步驟 2:規則式篩選,自動挑出適合當梗的留言(讚數門檻 / 字數範圍 / 關鍵字排除)。"""
import re

from .comments import Comment

# 基本排除清單:髒話、廣告/推銷、劇透常見用語(中/英/韓)。不追求完整覆蓋,
# 只擋最常見的雜訊,漏網的仍可事後靠人工複查或加到 exclude_keywords 補強。
DEFAULT_EXCLUDE_KEYWORDS = [
    # 廣告/推銷
    "구독", "subscribe", "http://", "https://", "www.", "訂閱", "廣告", "代購", "賣家",
    "check out my channel", "follow me",
    # 劇透常見字眼
    "spoiler", "劇透", "스포", "結局", "ending",
    # 常見髒話(中/英)
    "fuck", "shit", "幹你", "他媽", "干你娘", "sb", "白癡",
]

_URL_PATTERN = re.compile(r"https?://\S+")


def filter_comments(
    comments: list[Comment],
    top_n: int = 5,
    min_likes: int = 0,
    min_chars: int = 5,
    max_chars: int = 120,
    exclude_keywords: list[str] | None = None,
) -> list[Comment]:
    """依讚數/字數/關鍵字篩選留言,回傳依讚數由高到低排序、最多 top_n 則。"""
    blocklist = [kw.lower() for kw in DEFAULT_EXCLUDE_KEYWORDS + (exclude_keywords or [])]

    kept = []
    for c in comments:
        text = c.text.strip()
        if not text:
            continue
        if c.like_count < min_likes:
            continue
        length = len(text)
        if length < min_chars or length > max_chars:
            continue
        lowered = text.lower()
        if any(kw in lowered for kw in blocklist):
            continue
        kept.append(c)

    kept.sort(key=lambda c: c.like_count, reverse=True)
    result = kept[:top_n]
    print(f"[filter] {len(comments)} 則留言篩選後剩 {len(result)} 則")
    return result
