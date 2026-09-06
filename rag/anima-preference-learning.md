# Animaの選好学習の成立確認

取得日: 2026-09-06。確度: 上流コードと一次資料を確認済み。Animaでの画質改善は未実測。

foxのsd-scriptsは `https://github.com/kohya-ss/sd-scripts.git` のcommit `37a1cbbc5725ed2a3575506e7bd2001c9908ac92`。2026-09-06のSSH観測で作業ツリーの変更なし。GPUはRTX 5090、メモリー32607 MiB。これは観測時点の証拠であり、現在値の設定正本ではない。

[当該版のAnima学習コード](https://github.com/kohya-ss/sd-scripts/blob/37a1cbbc5725ed2a3575506e7bd2001c9908ac92/anima_train_network.py) は `noise - latents` を目標とする。テキストとVAEの前処理・LoRAの読込みはこの版のライブラリを再利用する。

[SimpleTunerのFlow-DPO設計](https://github.com/bghira/SimpleTuner/blob/main/documentation/experimental/FLOW_DPO.md) は、同一prompt・noise・timestepで選好画像と却下画像の誤差を比較する。試作の損失はそのmargin形式を用い、潜在要素の平均二乗誤差に対して固定betaを掛ける。自動beta、マスク、追加の損失項は導入しない。必要な係数は実測で判断する。

今回の既存LoRA修正では固定基準にも旧キャラクターLoRAが必要。更新対象を単に無効にして素のAnimaを基準とする方法は使わない。モデル本体を一つだけ持ち、旧LoRAを固定したものと更新対象の複製を切り替える。生成時のLoRA強度も同じにする。

一組・一更新による成立確認は、勾配方向、旧LoRA保持、出力重みの変化、保存・再読込みを確認するためのもの。学習データを使った損失低下を、未学習画像の髪型改善の証拠としない。後続の実画像比較で確認する。

実機の元LoRAにはDiTとQwenテキストエンコーダーの両方の重みがある。試作は全キーを厳密に読み、Qwenの重みを固定した条件をキャッシュし、DiTのみ更新する。新版にもQwenの重みを保持する。

当該Anima実装のAdaLNはautocastの外で時刻由来の単精度テンソルを処理する。試作で本体をbfloat16にすると型不一致を再現したため、本体はfloat32、通常の順伝播はbfloat16のautocastとした。QwenのLoRA適用時もautocastを使う。上流コードを変更せず成立した。学習一更新・保存再読込みの実測は約10.16秒、学習部分の最大割当は9,622,857,728 bytes。これは416×608・一組での成立測定であり、通常解像度・複数組の性能値ではない。
