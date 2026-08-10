"""單獨測試留言翻譯 prompt,不必跑下載影片/抓留言的完整流程。

用法:
  python test_translate.py                    # 用內建的範例留言(涵蓋認真/抱怨/玩笑等語氣)
  python test_translate.py --engine google     # 換引擎
  python test_translate.py --file my.txt       # 自訂留言,一行一則
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from subtool.comments import Comment
from subtool.translate_comments import translate_comments

_SAMPLE_TEXTS = [
    "This song genuinely changed my life, I was crying by the second verse.",
    "bro why is the mixing so bad on this track ㅋㅋㅋ",
    "I don't understand why everyone loves this, it's just okay to me.",
    "この曲本当に神すぎる、涙が止まらない www",
    "Can someone explain the chord progression at 1:23? Sounds really unusual.",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default="claude", choices=["auto", "google", "claude"])
    parser.add_argument("--file", help="每行一則留言的文字檔;不指定則用內建範例")
    args = parser.parse_args()

    if args.file:
        texts = [
            line.strip()
            for line in Path(args.file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        texts = _SAMPLE_TEXTS

    comments = [
        Comment(
            comment_id=str(i),
            author="test",
            avatar_url="",
            text=t,
            like_count=0,
            published_at="",
            video_id="test",
        )
        for i, t in enumerate(texts)
    ]

    translated = translate_comments(comments, engine=args.engine)
    for c in translated:
        print(f"原文: {c.text}")
        print(f"譯文: {c.text_translated}")
        print()


if __name__ == "__main__":
    main()
