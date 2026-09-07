"""プレビュー判定の理由を、修正と維持に分けて記録する。"""
from .intent import StrictModel


class ReviewMeaning(StrictModel):
    fix: list[str]
    preserve: list[str]
    questions: list[str]


class ReviewCorrection(StrictModel):
    revision: int
    meaning: ReviewMeaning


class IdentityInstructionDraft(StrictModel):
    include_en: str
    avoid_en: str
    summary_ja: str
    questions: list[str]
