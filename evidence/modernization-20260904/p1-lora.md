# p1-lora — Anima LoRA の実走

## 裁定と教材

- 2026-09-04 のオーナー裁定で、Hugging Face 上の Microsoft Mage-Flow
  （Base / RL / Turbo / Edit）が公式に取り下げられ、ログイン済みでも 404 となることを
  確認した。そのため Mage-Flow、SimpleTuner、ai-toolkit の経路は採用せず、Anima Base
  v1.0 と p0-trainer の sd-scripts に切り替えた。量産用は Anima Turbo v1.1、編集用は
  JoyAI-Image-Edit-Plus である。
- 中止した Mage-Flow 経路では、公式 `rustup`、vcpkg、Visual Studio Build Tools、Ninja、
  LLVM を導入して `trainingsample 0.3.2` の CPython 3.13 wheel をビルドした。続く
  SimpleTuner 4.5.1（`triton-windows 3.3.1post21`）は Mage-Flow import 時に Windows
  非対応の `fcntl` で停止し、ai-toolkit は Python 3.12 環境で依存導入まで成功したが
  Mage-Flow 重みの公式取り下げで学習対象を失った。いずれも以後の学習器には使わない。
- 教材は p1-edit の JoyAI 出力 12 枚
  `C:\\Users\\kite_\\ComfyUI\\ComfyUI\\output\\p1_edit\\joy_*.png` を
  `C:\\sf\\anima-lora-dataset\\` に複製した。全画像に
  `sprite_subject, a full-body JRPG fire mage character with red twin tails, crown, flame outfit, and staff, clean game illustration`
  の caption を添えた。
- dataset TOML は 1024px、batch size 1、bucket 有効、caption extension `.txt`、
  `num_repeats = 1` とした。

## 学習実行

fox の `C:\\sf\\venv`（Python 3.13）で、既存の
`C:\\sf\\train.py` を入口に以下の設定で実行した。

```text
anima_train_network.py / bf16 / rank 16 / alpha 16 / learning rate 1e-4
max_train_steps 12 / Anima Base v1.0 / qwen_3_06b_base / qwen_image_vae
```

- 12 images / 12 batches / 12 steps が完走した。
- Qwen3 LoRA 196 モジュール、Anima DiT LoRA 280 モジュールを作成した。
- 最終 `avr_loss=0.05`、exit code 0。
- 出力: `C:\\sf\\output\\anima_joy_sprite_lora\\anima_joy_sprite_lora.safetensors`
  （66,232,904 bytes、作成時刻 2026-09-04 11:30:43）。

## Control-Pose 受入

公式 `Claquasse/Anima-Control-Pose` の `comfyui/anima_control_lora` と
`comfyui/ComfyUI-anima-pose-control` を fox の ComfyUI custom_nodes へ導入し、
後者の `requirements.txt`（rtmlib、onnxruntime、opencv-contrib-python）を embedded
Python 3.13 に導入して ComfyUI を再起動した。

- 入力骨格: `p1_pose_casting_skeleton.png`（1024px、杖を上げ、右腕を前へ伸ばし、
  両脚を開くキャスティング・ランジ）。
- グラフ: Anima Base → pose adapter LoRA (1.0) → 学習済み LoRA (0.8) →
  `AnimaPoseControl` (R0_thin, 1024px) → `VAEEncode` → `AnimaControlApply`
  (strength 1.0) → `CFGZeroStar` → Euler/simple 28 steps, CFG 4。
- prompt: `de4b679c-05ef-492f-8b5e-7a409fc10d2e`、status `success`、実行時間 18.111 秒。
- 出力: `C:\\Users\\kite_\\ComfyUI\\ComfyUI\\output\\p1-lora\\anima_joy_control_pose_00001_.png`
  （1024×1024、SHA-256
  `51f2a8fab512d87fd376b58c7931c91004582a10284237cc97a35c33f3cfe29d`）。

出力は赤いツインテール、王冠、炎の衣装、杖を保ち、骨格の大きく開いた両脚と
前方へ伸ばした腕に沿う詠唱ポーズを生成した。これを Anima + LoRA + Control-Pose の
受入結果とする。
