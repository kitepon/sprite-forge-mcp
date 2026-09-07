"""指摘の被写体だけを生成文へ足す。画風は足さない。"""
import pytest

from backend.identity_instruction import insert_include, reject_style_words


PLAIN = (
    "ndac1de01, full body, standing, front view, looking at viewer, white cropped top "
    "with a fluffy fur collar and diamond chest opening, gold trim and star ornaments, "
    "layered white ruffled mini skirt, white fur-trimmed knee-high boots, slim young adult "
    "woman with a slightly stylized roughly six-head-tall proportion, simple background, "
    "white background"
)


def test_inserts_twin_tails_after_trigger():
    text = insert_include(PLAIN, "ndac1de01", "twin tails")
    assert text.startswith("ndac1de01, twin tails, full body")
    assert "anime style" not in text
    assert PLAIN.startswith("ndac1de01, full body")


def test_rejects_style_words_in_subject():
    with pytest.raises(ValueError, match="画風"):
        reject_style_words("anime style twin tails")
    with pytest.raises(ValueError, match="画風"):
        insert_include(PLAIN, "ndac1de01", "anime style twin tails")
