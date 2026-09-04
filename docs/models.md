# Models manifest（fox の ComfyUI に配置する候補）

sprite-forge は推論を GPU box（fox）の ComfyUI に委ねる。ここでは
`C:\Users\kite_\ComfyUI\ComfyUI\models` を起点とし、Phase 1 で比較する
新顔の候補を正確なファイル名で配置する。旧世代の Illustrious、Qwen-Image-Edit-2511、
SDXL ControlNet、rembg は配置しない。

## 配置表

| 用途 | 配置先 | ファイル | 配布元 |
|---|---|---|---|
| Anima Base v1.0 | `diffusion_models/` | `anima-base-v1.0.safetensors` | `circlestone-labs/Anima` |
| Anima Turbo v1.1 | `diffusion_models/` | `anima-turbo-v1.1.safetensors` | `circlestone-labs/Anima` |
| Anima text encoder | `text_encoders/` | `qwen_3_06b_base.safetensors` | `circlestone-labs/Anima` |
| Anima / Krea VAE | `vae/` | `qwen_image_vae.safetensors` | `circlestone-labs/Anima` |
| Anima Control-Pose preview-2 | `loras/` | `anima_pose_preview2.safetensors` | `Claquasse/Anima-Control-Pose` |
| JoyAI-Image-Edit-Plus | `diffusion_models/` | `joyai_image_edit_plus_int8_convrot.safetensors` | `jdopensource/JoyAI-Image-Edit-Plus-ComfyUI` |
| JoyAI text encoder | `text_encoders/` | `qwen3vl_8b_joyimage_edit_plus_int8_convrot.safetensors` | `jdopensource/JoyAI-Image-Edit-Plus-ComfyUI` |
| JoyAI VAE | `vae/` | `wan_2.1_vae.safetensors` | `jdopensource/JoyAI-Image-Edit-Plus-ComfyUI` |
| Krea 2 | `diffusion_models/` | `krea2_raw_int8_convrot.safetensors` | `Comfy-Org/Krea-2` |
| ToonOut | `RMBG/BiRefNet/` | `BiRefNet_toonout.safetensors`, `birefnet.py`, `BiRefNet_config.py`, `config.json` | `1038lab/BiRefNet` |
| SAM 3.1 Multiplex | `checkpoints/` | `sam3.1_multiplex_fp16.safetensors` | `Comfy-Org/sam3.1` |

ComfyUI-RMBG は `RMBG/BiRefNet/` を読む。SAM 3.1 は ComfyUI ネイティブ node の
`SAM3_*` 系から `checkpoints/sam3.1_multiplex_fp16.safetensors` を選ぶ。全モデルを
置いた後は ComfyUI を再起動し、`/object_info` の各 loader の選択肢に上記の重みが
現れることを確認する。

## ライセンス上の注意

- Anima と Anima Control-Pose は非商用モデルライセンスである。生成物は商用利用できる。
  LoRA は配布しない前提で扱い、モデルや LoRA の配布・販売が必要になった時だけ
  Circlestone へ商用ライセンスを確認する。
- JoyAI-Image-Edit-Plus は Apache-2.0、ToonOut は各配布元の条件、SAM 3.1 は
  SAM License に従う。Mage-Flow 系は 2026-09-04 の公式取り下げにより採用対象から
  除外した。

## LoRA 学習器

Anima Base v1.0 のキャラクター LoRA は fox の Python 3.13 仮想環境
`C:\\sf\\venv` と、p0-trainer が導入した sd-scripts
`C:\\sd-scripts\\anima_train_network.py` を使う。入口は `C:\\sf\\train.py` であり、
Anima DiT、`qwen_3_06b_base.safetensors`、`qwen_image_vae.safetensors` と dataset TOML を
渡して `accelerate launch` を起動する。

- 学習精度は `bf16`、LoRA rank / alpha はともに 16、学習率の初期値は `1e-4` とする。
- p1-lora では JoyAI-Image-Edit-Plus の設定画12枚と caption を教材に 12 step を完走し、
  `C:\\sf\\output\\anima_joy_sprite_lora\\anima_joy_sprite_lora.safetensors`
  （66,232,904 bytes）を得た。
- 推論では Anima Base → `anima_pose_preview2.safetensors` → 学習済み LoRA の順に
  `LoraLoaderModelOnly` を接続し、`AnimaControlApply` に同 pose adapter を指定する。
  任意ポーズには `AnimaPoseControl` を使う。量産は Anima Turbo v1.1、編集・設定画は
  JoyAI-Image-Edit-Plus とする。
