# p0-trainer — fox の Anima LoRA 学習器

## 実施内容

- fox を Windows ネイティブのまま使い、`C:\\sd-scripts` に kohya
  sd-scripts を配置した。確認した commit は
  `37a1cbbc5725ed2a3575506e7bd2001c9908ac92` で、
  `anima_train_network.py` を含む。
- `C:\\sf\\venv` に Python 3.13 用の PyTorch 2.14.0+cu130、accelerate
  1.6.0 と sd-scripts requirements を導入した。`torch.cuda.is_available()`
  は `True` を返した。
- 追跡対象の `box/train.py` を `C:\\sf\\train.py` として配置した。この入口は
  TOML、出力名、Anima DiT、Qwen3、VAE を受け取り、ComfyUI の `/free` を HTTP POST
  してから `accelerate launch ... anima_train_network.py` を起動する。PowerShell
  のコードや WSL2 は使わない。
- `box/smoke-dataset.toml` は、fox の `C:/sf/smoke` を指定する最小の kohya dataset
  TOML として追加した。

## 最終確認

2026-09-04 に fox で次を実行し、全て成功した。

1. `py -3.13 C:\\sf\\train.py --help` が成功し、必須の dataset TOML、出力名、
   Anima DiT、Qwen3、VAE の引数を表示した。
2. `C:\\sf\\venv\\Scripts\\python.exe anima_train_network.py --help` が成功し、
   Anima 固有の `--qwen3`・`--vae` と `networks.lora_anima` を含む学習器が起動した。
3. Anima Base v1.0、`qwen_3_06b_base`、`qwen_image_vae` と、3 枚の smoke 教材、
   `--max-train-steps 3 --mixed-precision bf16` を `C:\\sf\\train.py` に渡した。
   CUDA 上で LoRA モジュール（Qwen3 196、DiT 280）が作成され、3/3 step が完走した。
   最終平均 loss は `0.0648`、出力は
   `C:\\sf\\output\\smoke-anima.safetensors`（66,232,480 bytes、SHA-256
   `C0F281F65F8FCE23416E5CD595E0816F0FC5B624C02E2FA90E29F20A8A4C095`）である。

この smoke 教材には caption ファイルが存在しない旨の警告が出たが、入口・モデル読込・
bf16 CUDA 学習・safetensors 保存の受入経路には影響せず、3 step の実走は成功した。本番の
教材は caption を添えて同じ TOML 形式で渡す。
