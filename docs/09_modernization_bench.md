# 近代化ベンチマーク

## 編集・設定画（Phase 1 / p1-edit）

既存の `bible_firemage` の正面素体を共通参照として、fox の ComfyUI 0.34.0
（RTX 5090, 32 GiB）で Mage-Flow-Edit と JoyAI-Image-Edit-Plus を比較した。
出力はすべて `ComfyUI/output/p1_edit/` に保存している。

### 条件

- 参照: `bible_firemage_panels/turn_front.png`（547×979）を ComfyUI input の
  `p1_edit_firemage_front.png` としてアップロード。
- 出力: 768×1024、固定 seed、正面・左右45度・左右側面・左右後方45度・背面の8方向、
  neutral/smile/angry の表情3種、カジュアル衣装1種を各モデルで1枚ずつ。
- Mage-Flow-Edit: `mage_flow_edit_int8_convrot` / Qwen3-VL 4B / Mage VAE,
  30 steps, CFG 5, Euler/simple。
- JoyAI-Image-Edit-Plus: int8 / Qwen3-VL 8B int8 / Wan VAE,
  30 steps, CFG 4, Euler/normal, CFGNorm pre-CFG。

### 結果

| 項目 | Mage-Flow-Edit | JoyAI-Image-Edit-Plus |
| --- | --- | --- |
| 生成成功 | 12 / 12 | 12 / 12 |
| 1枚の平均時間 | 5.40 秒（cold正面 10.47 秒、warm 4.69–6.78 秒） | 31.19 秒（cold正面 36.85 秒、warm 29.78–30.28 秒） |
| 常駐 VRAM | 14.22 GiB | 25.94 GiB |
| 同一人物性 | 髪型・王冠・炎の衣装・杖を全12枚で安定して維持 | 全12枚で人物は維持するが、側面の杖と衣装シルエットに揺れがある |
| 背面 | 顔を出さず、髪・炎衣装・杖の背面を一貫して生成 | 背面は成立するが、衣装・杖の輪郭変動がMageより大きい |
| 表情・衣装 | 3表情を明確に分け、カジュアル衣装でも人物特徴を維持 | 3表情・衣装変更は成功するが、処理時間とVRAMが大きい |

出力パス（`p1_edit/` 配下）は次のとおり。各行の先頭は Mage-Flow-Edit、後尾は JoyAI。

| 指示 | Mage-Flow-Edit | JoyAI-Image-Edit-Plus |
| --- | --- | --- |
| front | `mage_smoke_front_00001_.png` | `joy_smoke_front_00001_.png` |
| front-right-45 | `mage_front_right_45_00002_.png` | `joy_front_right_45_00001_.png` |
| right-profile | `mage_right_profile_00001_.png` | `joy_right_profile_00001_.png` |
| rear-right-45 | `mage_rear_right_45_00001_.png` | `joy_rear_right_45_00001_.png` |
| rear | `mage_rear_00001_.png` | `joy_rear_00001_.png` |
| rear-left-45 | `mage_rear_left_45_00001_.png` | `joy_rear_left_45_00001_.png` |
| left-profile | `mage_left_profile_00001_.png` | `joy_left_profile_00001_.png` |
| front-left-45 | `mage_front_left_45_00001_.png` | `joy_front_left_45_00001_.png` |
| neutral | `mage_neutral_00001_.png` | `joy_neutral_00001_.png` |
| smile | `mage_smile_00001_.png` | `joy_smile_00001_.png` |
| angry | `mage_angry_00001_.png` | `joy_angry_00001_.png` |
| casual outfit | `mage_casual_outfit_00001_.png` | `joy_casual_outfit_00001_.png` |

### 採用

**Mage-Flow-Edit を採用する。** 同一人物性と後ろ姿は両者で受入可能だったが、
Mage-Flow-Edit は JoyAI より約5.8倍高速で、常駐VRAMも約11.7 GiB小さい。
設定画を反復生成する用途では、この差が直接的な優位になる。

## 透過（Phase 1 / p1-matte）

同一の素体比較初回出力（各 1024×1024）に対して、ComfyUI-RMBG の
`BiRefNet_toonout` と ComfyUI ネイティブ SAM 3.1 Multiplex を比較した。
SAM 3.1 は短いテキストプロンプト `character` を使い、出力 MASK を反転して
RGBA の alpha とした（SAM の MASK 極性は背景=white のため）。

### 条件

| 入力 | fox 上の元画像 | SHA-256 |
| --- | --- | --- |
| Anima Base | `output/p1-base/anima_00001_.png` | `a7ea5b485686dc742441b597821ba5ef20831d221f366c07bfea78eafb299509` |
| Mage-Flow | `output/p1-base/mage-flow_00001_.png` | `963868c04c291e887469316f38fd1f6540716c6d3c70cd235d8645f752016f79` |
| Krea 2 raw | `output/p1-base/krea2_00001_.png` | `316b6d276300511718eda7ec202a3940e341cb0b5e28a17db869631ff4361379` |

- ToonOut: `BiRefNetRMBG`, model `BiRefNet_toonout`, sensitivity 1.0,
  mask blur / offset 0, alpha background。
- SAM 3.1: `sam3.1_multiplex_fp16.safetensors` → `CLIPTextEncode` (`character`)
  → `SAM3_Detect` (threshold 0.5, refine iterations 2) → `InvertMask`。
- 各入力・各方式の ComfyUI prompt は成功した。ToonOut は
  `8f7cfad7` / `e774de79` / `3f089bad`、SAM 3.1 の RGBA 最終実行は
  `dd2b1f8f` / `cf657a85` / `0d014dc9`。

### 結果

| 判定項目 | ToonOut | SAM 3.1 |
| --- | --- | --- |
| 成功 | 3 / 3 | 3 / 3 |
| 四隅 alpha | 全12点が 0 | 全12点が 0 |
| 髪先・指・杖 | 細い髪、指、杖先まで連続して残る | 主体は捉えるが、細い髪と杖の先端を丸める傾向 |
| 半透明の縁 | 8,750 / 13,025 / 16,014 px の部分 alpha（Anima / Krea / Mage） | 3画像とも部分 alpha 0 px（hard mask） |
| 縁のにじみ | 背景の色漏れなし | 背景の色漏れなし。ただし hard mask のため髪際が硬い |

出力は `ComfyUI/output/p1-matte/` に保存した。各方式に
`toonout-{anima,mage-flow,krea2}_00001_.png` と
`sam31-inverted-{anima,mage-flow,krea2}_00001_.png` がある。

### 採用

**ToonOut を採用する。** 両方式とも文字プロンプト付きの実行と四隅 alpha=0 を満たした。
しかし ToonOut は3入力すべてで部分 alpha を保持し、髪先・指・杖の細部も SAM 3.1 の
hard mask より自然に残した。SAM 3.1 は文字・点プロンプトによる対象マスク抽出の補助手段として
残すが、sprite の最終 RGBA 化は ToonOut を標準とする。
