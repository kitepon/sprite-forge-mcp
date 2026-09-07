"""LoRAと対になる被写体の指示。画風語句は入れない。"""
from copy import deepcopy

STYLE_WORDS = ("anime style", "manga", "ghibli", "cel shaded", "painterly", "watercolor")


def prompt_text(*parts: str) -> str:
    return ", ".join(part.strip() for part in parts if part and str(part).strip())


def reject_style_words(text: str) -> str:
    """指示は被写体の内容だけにする。画風はLoRAの選択で決める。"""
    lowered = (text or "").lower()
    if any(word in lowered for word in STYLE_WORDS):
        raise ValueError("指示文書に画風語句が入っています。被写体の内容だけを書いてください。")
    return text or ""


def instruction_parts(instruction: dict | None) -> tuple[str, str]:
    if not instruction:
        return "", ""
    include = reject_style_words(instruction.get("include_en") or "").strip()
    avoid = reject_style_words(instruction.get("avoid_en") or "").strip()
    return include, avoid


def character_prompt(trigger: str, instruction: dict | None, style_word: str, *rest: str) -> str:
    include, _ = instruction_parts(instruction)
    return prompt_text(trigger, include, style_word, *rest)


def character_negative(base: str, instruction: dict | None) -> str:
    _, avoid = instruction_parts(instruction)
    return prompt_text(base, avoid)


def insert_include(prompt: str, trigger: str, include: str) -> str:
    include = reject_style_words(include).strip()
    if not include:
        return prompt
    if not trigger:
        return prompt_text(include, prompt)
    if prompt == trigger:
        return prompt_text(trigger, include)
    prefix = f"{trigger}, "
    if prompt.startswith(prefix):
        rest = prompt[len(prefix):]
        if rest == include or rest.startswith(f"{include}, "):
            return prompt
        return prompt_text(trigger, include, rest)
    return prompt_text(trigger, include, prompt)


def strip_include(prompt: str, trigger: str, include: str) -> str:
    include = (include or "").strip()
    if not include:
        return prompt
    prefix = prompt_text(trigger, include)
    if prompt == prefix:
        return trigger
    extra = f"{prefix}, "
    if prompt.startswith(extra):
        return prompt_text(trigger, prompt[len(extra):])
    return prompt


def applied_instruction(record: dict, use_instruction: bool) -> dict | None:
    if not use_instruction:
        return None
    current = record.get("identity_instruction")
    if current:
        instruction_parts(current)
        return deepcopy(current)
    return {
        "include_en": "",
        "avoid_en": "",
        "summary_ja": "",
        "lora_name": record.get("lora_name") or "",
        "revision": 0,
    }


def store_instruction(record: dict, snapshot: dict) -> None:
    current = record.get("identity_instruction")
    if current and current != snapshot:
        record.setdefault("identity_instruction_history", []).append(deepcopy(current))
    record["identity_instruction"] = deepcopy(snapshot)
