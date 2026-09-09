# 設定画パネルを合格した一枚シートから描く — fox 実測 2026-09-10

オーナーの申告は「一枚シートを作った後の設定画が、直前のシートをベースにしていない」。
コードを読むと事実そのとおりで、合格シートは設定画のヘッダー画像として貼るだけ、
パネル本体は Anima+LoRA が文字注文から描いていた。合格した姿とパネルの姿が別物になる。

ここに置いたのは、合格シートを実際にパネルの入力へ使えるかを fox（RTX 5090）の
ComfyUI で測った記録である。実測に使った ComfyUI は `SPRITEFORGE_COMFY_URL`、
入力は本番台帳の合格シート 1 枚（`/tmp/approved_sheet.png` として渡した）。

## 結論

1. `ReferenceLatent` は Anima に効かない。参照を足した出力とベースラインの出力に
   1 ピクセルの差もなかった（probe）。
2. JoyAI-Image-Edit-Plus（`workflows.joy_edit`）は参照画像を実際に読む。ただし
   **参照の構図が出力へ写る**。シート全体を渡すと、出力も複数ビュー＋色見本のシートになった（probe2）。
3. だから参照は人物一体でなければならない。投影（行・列の白い谷）で割る方式は破れた
   ——題字・顔アップ・チビ・色見本の位置が生成ごとに変わり、背面図の列に色見本が同居する（probe4, probe5, diag）。
4. SAM 3.1（`SAM3_Detect`, `individual_masks=True`）は人物の全身マスクを返す。マスクの外を
   白で塗って外接矩形で切ると、隣の人物も色見本も題字も入らない参照になった（probe6–probe8）。
5. 対象語は `"character"`・`"person"`・`"girl"` のどれでも同じマスク座標・同じ切り出しになった。
   製品は性別も人外かどうかも決め打ちできないので、`"character"` を使う（probe11）。
6. 顔だけを求めるパネルへ全身を渡すと全身が返る。人物の上部だけを切った参照を渡すと
   顔アップになった（probe8 の `ex_smile-figure` と `ex_smile-head`）。
7. 指示文の語順が効く。「同じ人物を描く」で始めて変更点を後ろのタグに置くと、編集モデルは
   冒頭を強く採り、タグを装飾として扱った。**替える内容を主節へ、残すものを従属節へ**回すと
   頼んだ絵になった（probe9）。衣装替えは「元の衣装を全部外す」より、外す部位名
   （top, sleeves, collar, skirt, gloves, footwear）を並べた方が従う（probe10）。

## 残った不完全さ

別衣装パネルで、キャラクターの特徴的な靴（星のブーツ）が残ることがある（probe10 の
`cos_casual`・`cos_armor`）。部位名を並べても消えない。程度の問題として受け入れ、
描き直し（`redraw_panel`）で直せる範囲とした。

## 製品への反映

- `backend/bible.py`: `figure_mask` / `figure_on_white` / `head_crop` / `reference_key`
- `backend/panel_intent.py`: `edit_instruction`（主節・従属節の並べ方）
- `backend/services.py`: `_approved_sheet` / `_sheet_references` / `_panel_reference`
- `backend/workflows.py`: `sam3_mask(..., individual=True)`

## ファイル

`probe.py` から `probe11.py` が実測スクリプト、`diag.py` は投影の profile を見る道具。
番号順に、前の測定で分かったことを次の仮説にしている。各ファイルの冒頭に、その回で
何を確かめたかと前提を書いた。

`probe.py` / `probe4.py` / `probe5.py` / `diag.py` は、その後に削除した投影方式の
切り出し（`bible.figure_crop`・`bible.reference_crop`・`bible._runs`）を呼ぶため、
現在のコードでは動かない。測定当時の入力と手順の記録として読む。

出力画像（`out*/`, `crops/`）は容量のため commit していない。再現するには
合格シート 1 枚を用意して、`SPRITEFORGE_COMFY_URL` を fox へ向けたうえで
`PYTHONPATH=. uv run python evidence/bible-sheet-source-20260910/probe8.py <sheet.png>` を実行する。
