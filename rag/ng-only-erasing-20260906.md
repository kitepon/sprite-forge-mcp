# OK画像を使わない忘却学習のAnima適用調査

取得日: 2026-09-06。確度: 論文・著者公開コード・既存Anima試作の静的照合。Animaでの忘却効果・保持・必要VRAMは未実測。今回は調査のみで学習・モデル変更なし。

## 結論

両方式とも研究と公開実装があるが、Anima対応の完成済み学習器ではない。第一候補は属性除去を持つESDの移植。少数画像方式はNG実例を使えるが、CLIPの直接更新からQwen3のLoRA更新へ変更する必要があり、原論文の追試とは区別する。OK画像・合成画像・前後unionマスクは使用しない方針に変更された。旧選好学習の継続は今回の指示に含まれない。

## ESD

- [著者解説](https://erasing.baulab.info/)は、除去対象の文章と凍結モデルの予測から、対象を避ける教師信号を作る方式。承認OK画像を要求しない。対象外の概念への干渉も限界として報告している。
- [著者README](https://github.com/rohitgandikota/erasing)に、`erase_concept`と`erase_from`を分けてcowboyからhatを除く例がある。これは属性除去の公開実装であって、キャラクター髪型の保持保証ではない。
- [共通学習コード](https://github.com/rohitgandikota/erasing/blob/main/utils/esd_trainer.py)の対応表はSD/SDXL/FLUX/FLUX2 Klein。Animaはない。学習目標は凍結モデルの対象条件予測から除去概念と空条件の予測差を引く。公開入口は選択パラメータを直接更新し、Anima形式LoRAを出力しない。
- 推論: FLUX向け実装があるためFlow系への適用例はある。Animaでは時刻・潜在形式・条件付け・サンプリングを合わせ、旧キャラクターLoRA込みのモデルを凍結基準として、更新対象をAnima LoRAに限定する移植が考えられる。単にmodel名を変更して実行することはできない。
- 入力案は「消したい髪型の文章」「対象キャラクターの条件」「既存重み」。NG画像は文章が正しい髪型を指しているかの確認・評価に使えるが、原方式の必須学習入力ではない。文章で識別できない固有の形への適性は低い可能性がある。

## 少数画像による忘却

- [論文2.2〜3.2](https://arxiv.org/html/2405.07288v2)は消す概念を含む画像とcaptionを使い、ノイズ予測誤差を増やすようテキストエンコーダーを更新する。代表条件は4画像。4枚が理論的な最低枚数という意味ではない。
- [train.py](https://github.com/fmp453/few-shot-erasing/blob/main/train.py)はU-Netを固定し、CLIPのMLPと最後のattentionを更新、負のMSEを最小化する。OK画像を要求せず、出力はテキストエンコーダー本体。通常のDiTキャラクターLoRAではない。
- [data.py](https://github.com/fmp453/few-shot-erasing/blob/main/data.py)は概念名をcaptionテンプレートへ入れ、画像全体を潜在化する。髪の形だけを分離する領域指定はない。パーツ画像だけで形・色・質感を分離できると解釈しない。
- AnimaではCLIPの代わりにQwen3からLLM Adapterへ条件を渡す。Qwen3 LoRAの学習と生成時の適用を成立させる必要がある。既存試作はテキスト重みを固定し、埋込みをno_gradでキャッシュしてencoderを破棄するので、そのまま負の損失に変えても原方式にならない。
- 推論: Qwen3経由の勾配を保持し、DiT本体を固定して負のFlow誤差を最小化する試作は構成可能。ただしQwen3とLoRAへの変更、キャラクター条件付きの髪だけの忘却は未実証。長く学習すれば良い目的関数ではなく、対象外の劣化も実画像で測る必要がある。

## 現行コードとの接続根拠

- `box/preference_train.py`は既存LoRA読込み、凍結基準と更新LoRA切替、Anima順伝播、`noise - latents`のFlow目標、保存再読込みを既に持つ。ESDの条件差とサンプリングは未実装。
- [使用版lora_anima.py](https://github.com/kohya-ss/sd-scripts/blob/37a1cbbc5725ed2a3575506e7bd2001c9908ac92/networks/lora_anima.py)はDiTとQwen3のLoRA生成・保存を持つ。[strategy_anima.py](https://github.com/kohya-ss/sd-scripts/blob/37a1cbbc5725ed2a3575506e7bd2001c9908ac92/library/strategy_anima.py)はQwen3出力とT5 token IDsを返す。T5 tokenizerの存在をT5 encoderの学習と混同しない。

## 次の検証の提案

まずESDの対象条件と髪型の文章が、元モデル上で狙ったNGを識別できるか確認する。成立した場合に、Anima LoRAへのESD移植を隔離領域で試す。評価はNG髪型の発生、他の髪型への崩れ、顔・衣装・画風の維持、NG語をpromptに含めない通常生成を分ける。OK教材で代用しない。この提案は未実施で、今回の調査完了と学習実証完了は別である。
