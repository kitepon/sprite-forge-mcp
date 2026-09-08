# 判定再学習の HTTP 524

2026-09-08。プレビュー判定画面で「この判定でLoRAを再学習する」を押すと、WebUI が赤バナー「応答を受け取れませんでした。制作状況をご確認ください：HTTP 524」を出した。学習そのものは失敗していない。

## 実測

公開面経由の同期 POST が Cloudflare の origin timeout（典型 100 秒）で切れた。ジョブ記録側は完走している。

| 項目 | 値 |
| --- | --- |
| 学習ジョブ | `483919fd-abcf-4f75-bb59-043e066a9867` |
| kind / status | `preview_learning` / `completed` |
| 作成 / 更新 | `2026-09-08T11:25:33Z` / `2026-09-08T11:42:27Z` |
| 学習回数 | `progress.step=20` / `total=20` |
| 再プレビュー | `02454108-e2fa-4af2-817f-51d547285055`（`kind=preview` / `completed` / 10 枚） |

判定本文と説明はここへ書かない。既存キャラの再学習ボタンは、同じ要求を二本立てにするため再送しない。

## 原因と直し

`relearn_preview` が解釈・選好学習・再プレビュー完了まで 1 本の POST で待っていた。直しは検証と `save_job(interpreting)` まで同期し、本体は `asyncio.create_task` してすぐ返す。呼び出し側はジョブを poll する。進捗表示は判定グリッド下・ボタン直上へ移し、再学習中は設定画へ進むボタンを無効にする。

関連試験 `tests/test_preview_learning.py` 7 件成功。完了時の Python 全試験 290 件成功、2 skip。
