"""合格シートの行・列の profile を出して、切り出しがどこで割れているかを見る。

使い方: uv run python evidence/bible-sheet-source-20260910/diag.py /tmp/approved_sheet.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from backend.bible import _ink_mask, _runs, figure_crop

sheet = Path(sys.argv[1])
rgb = Image.open(sheet).convert("RGB")
mask = _ink_mask(rgb)
print("sheet", rgb.size)

rows = list(mask.resize((1, rgb.height), Image.BOX).getdata())
print("row runs", _runs(rows))
print("row values 0..40", rows[:40])
nonzero = [i for i, v in enumerate(rows) if v]
print("row nonzero first/last", nonzero[0], nonzero[-1])
print("min value inside", min(rows[nonzero[0]:nonzero[-1] + 1]))
low = [(i, v) for i, v in enumerate(rows) if 0 < v <= 3]
print("faint rows count", len(low), low[:20])

cols = list(mask.resize((rgb.width, 1), Image.BOX).getdata())
print("col runs", _runs(cols))

crop = figure_crop(sheet)
print("figure_crop", crop.size)
