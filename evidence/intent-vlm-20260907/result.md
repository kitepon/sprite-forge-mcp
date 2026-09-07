# コメント解釈のローカルVLM実測 2026-09-07

静止画として ComfyUI-QwenVL を呼ぶ。動画入力は使っていない。

| 候補 | 結果 |
| --- | --- |
| Qwen3-VL-8B-Instruct | 同日の汎用NG実測で否定が逆転。製品には使わない |
| Qwen3-VL-32B-Instruct-FP8 | fox で `kernels` 0.16 不足。finegrained FP8 が動かない |
| Qwen3-VL-32B-Instruct 8-bit | スキーマ合格。VRAM ほぼ満杯（空き約 1.6GB）。載せたままの2本目 52秒 |
| Qwen3-VL-32B-Instruct 4-bit | 同じスキーマ合格。VRAM 空き約 13GB。載せたままの2本目 4秒 |

ロード中はホスト RAM が一時的に逼迫し、載ったあとは GPU 側に残る。公式 Qwen3-VL に 8B と 32B の中間サイズはない。unsloth 27B は視覚系列として未確認のため未測。

`smoke.json` は 8-bit 初回取得込み（470秒 / 150秒）。載せ直しを外した比較は `compare.json`。

再実行: `uv run python evidence/intent-vlm-20260907/compare.py`
