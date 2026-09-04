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
| Mage-Flow | `diffusion_models/` | `mage_flow_bf16.safetensors`, `mage_flow_int8_convrot.safetensors` | `Comfy-Org/Mage-Flow` |
| Mage-Flow-Edit | `diffusion_models/` | `mage_flow_edit_bf16.safetensors`, `mage_flow_edit_int8_convrot.safetensors` | `Comfy-Org/Mage-Flow` |
| Mage text encoder | `text_encoders/` | `qwen3vl_4b_bf16.safetensors` | `Comfy-Org/Mage-Flow` |
| Mage VAE | `vae/` | `mage_flow_vae_bf16.safetensors` | `Comfy-Org/Mage-Flow` |
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
- Mage-Flow / Mage-Flow-Edit は MIT、JoyAI-Image-Edit-Plus は Apache-2.0、
  ToonOut は各配布元の条件、SAM 3.1 は SAM License に従う。
