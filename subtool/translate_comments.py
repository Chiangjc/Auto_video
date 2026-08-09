"""步驟 3:翻譯留言成道地繁體中文(台灣網路用語),保留語氣詞、表情符號、迷因梗。

比照 VideoSubtitler/subtool/translate.py 的 auto/google/claude 引擎切換模式,
但提示詞改成針對「YouTube 留言」設計,而非字幕逐句直譯。
"""
import os

from .comments import Comment

BATCH_SIZE = 30

_SYSTEM_PROMPT = (
    "你是專業的 YouTube 留言翻譯,負責把各國語言的留言翻譯成台灣人平常在網路上會打的繁體中文。"
    "這是社群留言,不是正式文件,請自然口語、保留原本的語氣和梗,不要逐字直譯。"
    "網路用語與語氣詞請意譯成台灣對應的說法,例如韓文「ㅋㅋㅋ」「ㅎㅎ」可譯成「哈哈哈」或「XD」,"
    "日文「www」可譯成「笑死」或「XD」,表情符號原樣保留。"
    "規則:1) 保持相同編號與行數,一行一句,格式為「編號|譯文」;"
    "2) 不要合併或拆分句子;3) 只輸出譯文行,不要任何說明或多餘文字。"
)


def _translate_claude(texts: list[str]) -> list[str]:
    import anthropic

    client = anthropic.Anthropic()
    results: list[str] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        numbered = "\n".join(f"{j + 1}|{t}" for j, t in enumerate(batch))
        resp = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": numbered}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        mapping = {}
        for line in text.strip().splitlines():
            if "|" in line:
                num, _, content = line.partition("|")
                if num.strip().isdigit():
                    mapping[int(num.strip())] = content.strip()
        results.extend(mapping.get(j + 1, batch[j]) for j in range(len(batch)))
        print(f"[translate] claude 進度 {min(i + BATCH_SIZE, len(texts))}/{len(texts)}")
    return results


def _translate_google(texts: list[str]) -> list[str]:
    from deep_translator import GoogleTranslator
    from opencc import OpenCC

    cc = OpenCC("s2twp")
    tr = GoogleTranslator(source="auto", target="zh-TW")
    results = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        try:
            out = tr.translate_batch(batch)
        except Exception:
            out = [tr.translate(t) for t in batch]
        results.extend(t if t else src for t, src in zip(out, batch))
        print(f"[translate] google 進度 {min(i + BATCH_SIZE, len(texts))}/{len(texts)}")
    return [cc.convert(t) for t in results]


def translate_comments(comments: list[Comment], engine: str = "auto") -> list[Comment]:
    """翻譯留言,補上 text_translated 欄位(原文 text 保留不變,雙語卡片會用到)。"""
    if not comments:
        return comments

    if engine == "auto":
        engine = "claude" if os.environ.get("ANTHROPIC_API_KEY") else "google"
        print(f"[translate] 自動選擇引擎: {engine}")

    texts = [c.text.replace("\n", " ") for c in comments]
    translated = _translate_claude(texts) if engine == "claude" else _translate_google(texts)

    for c, t in zip(comments, translated):
        c.text_translated = t

    return comments
