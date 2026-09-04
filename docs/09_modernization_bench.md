# 近代化ベンチマーク

## 素体生成（Phase 1 / p1-base）

fox の ComfyUI 0.34.0（RTX 5090）で、同一の JRPG キャラクター指示を使い
Anima Base v1.0、Mage-Flow int8、Krea 2 raw int8 を各 4 枚ずつ比較した。
すべて 1024×1024、seed `2026090401`–`2026090404`、正面の neutral A-pose とした。

| 候補 | 平均時間 | 画質判定 | 代表画像パス |
| --- | ---: | --- | --- |
| Anima Base v1.0 | 6.65 秒 | 2/4 は良好だが、残る 2 枚は人物が小さ過ぎるか顔が黒く潰れた | `C:\\Users\\kite_\\ComfyUI\\ComfyUI\\output\\p1-base\\anima\\2026090401_00001_.png` |
| Mage-Flow int8 | **3.71 秒** | **4/4** で全身・正面・銀髪・teal/navy 配色・杖・淡色背景が維持され、輪郭が最も明瞭 | `C:\\Users\\kite_\\ComfyUI\\ComfyUI\\output\\p1-base\\mage-flow\\2026090401_00001_.png` |
| Krea 2 raw int8 | 3.96 秒 | 4/4 で線と人物外縁が軟焦点になり、小物混入・頭部の潰れもあった | `C:\\Users\\kite_\\ComfyUI\\ComfyUI\\output\\p1-base\\krea2\\2026090401_00001_.png` |

各候補の残る出力は、それぞれの `p1-base/{anima,mage-flow,krea2}/`
ディレクトリに `2026090402_00001_.png`–`2026090404_00001_.png` として保存した。
Anima は `sd-scripts/anima_train_network.py` の学習器を p0-trainer で smoke 実証済みであり、
Krea 2 の musubi と Mage-Flow 専用学習器は fox では未検証である。

### 採用

初回比較では Mage-Flow が最良だったが、2026-09-04 に配布元 Microsoft が
Mage-Flow（Base / RL / Turbo / Edit）を Hugging Face から公式に取り下げ、
ログイン済みでも 404 となった。従って比較値は履歴として残すが、Mage-Flow は採用対象から
除外する。**以後の素体生成は Anima Base v1.0 を採用し、量産は Anima Turbo v1.1 を使う。**
Anima Base は p0-trainer の `anima_train_network.py` で LoRA 学習を実走済みであり、
本書の p1-lora でも同じ経路を受入した。

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

初回比較では Mage-Flow-Edit が速度・VRAMで優勢だったが、素体と同じ公式取り下げにより
利用不能となった。**JoyAI-Image-Edit-Plus を編集・設定画の採用器とする。** 12/12 の
出力成功と人物特徴の維持は確認済みであり、p1-lora の教材にもこの JoyAI 出力を使用した。

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

## ダメージ版（Phase 1 / p1-damage）

初回検証では Mage-Flow-Edit を用い、SAM 3.1 のテキストマスクで火の魔術師の
衣装だけを編集し、元画像をマスク外へ戻す経路を fox の ComfyUI 0.34.0（RTX 5090）で確認した。

### 条件

- 入力: ComfyUI input の `p1_damage_firemage_base.png`（768×1024、SHA-256
  `f6be351a437fce9aa6bd3d47e10596f7b94658159e67fa986f6bc3fdc884aaf3`）。
- SAM 3.1 Multiplex: `character`（threshold 0.50）で主体 alpha、`red robe clothing`
  （threshold 0.45）で衣装マスクを作った。どちらも refine iterations 2。
- 編集（履歴検証）: `mage_flow_edit_int8_convrot.safetensors`、Qwen3-VL 4B、Mage VAE、seed 41002、
  30 steps、CFG 5、Euler/simple。顔・髪・王冠・手・杖・ポーズ・canvas を維持し、赤い
  ローブと袖だけを torn / scorched / battle-damaged にする指示を与えた。
- 復元: `ImageCompositeMasked(destination=base, source=edited, mask=clothing)` の後、
  character alpha を `JoinImageWithAlpha` に渡した。

### 結果

主 workflow `a9e743c0-c13f-49f9-b706-06537d82cdb4` は成功し、10.169 秒で raw と
合成 RGBA を出力した。最終出力は
`ComfyUI/output/p1-damage/firemage-damaged-composited_00001_.png`
（SHA-256 `020dbecaafc62ed67ebbf0258fd3d2a47c52502614aba78d3eba70753ccd3dc5`）、
raw は `firemage-damaged-raw_00001_.png`、SAM マスク確認は
`f33a5343-5321-4dbd-9b49-43850b02ff72` で成功した。

| 測定 | 値 |
| --- | --- |
| 出力サイズ | 768×1024 |
| 合成 RGBA の四隅 alpha | 0 / 0 / 0 / 0 |
| 衣装マスク内の変化 | 410,546 px |
| 衣装マスク外の変化 | 0 px（pixel-exact） |
| bbox 中心差（白背景を除く RGB < 250 の閾値） | x -7.0 px, y +0.5 px（記録のみ・gate 外） |

目視では、ローブの裾と袖に焦げ・破れが入り、顔、髪、王冠、手、杖は元画像のまま保たれた。
マスク外復元により、編集器の出力が衣装外へ及ぼす変化は残らない。

## ポーズ指定（Phase 1 / p1-pose）

初回の Mage-Flow-Edit 第2参照方式は、骨格線が画像へ混入しポーズ追従も不十分だった。
その後、Microsoft の Mage-Flow 公式取り下げにより前提そのものが失効したため、
Anima Base を素体とする `Anima-Control-Pose preview-2` に切り替えた。

### 条件と結果

- 教材由来の Anima LoRA: `anima_joy_sprite_lora.safetensors`（rank 16 / alpha 16、
  JoyAI-Image-Edit-Plus の12枚で12 step学習）。
- 骨格参照: `p1_pose_casting_skeleton.png`（1024×1024、SHA-256
  `b1bdc60e93e059d163dbc097cc14ea16450416786d5e7f09b15b210ed8706cef`）。
- Anima Base → pose adapter LoRA 1.0 → 学習済み LoRA 0.8 →
  `AnimaPoseControl`（R0_thin）→ `AnimaControlApply`（strength 1.0）→
  Euler/simple 28 steps、CFG 4 で実行した。
- ComfyUI prompt `de4b679c-05ef-492f-8b5e-7a409fc10d2e` は成功し、18.111 秒で
  `ComfyUI/output/p1-lora/anima_joy_control_pose_00001_.png` を出力した
  （1024×1024、SHA-256
  `51f2a8fab512d87fd376b58c7931c91004582a10284237cc97a35c33f3cfe29d`）。

| 判定 | 観測 |
| --- | --- |
| 同一性 | 赤いツインテール、王冠、炎の衣装、杖を保った。 |
| ポーズ追従 | 大きく開いた両脚、前方へ伸ばした腕、杖を上げた詠唱ポーズを生成した。 |
| 出力品質 | 骨格線は描画として残らず、1024px のキャラクター画像として利用できる。 |

### 採用

**Anima Base + 学習済み LoRA + Anima-Control-Pose を任意ポーズの受入経路として採用する。**
Mage-Flow 系の比較結果は公式取り下げ前の履歴であり、後続工程の前提にはしない。
