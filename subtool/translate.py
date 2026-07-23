"""步驟 2:將字幕翻譯成繁體中文 (zh-TW)。

三種引擎:
  google — deep-translator 的 Google 翻譯(免費、免金鑰),再以 OpenCC s2twp 統一為台灣正體
  claude — Anthropic Claude API(品質最佳,需 ANTHROPIC_API_KEY 或 ant auth login)
  opencc — 純簡轉繁(來源已是簡體中文時使用)
"""
import os
from pathlib import Path

import srt

BATCH_SIZE = 40  # 每批翻譯的字幕句數


def _opencc_convert(texts: list[str]) -> list[str]:
    from opencc import OpenCC

    cc = OpenCC("s2twp")  # 簡體 → 台灣正體(含用語轉換)
    return [cc.convert(t) for t in texts]


def _translate_google(texts: list[str]) -> list[str]:
    from deep_translator import GoogleTranslator

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
    return _opencc_convert(results)


def _translate_claude(texts: list[str]) -> list[str]:
    import anthropic

    client = anthropic.Anthropic()
    system = (
        "你是專業字幕翻譯。將使用者提供的編號字幕逐句翻譯成台灣慣用的繁體中文。"
        "規則:1) 保持相同編號與行數,一行一句,格式為「編號|譯文」;"
        "2) 語氣自然口語,符合字幕長度;3) 不要合併或拆分句子;4) 只輸出譯文行,不要任何說明。"
    )
    results: list[str] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        numbered = "\n".join(f"{j + 1}|{t}" for j, t in enumerate(batch))
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=16000,
            system=system,
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


def translate_srt(
    srt_path: str,
    output_dir: str,
    engine: str = "auto",
) -> str:
    """翻譯 SRT 為繁體中文,回傳新 SRT 路徑。engine: auto|google|claude|opencc"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    subs = list(srt.parse(Path(srt_path).read_text(encoding="utf-8")))
    texts = [s.content.replace("\n", " ") for s in subs]

    if engine == "auto":
        engine = "claude" if os.environ.get("ANTHROPIC_API_KEY") else "google"
        print(f"[translate] 自動選擇引擎: {engine}")

    if engine == "claude":
        translated = _translate_claude(texts)
    elif engine == "opencc":
        translated = _opencc_convert(texts)
    else:
        translated = _translate_google(texts)

    for s, t in zip(subs, translated):
        s.content = t

    out_path = str(out / f"{Path(srt_path).stem}.zh-TW.srt")
    Path(out_path).write_text(srt.compose(subs), encoding="utf-8")
    txt_path = str(out / f"{Path(srt_path).stem}.zh-TW.txt")
    Path(txt_path).write_text("\n".join(translated), encoding="utf-8")

    print(f"[translate] 繁中字幕: {out_path}")
    print(f"[translate] 繁中文字: {txt_path}")
    return out_path


def build_bilingual_srt(orig_srt_path: str, zh_srt_path: str, output_dir: str) -> str:
    """合併原文與繁中字幕,產生雙語字幕(同一句上方原文、下方繁中)。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    orig_subs = list(srt.parse(Path(orig_srt_path).read_text(encoding="utf-8")))
    zh_subs = list(srt.parse(Path(zh_srt_path).read_text(encoding="utf-8")))

    if len(orig_subs) != len(zh_subs):
        raise RuntimeError(
            f"原文字幕與繁中字幕句數不一致({len(orig_subs)} vs {len(zh_subs)}),"
            "無法合併雙語字幕(可能手動編輯時新增/刪除了某幾句)"
        )

    merged = [
        srt.Subtitle(index=i, start=z.start, end=z.end, content=f"{o.content}\n{z.content}")
        for i, (o, z) in enumerate(zip(orig_subs, zh_subs), start=1)
    ]

    stem = Path(zh_srt_path).stem.removesuffix(".zh-TW")
    out_path = str(out / f"{stem}.bilingual.srt")
    Path(out_path).write_text(srt.compose(merged), encoding="utf-8")

    print(f"[translate] 雙語字幕: {out_path}")
    return out_path
