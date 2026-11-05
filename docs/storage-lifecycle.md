# 保存と回収の公開契約

## 機能図

| 機能・正本 | 入力 → 出力 | 状態とデータの所有 | 失敗・終了・保持回収 |
| --- | --- | --- | --- |
| WebUI/MCP・`backend/app.py` | 利用者操作 → 同一 `Services` | ブラウザーは下書き、主機は制作の正本 | エラーはAPIへ返す。起動時に再開/中断の記録を確定 |
| 取込・台帳・`backend/services.py` | upload/URL/data/既存path → PNG/キャラクター/画風 | 主機uploads・台帳sample・説明・adopted素材 | 唯一データを時刻だけで削除しない。明示削除だけを既契約で処理 |
| 制作・`services.py`/`bible.py`/`workflows.py` | 台帳/注文 → fox ComfyUI → 画像/パネル/HTML | 主機generated・台帳・jobが結果の正本、foxは実行 | 成否/一部結果をjob/eventへ保存。利用者作品・採用結果を一括回収しない |
| 教材凍結・`services.py`/`preview_learning.py` | 確認済sample/判定 → dataset/説明/履歴 | 主機generated/trainingとpreferenceは過去の確認教材 | snapshotは元sampleの変更/削除から独立。履歴を表示するため保持 |
| 転送・`backend/box.py` | UUID別教材とTOML/JSON → fox一時stage | 学習ごとにUUID専用stage、主機正本とLoRA出力は対象外。jobは転送writerの実寿命が未確定であることを最初のawait前から保存 | SCPの作成/communicateが戻るまではwriter終端を仮定しない。取消ではjobのretained_unknownを保持し、remote preparedを未使用と解釈しない。起動要求前にlaunchingへ確定 |
| 学習・`box/train.py`/`box/staging.py` | stage内configとモデル → LoRA/metrics/進捗 | foxのLoRA出力とモデルは永続。stageのみ転送コピー | OS lockでprepare/launch/run/clean状態変更を直列化。runningの教材は削除禁止。実subprocess終端後だけfinishedへ確定し回収。親trainerの強制終了/通信断はlaunching/runningのままunknown保持し、SSH終了をworker終端に読み替えない |
| 履歴・`backend/events.py` | 操作/進捗/結果 → jobs JSON/events NDJSON/SSE | 主機永続、WebUI/MCP共通 | 複製バックアップではなく操作履歴。既データの自動時限削除はしない |
| build/配備・担当integrations | lock済source/現image → 候補/Compose/受入 | 製品担当、主機Docker | .dockerignoreでcache/evidence/tests/.git/.venvを除外。候補受入成功後だけ現用・直前戻しを残し、自製未参照imageを通常rm。全container参照と混在所有は保護、force/prune禁止 |
| 退避・担当配備器 | 停止中正本/manifest → NAS差分archive/復旧索引 | 正式NFS1000:1000、既5世代は復旧参照あり | 正式mount不成立で書込前停止。検証済immutable全量基点+file差分+削除一覧+source bundleで復旧可能にする。新管理世代は成功後current/previousの2参照を保持し、非参照の所有完了世代だけ回収。既legacy基点/unknownを無断退役しない |
| 開発・受入 | tracked source/fixture → 試験結果/差分 | 本人席、公開repository | 一時生成物はTemporaryDirectory等で回収。完了candidateの展開コピーはsource commit/manifestで代替し、必要な差分と小証拠だけ保持 |

## データフロー図

1. 利用者 → WebUI REST またはMCP → 共通Services → uploads/キャラクター/画風台帳 → frozen教材。
2. frozen教材＋job UUID → `Services._training_stage`がwriter実寿命未確定をjob.remote_stage_cleanup=retained_unknownとして最初のawait前に永続化 → fox `C:/sf/staging/<UUID>/`（所有marker） → SCP writer開始 → communicate返却で転送の実終端を確認 → launching確定 → trainer（running確定） → sd-scripts/ComfyUIモデル → 永続LoRA/metrics。
3. trainer進捗 → SSH stdout → 主機log/job/event → WebUI SSE/MCP。metrics → 主機履歴。実subprocess終端 → finished確定 → marker・path・OS lock検証 → stageだけ回収。成功時には専用LoRA出力の実在も確認してからSSH成功を返す。転送側finallyはprepared/finishedだけを回収し、起動/稼働/結果不明は保持結果をjob/eventに保存。
4. backend再起動 → 既存job再開/非再開jobをfailed確定 → job.remote_stage_cleanupを確認。retained_unknownなら回復のcleanも同jobの新しいprepareも送らず保持し、preparedへも読み替えない。remote launching/running/unknownも従来通り保護し、通常終了したremote trainer自身の回収を優先。取消/終了不明のwriterは再起動や無条件TTLでは回収可能にならない。
5. source/uv.lock → .dockerignore付きbuild → 候補 → idle確認 → 正式NASのimmutable基点+delta/削除一覧＋全manifest検証 → Compose → health/変更経路/データ保持受入 → 現用・直前戻し・全container参照を保護した自製image整理 → NAS current/previous索引更新と非参照の所有完了退避回収 → 配備結果記録。

## 削除境界

回収対象は所有markerのあるUUID stageと識別できる自製未参照image、完了試験の再生成できるcontext/cacheに限定。stageはsymlink/junctionを辿らず、設定pathがstage外なら拒否。利用者画像・主機教材・log/job/event・LoRA・モデル・共有ComfyUIのinput/output・他製品・復旧正本は自動回収しない。唯一データか判別できない過去試験も不用と推測しない。共有ComfyUI保存の変更が必要なら装置担当と調整する。

変更前は主機からfox `C:/sf/` 直下へ教材/TOMLを転送し、終端後の回収窓口が無かった。上記UUID stageと状態契約は2026-11-06修理の変更案であり、実装・試験・配備の成立は担当の `docs/storage-lifecycle-20261106.md` を参照。過去の無marker教材は主機正本との全file一致とworker非参照が確認できた個体だけを移行整理し、単なる名前一致では回収しない。
