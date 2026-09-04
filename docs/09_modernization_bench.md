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
