"""步驟 3:翻譯留言成道地繁體中文(台灣網路用語),保留語氣詞、表情符號、迷因梗。

比照 VideoSubtitler/subtool/translate.py 的 auto/google/claude 引擎切換模式,
但提示詞改成針對「YouTube 留言」設計,而非字幕逐句直譯。

claude 引擎透過本機安裝的 Claude Code CLI(`claude -p`)執行翻譯,不需要
ANTHROPIC_API_KEY,但需要先執行 `claude login` 完成登入。
"""
import shutil
import subprocess

from .comments import Comment

BATCH_SIZE = 30

CLAUDE_CLI_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_CLI_TIMEOUT_SECONDS = 120
CLAUDE_CLI_DISALLOWED_TOOLS = "Bash Read Write Edit NotebookEdit WebFetch WebSearch Agent Task"

_SYSTEM_PROMPT = (
    "你是專業的 YouTube 留言翻譯,負責把各國語言的留言譯成通順自然的繁體中文,不要逐字直譯。"
    "譯文的語氣要貼著原文本身的語氣走:原文認真就譯得認真,原文抱怨就譯得抱怨,"
    "原文本來俏皮才跟著俏皮,不要每則都刻意加重網路用語或迷因梗,"
    "也不要為了追求「道地」而讓譯文比原文更隨便、更浮誇。"
    "表情符號原樣保留,避免中國大陸用語(如「視頻」「軟件」「信息」)。"
    "全部使用繁體中文字,不得混入任何簡體字(例如「这」「说」「没」等)。"
    "規則:1) 保持相同編號與行數,一行一句,格式為「編號|譯文」;"
    "2) 不要合併或拆分句子;3) 只輸出譯文行,不要任何說明或多餘文字。"
)


def _translate_claude(texts: list[str]) -> list[str]:
    executable = shutil.which("claude")
    if executable is None:
        raise RuntimeError(
            "找不到 claude CLI,請先安裝 Claude Code(npm install -g @anthropic-ai/claude-code)"
            "並執行 `claude login` 登入"
        )

    results: list[str] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        numbered = "\n".join(f"{j + 1}|{t}" for j, t in enumerate(batch))
        try:
            process = subprocess.run(
                [
                    executable,
                    "-p",
                    "--model", CLAUDE_CLI_MODEL,
                    "--system-prompt", _SYSTEM_PROMPT,
                    "--disallowedTools", CLAUDE_CLI_DISALLOWED_TOOLS,
                ],
                input=numbered,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=CLAUDE_CLI_TIMEOUT_SECONDS,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("claude cli 執行逾時") from exc

        if process.returncode != 0:
            raise RuntimeError(f"claude cli 執行失敗: {process.stderr.strip()}")

        mapping = {}
        for line in process.stdout.strip().splitlines():
            if "|" in line:
                num, _, content = line.partition("|")
                if num.strip().isdigit():
                    mapping[int(num.strip())] = content.strip()
        results.extend(mapping.get(j + 1, batch[j]) for j in range(len(batch)))
        print(f"[translate] claude cli 進度 {min(i + BATCH_SIZE, len(texts))}/{len(texts)}")
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
        engine = "claude" if shutil.which("claude") else "google"
        print(f"[translate] 自動選擇引擎: {engine}")

    texts = [c.text.replace("\n", " ") for c in comments]
    translated = _translate_claude(texts) if engine == "claude" else _translate_google(texts)

    for c, t in zip(comments, translated):
        c.text_translated = t

    return comments
