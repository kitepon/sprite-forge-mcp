"""プレビュー判定の理由を、修正と維持に分けて記録する。"""
from .intent import StrictModel


class ReviewMeaning(StrictModel):
    fix: list[str]
    preserve: list[str]
    questions: list[str]
    description_en: str


class BatchPrompt(StrictModel):
    description_en: str


class ReviewCorrection(StrictModel):
    revision: int
    meaning: ReviewMeaning
