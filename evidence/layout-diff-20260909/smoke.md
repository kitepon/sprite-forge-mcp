# 構成変更の解釈で QwenVL が OOM

2026-09-09。設定画の構成画面で「17 ARMOR を水着に変更」と注文すると、fox の ComfyUI が `AILab_QwenVL_Advanced` で `torch.OutOfMemoryError`（Requested 9.56 GiB / Device limit 31.82 GiB）を出した。

## 原因

`layout` 工程の解釈入力が 39,212 文字あった。`sheet_layout` と `panel_specs` が同じ 23 項目を二重に持ち、`training_captions` も入っていた。さらに契約が「構成全体を返す」だったため、Qwen3-VL-32B 4-bit が 23 項目分の JSON を書き出す途中で KV cache と logit の確保に失敗した。`max_tokens=2048` では全項目の JSON は途中で切れる。

## 直し

- `layout` の契約を差分（`LayoutChange`: 変更・追加した項目と `removed_keys`）にし、サーバーの `merge_layout_change` が現在の構成へ合成する（commit `7f88186`）。
- `layout` の入力から `panel_specs` と `training_captions` を外す。
- 項目の恒久識別子は `seed_offset`。モデルが key を書き換えても既存 key を引き継ぐ（commit `2c29d6e`。初回実測でモデルが `cos_armor→cos_bikini` と書き換え、`validate_layout_proposal` が 500 を返したため）。

## 実測（本番 API → fox）

| 項目 | 修正前 | 修正後 |
| --- | --- | --- |
| 注文 | 「17 ARMOR を水着（ビキニ）に変更」 | 同じ |
| 解釈入力（`custom_prompt`） | 39,212 文字 | 23,691 文字 |
| モデル出力 | OOM で未完 | 2,802 文字（差分 2 項目） |
| ComfyUI | `execution_error` OOM | `success`（prompt_id `2636859d-…`） |
| HTTP | 500 | 200 |
| 所要 | — | 390.7 秒（モデル読込含む） |
| VRAM ピーク | 限界超過 | 31.54 GiB / 31.82 GiB（2 秒間隔 173 点、30 GiB 超は 2 点） |
| 実行前後の VRAM | — | 1.75 GiB → 1.75 GiB（`keep_model_loaded=False` で解放） |

合成結果は 24 項目。手を触れていない 22 項目は順序・内容・key・seed_offset をそのまま引き継いだ。

## 目視結果と残る論点

- モデルは seed_offset 16 の `cos_armor` を BIKINI へ差し替え（key は既存を維持）、同時に seed_offset 23 で `cos_bikini`「SWIMSUIT (BIKINI)」を追加した。「変更」の注文に対して差し替えと追加の両方をしている。契約と合成は正しく動いたが、モデルの解釈としては項目が 1 つ余る。1 回の観測で、指示文を変える根拠にはまだしない。
- VRAM ピークが装置上限の 0.28 GiB 手前。入力 23,691 文字のうち大半が `sheet_layout` の 23 項目。次に余裕を作るなら、`parts` の英文をモデルへ渡す形の見直しが候補。

ファイル: `model-output.json`（モデルの差分出力そのまま）、`comfy-status.json`（ComfyUI 履歴の status と node 入力の要約）、`vram.log`（epoch 秒と使用バイト）。
