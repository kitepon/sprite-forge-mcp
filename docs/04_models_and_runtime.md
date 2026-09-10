# 04 — Models and Runtime

GPU 機 fox は Windows 11 ネイティブの ComfyUI Portable（Python 3.13 / CUDA 13）を
NSSM で `:8188` に常駐させる。メインサーバーからは HTTP と SSH だけを使う。WSL2 は
Blackwell で CUDA 利用可能量が小さくなる未解決の問題があるため、推論・学習とも使わない。

| 用途 | 採用 | 実装上の入口 |
| --- | --- | --- |
| 素体・LoRA 学習 | Anima Base v1.0、量産は Turbo v1.1 | `workflows.anima_base` / `anima_train_network.py` |
| 任意ポーズ | Anima-Control-Pose preview-2 | Anima + LoRA の受入経路 |
| 編集・設定画 | JoyAI-Image-Edit-Plus | `workflows.joy_edit` |
| 透過 | ToonOut (`BiRefNet_toonout`) | `workflows.toonout` |
| 対象・衣装マスク | SAM 3.1 | `workflows.damage` |
| ダメージ版 | SAM 3.1 + JoyAI + マスク外復元 | `workflows.damage` |

Mage-Flow は初回比較で品質・速度とも優位だったが、2026-09-04 に Microsoft が公式重みを
取り下げたため採用しない。比較の測定値と切替根拠は
[09_modernization_bench.md](09_modernization_bench.md) に残す。

LoRA は fox の `C:\sf\train.py` から sd-scripts の `anima_train_network.py` を起動する。
既定は bf16、rank 16、alpha 16、learning rate `1e-4`。学習前に ComfyUI を `/free` で
解放し、モデルや学習器の操作をメインサーバーへ持ち込まない。
