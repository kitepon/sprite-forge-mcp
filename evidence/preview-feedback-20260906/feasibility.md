# OK／NG学習の成立実測

2026-09-06。実装は `box/preference_probe.py` と `box/preference_loss.py`。foxのWindowsネイティブで実施。入力は利用者がOK／NGを指定したプレビュー一組、416×608、追加学習一更新。元サンプル・採用LoRA・キャラクター台帳は変更していない。

## 結果

- 順伝播・逆伝播・更新・保存・再読込みを完走。
- 初期の更新対象と固定基準の誤差は一致。損失0.6931471825、勾配ノルム0.0407481119。
- 保存LoRAと元LoRAの差の二乗和0.0020312814。固定基準の重みは完全一致、保存前後の推論最大差0。
- 所要10.16秒、学習部分の最大GPU割当9,622,857,728 bytes。前処理を含む全工程のピークではない。
- 元LoRAの処理後SHA256は `cfce144cab9dd729f81b20ae91dc526a4d0bbca7e809451386ca0d68dbed9a87`。処理前と一致。
- ComfyUIで新版のみを通常のLoraLoaderへ読み、Anima Base・強度0.8・seed37・28stepsで画像生成成功。履歴の実行時間は3.25秒。出力はfoxの `output/sprite-forge/preference-probe_00001_.png`、サーバーの隔離領域 `.cache/preview-feedback-probe/comfy-output.png` に保存。

機械結果は `feasibility-result.json`、生成条件と完了履歴は `comfy-history.json`。個人の画像やLoRA重みはcommitしない。

## 原因を確認して修正した点

1. 元LoRAにはQwenの重みも含まれた。DiTだけの読込みは失敗したため、全重みを読み、Qwenを固定してDiTだけ更新する。
2. Qwenのbfloat16本体とfloat32 LoRAはautocast下で処理する。
3. AnimaのAdaLNはautocast外で単精度入力を扱う。本体をfloat32で保持し、通常計算をbfloat16のautocast下で行う。上流checkoutは変更していない。

## 反証と限界

独立した読取り確認で、固定版上流のLoRAModuleによるCPU最小実験を実施。二重wrapperの初期出力差0、固定基準に勾配なし、更新対象に勾配あり、新規baseへ新版のみを読み込んだ出力差0を確認。保存後の実Anima単独読込みは上記ComfyUI実行で確認した。

損失のfocused testはPyTorch環境で2件成功。両ラベルが反対方向の更新を与え、ラベルを入れ替えると損失と勾配が変わることを確認。通常バックエンドにはPyTorchを追加せず、この2件は明示skipとなる。

成立試作のコード変更後の全Python試験は275件成功、上記2件skip。既存のStarlette由来の非推奨警告1件。

画像は目視で開き、人物画像として出力されていることを確認した。一更新の画像だけを髪型改善の証拠にはしない。未学習seedでの改善、OKだった特徴の保持、適切な学習量は後続の品質比較で確認する。
