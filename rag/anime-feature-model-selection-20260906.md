# アニメのNG髪型を抽出するモデルの選定

取得日：2026-09-06。一次資料に基づく比較試験の優先順位。導入・新規推論は今回行わない。

## 導入時の実測追記（同日）

選定後にユーザーが導入を承認。Hugging Face認証後、revision `18177355d1448a69bafb0410a0608e144f714e8b` の重み・設定・タグをWindowsへ取得した。

`dghs-imgutils 0.19.0` は `numpy<2` を要求し、既存ComfyUI環境での `pip install --dry-run` はNumPyのソースビルド準備中に `Cannot import 'mesonpy'` で失敗した。依存は変更していない。

試作ノード `box/animetimm_node.py` は配布 `preprocess.json` と公式の [pad.py](https://github.com/deepghs/imgutils/blob/main/imgutils/data/pad.py)、[torchvision.py](https://github.com/deepghs/imgutils/blob/main/imgutils/preprocess/torchvision.py) を確認して実装した。縦横比を維持してbilinear縮小、白い余白を中央配置し、指定のResize・CenterCrop・ToTensor・Normalizeへ渡す。既存Pillow/torchvisionを使い、補助ライブラリの依存不成立を隠した自動切替はしない。推論はComfyUI内で実行し、閾値以下を含む全タグスコアを返す。

## 結論

第一候補は `animetimm/convnextv2_huge.dbv4-full`。アニメ用の多ラベル分類と特徴抽出を目的として学習され、属性スコアを返す。自由文生成より今回の髪型比較に直接対応する設計である、という適性判断。髪型に限定した精度の世界一を示す資料ではない。

## 一次資料の比較

| 候補 | 根拠と判断 |
| --- | --- |
| [AnimeTimm ConvNeXtV2-Huge](https://huggingface.co/animetimm/convnextv2_huge.dbv4-full) | 第一候補。692.6Mパラメータ、512入力、1.2T FLOPs。一般タグのMacro@Best F1は0.494。PyTorch/timm例あり。 |
| [AnimeTimm EVA-Giant](https://huggingface.co/animetimm/eva_giant_patch14_560.dbv4-full) | 同じdbv4-full評価で比較可能。1.0Gパラメータ、560入力、3.2T FLOPs。一般タグMacro@Best F1は0.489。大きさ・新しさだけでこちらを選ばない。 |
| [AnimeTimm SigLIP-Giant](https://huggingface.co/animetimm/vit_giantopt_patch16_siglip_384.dbv4-full) | 同じdbv4-full評価。1.2Gパラメータ、実際の評価入力512、2.3T FLOPs。一般タグMacro@Best F1は0.486。画像テキスト検索用の元SigLIPと、この分類用派生重みを混同しない。 |
| [Camie Tagger v2](https://huggingface.co/Camais03/camie-tagger-v2) | 軽量な対抗候補。143M、512入力、ONNX/Safetensors配布。タグが画像パッチへ注意を向ける構造。一般タグMacro F1は0.346だが、AnimeTimmと評価データ・語彙が違うため大小を直比較しない。 |
| [WD EVA02-Large v3](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) | 比較基準。アニメ属性分類、ONNXバッチ推論に対応。資料のMacro F1 0.4772を他データセットの総合値と比較しない。 |
| [PixAI Tagger v0.9](https://huggingface.co/pixai-labs/pixai-tagger-v0.9) | 新しいキャラクターの網羅と再現率を重視。WD EVA02の画像エンコーダを固定して分類部を更新。髪型の細部識別が改善した根拠とは別なので第一候補にしない。 |
| [DINOv3](https://github.com/facebookresearch/dinov3) | パッチ特徴の対応・局所比較に適する補助候補。アニメ髪型のタグや自然言語のNG理由を単独で出すモデルではない。最初から追加必須とはしない。 |

公開総合評価にはキャラクター認識なども混ざるため、今回は一般タグ評価を参照した。一般タグF1も髪型だけの精度ではなく、同条件の20枚による比較試験へ進める根拠として使う。

## 処理案

1. 全20枚から属性スコアを取得する。閾値以下を切り捨てず、比較用のスコアを保存する。
2. ユーザー理由に関連する属性に絞って分布を比較する。NG13枚を全て同じ髪型にまとめず、17の長髪は別理由として保持する。未選択7枚は比較専用。
3. NG群と残りのスコア差を手掛かりにするが、差だけを因果的なNG理由と扱わない。衣装・画風を混ぜない。
4. 具体的なNG属性名をESD概念候補にする。ツインテールのスコアが低いというだけでtwintails自体を消去対象にしない。スコア数値はAnimaの条件ベクトルへ直接投入できない。
5. 固定語彙で表せない細部が残る場合だけ、局所特徴の比較を追加する。タグスコア比較は、生の局所特徴ベクトル比較とは区別する。

モデルは日本語の指示を直接読む必要がない。理由から比較対象の属性を選ぶ処理と、画像から属性を検出する処理を分ける。文章への変換が必要ならスコアと理由だけを渡し、20枚を外部モデルへ送らない。

## Windowsと導入条件

AnimeTimmの正規例はPyTorch/timm。foxの既存WindowsネイティブPyTorchを使う構成を候補とする。692.6M重みのFP32素サイズは約2.77GBで、32GB GPUに対する配置候補として妥当だが、これを総VRAM実測値とはしない。

AnimeTimmはHugging Face上で条件同意が必要、ライセンス表記はGPL-3.0。取得前にユーザーのアカウントで条件を確認する。未承認の同意を代行しない。CamieはGPL-3.0、WDはApache-2.0。ONNX経路のWindows GPU依存は[公式CUDA EP資料](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)を正とし、foxのCUDA13環境へCUDA12向けDLLを混同して入れない。

## 比較試験の判定対象

ツインテールの有無、短い下ろし髪、17の長い後ろ髪を画像単位で確かめる。既に与えられたNG指定以外の採否ラベルを捏造しない。推論時間・VRAMと誤検出を併記し、キャラクター名の正答や総合タグF1で代用しない。
