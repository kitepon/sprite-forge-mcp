# 一枚シート判定の本番実機目視

2026-09-09。PR #3（`2cc745f`）は main に着地済みで、本番 `/home/kite/sprite-forge-mcp` も同じ commit で就役済みだった。再配備はしていない。検証例として本番キャラクター「ベル」（key `ndac1de01`）を使い、学習は動かしていない。

## 入力

| 項目 | 値 |
| --- | --- |
| キャラクター | ベル / `ndac1de01` |
| LoRA | `ndac1de01_preference_f24a5a97-167b-492e-b7b1-85c6f767efe5.safetensors` 強度 0.8 |
| 画風 | なし |
| モデル | Anima（turbo なし） |
| seed | 20260909 |
| GPU | fox RTX 5090 / ComfyUI 0.34.0 |

## 工程

| 操作 | 結果 |
| --- | --- |
| `POST /api/characters/ベル/sheet?seed=20260909` | HTTP 200。job `59129db2-7e0f-4d1d-aca4-bba1def5adb2`。`elapsed_s=10.1`。832×1216 RGB PNG |
| 目視（一枚シート） | 白背景・正面全身ひとり。銀〜桃色ツインテール、金星飾り、紫目、白ファー襟クロップ、段フリルスカート、ファー付きニーハイブーツ。コラージュなし。合格 |
| `POST /api/characters/ベル/sheet/approve?job_id=59129db2-…` | HTTP 200。`approved_sheet`=`/app/.cache/characters/ndac1de01/approved_sheet.png`。合格画像とバイト一致（SHA-1 `c4319cd9…`） |
| `POST /api/bible?name=ベル&seed=20260909` | HTTP 200。job `ed77e95f-083a-4de8-9632-add6fef5a718`。24/24。所要 154.1s。`source`=`approved_sheet.png` |

## 公開閲覧（本番 `.cache`。画像本体は commit していない）

- 一枚シート: `http://192.168.1.2:8766/api/file?path=/app/.cache/generated/59129db2-7e0f-4d1d-aca4-bba1def5adb2-character-sheet.png`
- 合格コピー: `http://192.168.1.2:8766/api/file?path=/app/.cache/characters/ndac1de01/approved_sheet.png`
- 設定画合成: `http://192.168.1.2:8766/api/file?path=/app/.cache/generated/bible_ndac1de01_ed77e95f-083a-4de8-9632-add6fef5a718.png`
- 設定画 HTML: `http://192.168.1.2:8766/api/file?path=/app/.cache/generated/bible_ndac1de01_ed77e95f-083a-4de8-9632-add6fef5a718.html`

## 設定画の目視

合成シート（2040×4928）の TRAINING PICTURES 欄は、合格した一枚シートそのもの。見出しは「ベル · sprite-forge model sheet」。複数パネル生成器は既存 `generate_character_bible` のまま。

| パネル | 向き・人数 | 所見 |
| --- | --- | --- |
| `turn_front` | 正面・ひとり | 基本衣装と顔が揃う |
| `turn_34` | ほぼ正面・ひとり | 3/4 より正面寄り |
| `turn_side` | 斜め寄り・ひとり | 真横のプロファイルまでは行かない |
| `turn_back` | 背面・ひとり | 向きは指定どおり。髪はツインテールでなく短い桃色ボブに見える |
| `body_front` | 正面・ひとり | 白レオタード・裸足 |
| `body_back` | 斜め後ろ＋振り返り・ひとり | 真後ろではない。髪はボブ |
| `act_cast` | 正面寄り・ひとり | 魔法エフェクトあり。基本衣装 |
| `cos_casual` | 正面・二人並び | フーディ＋デニムショーツ。一枚に人物が二人いる |

ゲートの受入は「合格一枚を設定画の起点にする」まで。`turn_34` / `turn_side` の向きの弱さ、背面での髪型ずれ、`cos_casual` の二人並びは既存設定画経路の生成品質であり、今回の導線欠陥ではない。描き直しは一枚シートでは不要だった。

## 未実施

WebUI の実ブラウザー操作はしていない。工程は本番 REST で通した。
