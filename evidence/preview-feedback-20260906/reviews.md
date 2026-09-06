# 生成画像と判定の保存

2026-09-06。`tests/test_preview_reviews.py` と `tests/test_generation_composition_negative.py` の9件が成功。

既定10枚、seedの対応、画像本体のdigest、生成設定、生成途中の判定保存、再読込み、コメントを保持した解除、履歴、古いrevisionの競合、別画像・別キャラクター・同名再作成、旧ジョブの説明をfixtureで確認した。生成画像は元サンプルへ追加していない。

REST／MCPは `preview_reviews` と `save_preview_review` の同一サービスを公開する。独立した読取り反証でも実害のある不具合なし。現行の単一プロセスで保存中に非同期の中断がないことを確認し、不要なロックは追加していない。

画面の接続と実ブラウザー受入は後続工程。本書は画像生成やUIを本番配備済みとする証拠ではない。
