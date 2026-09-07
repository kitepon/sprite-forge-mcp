"""指摘から取り出した被写体だけを、既存の生成文へ足す。画風語句は足さない。"""

TRIGGER_PREFIX = "ndac1de01, "
# 本人NG「髪型がツインテールではない」から取り出した被写体。AnimaのDanbooruタグ。
SUBJECT_FROM_NG = "twin tails"
STYLE_WORDS = ("anime style", "manga", "ghibli", "cel shaded", "painterly")


def with_subject(prompt: str, subject: str = SUBJECT_FROM_NG) -> str:
    if not prompt.startswith(TRIGGER_PREFIX):
        raise ValueError("生成文の先頭がトリガーではありません。")
    if any(word in subject.lower() for word in STYLE_WORDS):
        raise ValueError("被写体指定に画風語句が入っています。")
    rest = prompt[len(TRIGGER_PREFIX):]
    if rest.startswith(subject + ", ") or rest == subject:
        return prompt
    return f"{TRIGGER_PREFIX}{subject}, {rest}"
