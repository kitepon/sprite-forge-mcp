# RAG Index

| Topic | Source | Retrieved | Confidence | Notes |
| --- | --- | --- | --- | --- |
| 学習キャプションと生成文の契約 | [identity-prompt-contract-20260907.md](identity-prompt-contract-20260907.md) | 2026-09-07 | kohya公式・Anima一次実測・崩壊論文、作り直しと生成文対照 | キャプションに出した特徴は生成で要求される。同一LoRAで twin tails 追加は 3/10→8/10。OK生成の再学習は裾を太らせない。 |
| 汎用NG事例の反映 | [generic-negative-feedback-20260907.md](generic-negative-feedback-20260907.md) | 2026-09-07 | 一次資料・コード照合、抑制効果未実証 | 髪型専用研究を撤回。画像と指摘から共通処理で除去対象を取り出す。 |
| アニメNG特徴のモデル選定 | [anime-feature-model-selection-20260906.md](anime-feature-model-selection-20260906.md) | 2026-09-06 | 一次資料比較・導入前 | 第一候補AnimeTimm ConvNeXtV2-Huge、対抗Camie v2、基準WD。属性スコア比較と局所特徴比較を区別。 |
| Windowsローカル画像読解 | [local-vlm-20260906.md](local-vlm-20260906.md) | 2026-09-06 | 一次資料・実環境確認 | Qwen3-VL 4B/8Bの20枚比較。ComfyUIの公式ノードを利用。 |
| Phase 2 stack decision | [modern-stack.md](modern-stack.md) | 2026-09-04 | project decision | Accepted runtime and withdrawn Mage-Flow rationale. |
| Animaの選好学習 | [anima-preference-learning.md](anima-preference-learning.md) | 2026-09-06 | 上流コード確認・画質効果未実測 | 旧LoRAを固定基準にしたFlow-DPOの最小試作。 |
| NGによるLoRA修正 | [negative-feedback-lora-20260906.md](negative-feedback-lora-20260906.md) | 2026-09-06 | 一次資料確認・Anima局所修正は未検証 | DPO/KTO、属性・領域の学習、OKも悪化する問題、教材の構図差。Grok相談は起動障害で未実施。 |
| OKを使わない忘却学習 | [ng-only-erasing-20260906.md](ng-only-erasing-20260906.md) | 2026-09-06 | 著者コード照合・Anima実機未検証 | ESDの属性除去と少数画像のCLIP更新。必要入力、Anima移植差、局所性の限界。 |

Raw external material is retained only when it is needed to reproduce a future
decision; this index points to the decision summary used by the implementation.
