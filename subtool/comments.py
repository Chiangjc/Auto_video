"""步驟 1:呼叫 YouTube Data API v3 的 commentThreads.list 抓取留言。"""
from dataclasses import dataclass, field

import requests

API_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


@dataclass
class Comment:
    comment_id: str
    author: str
    avatar_url: str
    text: str
    like_count: int
    published_at: str
    video_id: str
    text_translated: str = ""
    avatar_path: str = ""


def fetch_comments(
    video_id: str,
    api_key: str,
    max_results: int = 100,
    order: str = "relevance",
) -> list[Comment]:
    """抓取熱門留言(order=relevance 已由 API 依熱門度排序,不需自行排序)。

    max_results:最多抓幾則(會自動分頁,每頁上限 100)。
    留言關閉或影片不存在時回傳空清單並印出警告,不拋例外(方便批次跑多支影片時不中斷整批)。
    """
    comments: list[Comment] = []
    page_token = None

    while len(comments) < max_results:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "key": api_key,
            "order": order,
            "maxResults": min(100, max_results - len(comments)),
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(API_URL, params=params, timeout=30)
        if resp.status_code == 403:
            print(f"[comments] {video_id}: 留言已關閉或無權限存取,略過")
            return []
        if resp.status_code == 404:
            print(f"[comments] {video_id}: 找不到影片")
            return []
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            comments.append(
                Comment(
                    comment_id=item["id"],
                    author=snippet.get("authorDisplayName", ""),
                    avatar_url=snippet.get("authorProfileImageUrl", ""),
                    text=snippet.get("textOriginal", ""),
                    like_count=snippet.get("likeCount", 0),
                    published_at=snippet.get("publishedAt", ""),
                    video_id=video_id,
                )
            )

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    print(f"[comments] {video_id}: 抓到 {len(comments)} 則留言")
    return comments
