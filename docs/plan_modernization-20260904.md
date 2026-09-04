# sprite-forge-mcp 近代化改修 計画（campaign 正本・2026-09-04）

## Context

- sprite-forge は「GPU 機（fox, RTX 5090）の ComfyUI に描かせ、LoRA を学習し、設定画を作る」道具。MCP（Bot/AI 用）と WebUI（人用）の二つの顔を持つ。
- **GPU 機は 2026-08-30 に Windows 11 を再インストール済みで、ComfyUI・モデル・学習器が全部消えている**（実測）。土台の再構築が前提。
- オーナー裁定（会話で確定）:
  - **価値観: 最新技術を最優先。比較は「新しい物同士」だけで行い、半年前の技術を対照にした実測はしない。安定性優先は旧世代のゴミを生む。** AI の内蔵知識は化石なので、判断は今週の一次ソースから。
  - **ComfyUI は残す。LoRA 学習は前提。**
  - **安全装置・セキュリティ機能は全部排除。** 欠陥は直す。
  - **軸はメインサーバー**（Linux, 192.168.1.2）。バックエンド・記録・WebUI・MCP をそこに置く。GPU 機は Windows ネイティブで ComfyUI と学習器を載せた装置。HTTP と `ssh fox python ...` でしか触らない。**Windows のシェルでコードを書かない。WSL2 は使わない**（Blackwell の WSL2 は CUDA が約 16GiB 見えなくなる未解決 issue microsoft/WSL#40401）。
  - **rpgdev 連携と「採用」は廃止。WebUI は作り直す**（①手で作る作業台 ②AI の過程を見る窓 ③記録）。
- 外部反証（Grok 4.6・ChatGPT gpt-5.6-thinking）は「推論・学習とも Windows ネイティブ」「透過は ToonOut」で一致。ここから先は「最新一択」の価値観で選び直した。

## 採用スタック（2026-09-04 時点の最新。一次ソース確認済み）

| 段 | 採用 | 根拠（日付） | 落とす旧世代 |
|---|---|---|---|
| 素体生成 | **Anima**（Circlestone × Comfy Org、2B、アニメ専用、ComfyUI ネイティブ）。学習用 Base v1.0（2026-05-15）、量産用 Turbo v1.1（2026-08-24） | HF circlestone-labs/Anima、docs.comfy.org/tutorials/image/anima | Illustrious-XL、画風 LoRA v2 |
| LoRA 学習 | **kohya sd-scripts `anima_train_network.py`**（2026-02 本線合流、bf16 必須、Windows 動作報告あり） | HF Anima discussions/35、sd-scripts PR #2260 | SDXL 用 sd-scripts 設定、musubi-tuner |
| ポーズ指定 | **Anima-Control-Pose preview-2**（2026-06-26、専用 node「Anima Pose Control」） | comfyui-wiki news 2026-06-26 | ControlNet-Union-SDXL |
| 編集・設定画・多方向 | **Mage-Flow-Edit**（Microsoft、2026-07-22、4B、MIT、参照画像複数、int8 版あり、ComfyUI v0.29 でネイティブ） | HF microsoft/Mage-Flow、Comfy-Org/Mage-Flow、ComfyUI changelog v0.29.0 | Qwen-Image-Edit-2511、Lightning LoRA、Multiple-Angles LoRA、Qwen-Image-Layered |
| 透過 | **ToonOut**（BiRefNet アニメ特化、MIT、HF joelseytre/toonout）を **ComfyUI-RMBG** node（`BiRefNet_toonOut`）で GPU 実行 | github MatteoKartoon/BiRefNet、ComfyUI-RMBG v2.9.2 | rembg（birefnet-general）、chroma-key、Layered |
| マスク指定 | **SAM 3.1**（ComfyUI ネイティブ node、点/枠/文字で指定） | docs.comfy.org SAM 3.1、PR #13408 | Mac の `.venv-sam2` |
| ドット化 | Pillow の縮小＋減色（決定論的処理。変えない） | — | — |
| ComfyUI | **Portable 最新**（Python 3.13 + CUDA 13.0 同梱、v0.34.x）、NSSM headless | docs.comfy.org installation | 0.25 |
| MCP | **FastMCP 4.0.x**（2026-09-02） | gofastmcp.com | 3.4 |
| Python/依存 | Python 3.13、`pyproject.toml` + `uv.lock` | — | requirements.txt |

- Anima の**モデルライセンスは非商用**（生成物は商用可）。商用利用が要る時は Circlestone（tdrussell@circlestone.ai）へ商用ライセンスを依頼する。オーナー判断。
- Mage-Flow-Edit に多角度専用 LoRA は無いので、多方向は指示文と参照画像で出す。出なければその時点で最新の代替を探す（旧世代へ戻さない）。

## 到達形

```
Bot / Claude Code ──MCP──▶ メインサーバー: sprite-forge (compose)  ──HTTP──▶ fox: ComfyUI Portable (NSSM :8188)
オーナーのブラウザ ──WebUI─▶   ├ services（工程の本体・記録1本）              Anima / Mage-Flow-Edit / ToonOut / SAM3.1
                              ├ .cache/（候補・設定画・LoRA 教材・events.ndjson） ──ssh python─▶ fox: train.py（sd-scripts Anima）
                              └ MCP + REST（同じ services を呼ぶだけ）
```

GPU 側の画像処理は全部 ComfyUI のワークフローに収める。メインサーバー側に画像 ML ライブラリは置かない（Pillow/numpy だけ）。

## Phase 0 — 土台再構築（GPU 機 fox、一回きり）

- ComfyUI Portable を `C:\Users\kite_\ComfyUI` へ。NSSM サービス `ComfyUI`（`--listen 0.0.0.0 --port 8188`、LocalSystem）。ファイアウォール 8188。メインサーバーの ssh 鍵を fox へ。第三者コードの導入を harness が止めたらオーナーが手で叩く。
- custom node: ComfyUI-RMBG（ToonOut）。他はネイティブ。
- モデル（Phase 1 の候補を全部。負けた物は Phase 2 で消す）: Anima Base v1.0 / Turbo v1.1 + `qwen_3_06b_base`（TE）+ `qwen_image_vae`／Anima-Control-Pose preview-2／Mage-Flow と Mage-Flow-Edit（bf16 と int8_convrot）+ `qwen3vl_4b_bf16` + `mage_flow_vae_bf16`／JoyAI-Image-Edit-Plus（int8）+ `qwen3vl_8b_joyimage_edit` + `wan_2.1_vae`／Krea 2／ToonOut／SAM 3.1。
- Anima のライセンス: モデルは非商用、生成物は商用可。LoRA は配布しない前提（オーナー裁定 2026-09-04）なので問題なし。配布・販売したくなった時だけ Circlestone へ商用ライセンスを依頼する。
- 学習器: Windows ネイティブ venv（torch cu130）に sd-scripts（Anima 対応版）。入口 `C:\sf\train.py`（Python。toml を受けて accelerate を起動、進捗を stdout）。学習前の GPU 解放は ComfyUI `/free`（HTTP）。
- 出口: メインサーバーから `/system_stats`、`/object_info` に Anima・MageFlow・RMBG・SAM3 の node、`ssh fox python C:\sf\train.py --help`。

## Phase 1 — 新顔同士の比較（旧世代は対照に置かない）

候補は全部 2026年5月以降のもの。同じ入力で並べ、用途（JRPG スプライト・同一人物・透過の縁）で勝った物を Phase 2 に採る。結果は `docs/09_modernization_bench.md` へ。

| 段 | 第一候補 | 比較相手（いずれも新顔） | 判定 |
|---|---|---|---|
| 素体生成 | Anima Base/Turbo v1.1（5月／8月） | Mage-Flow 本体 txt2img（7月、MIT）／Krea 2（6月、musubi 対応） | JRPG 画風の追従、輪郭、秒数。**LoRA 学習器がある物を優先**（Anima=sd-scripts、Krea 2=musubi、Mage-Flow=未確認） |
| 編集・設定画 | Mage-Flow-Edit（7月、4B） | JoyAI-Image-Edit-Plus（JD、5〜6月、8B+16B、int8 版、参照 1〜6 枚、Apache-2.0） | 8方向＋表情で同一人物か、後ろ姿、1枚の秒数と VRAM |
| ポーズ | Anima-Control-Pose preview-2（6月） | Mage-Flow-Edit に骨格画像を参照として渡す | ポーズ追従と同一性 |
| 透過 | ToonOut（6月更新） | SAM 3.1 の文字/点プロンプトでのマスク抽出（BRIA の最新 V-RMBG 3.0 は動画専用・重み非公開なので外す） | 毛先・指・半透明、四隅 alpha=0 |
| LoRA 学習 | sd-scripts Anima 対応（2月本線） | 新顔が一つなので比較なし。step 数と解像度だけ当たりを取る | 学習後の同一性、時間 |
| ダメージ版 | SAM 3.1 マスク + 勝った編集モデル + マスク外復元 | — | bbox 差の数値 |

- 素体で Anima 以外が勝った場合は、その学習器（musubi 等）に Phase 0 の学習器を差し替える。
- **2026-09-04 裁定（Phase 1 の途中）**: 素体・編集とも Mage-Flow が比較で勝ったが、Microsoft が Mage-Flow 系を Hugging Face から取り下げた（ログイン済みでも 404、コレクションは Mage-ViT だけ）ため **Mage-Flow を捨てる**。素体は **Anima**（Base v1.0 で学習、Turbo v1.1 で量産、学習器は sd-scripts の anima_train_network.py）、編集・設定画は比較 2 位の **JoyAI-Image-Edit-Plus** に繰り上げ。理由: 公式が消した重みは更新が来ず、ミラー頼みは長寿命の道具の土台にならない。Windows ネイティブでの学習器の壁（SimpleTuner は fcntl で非対応、ai-toolkit は Python 3.12 venv なら導入できたが元重みが取得不能）もここで記録する。fox に入れた SimpleTuner・ai-toolkit・venv-aitoolkit・Mage-Flow 重みは Phase 2 の整理で撤去。
- Anima のモデルライセンス（非商用）が問題になるなら、その時点で Mage-Flow か Krea 2 に寄せる。

## Phase 2 — コード再構築

### 撤去
- rpgdev 一式（`adopt`、`RPGDEV_*`、`ADOPTION_LOG`、`list_sprites`、`pair_with`、採用画面）。
- 採用ゲート・`force`、chroma 一致度ゲート、`black_leak_count`、`chroma_halo_count`、`_auto_bg`、`SAFE_CHROMA` 系、`STYLE_PHRASE`。計測（四隅 alpha・bbox 中心差・canvas 一致）は数値として結果に付けるだけ。
- 例外の変換（`app.py` の try/except→404/502、`bible._job` の例外制御フロー、`_font` の握りつぶし）。失敗は raise。
- `comfy_client.py` の WebSocket・再接続・SSE・`/history` 40回ポーリング。
- `training.py` の PowerShell 生成・`cmd /c dir`・`SF_DONE`・`TRAIN_TIMEOUT`・サービス再起動分岐。
- Qwen 系 workflow、`sdxl_*` workflow、LayerDiffuse 関連、rembg、`.venv-sam2`、`sam2_bridge.py`、chroma-key。

### 欠陥修正
- ジョブID `hash()` → `uuid4`。状態は `.cache/jobs/<id>.json`。
- 重い同期処理は残らない（画像 ML は全部 ComfyUI 側）。Pillow の処理だけ `asyncio.to_thread`。
- 設定画プロンプトの `her` 固定 → `char_desc` から代名詞込みで組む。
- `config.STYLE_LORA` の実行時書き換え廃止。
- `list_loras` は `/object_info`。MCP/REST の二重定義を `services` に一本化。

### 構造
- `backend/workflows.py`: Anima txt2img（+LoRA +Control-Pose）／Mage-Flow-Edit（参照 N 枚）／ToonOut 透過／SAM 3.1 マスク の4 builder。
- `backend/comfy.py`: HTTP だけ（`/prompt` `/history` `/upload/image` `/view` `/free` `/object_info`）。
- `backend/box.py`: `ssh fox python C:\sf\train.py ...` と `scp` だけ。PowerShell 文字列は持たない。
- `backend/events.py`: **記録一本** `.cache/events.ndjson`。各行 `event_id`・`job_id`・`seq`・`schema_version`・`at`・`kind`・`payload`。`services` が MCP/WebUI どちらから呼ばれても同じ関数で追記。
- MCP: FastMCP 4.0.x（`combine_lifespans`、`fastmcp.apps`）。長時間ジョブは Claude Code が task mode 未対応（#18617 not planned）なので start/status 形。task 化（`fastmcp[tasks]`＋`TasksExtension`）は対応後の別作業として docs に残す。
- 依存: `pyproject.toml` + `uv.lock`（fastmcp≥4、fastapi、httpx、pillow、numpy）。Python 3.13。
- 配置: メインサーバーに `compose.yaml`（1サービス、port 8765、`.cache` volume、ssh 鍵と `.env` は volume）。`git pull && docker compose up -d --build`。

### WebUI 作り直し（web/）
- vanilla ESM・ビルドなし。`api.js`/`state.js`/`ui.js` の骨は流用。
- 画面: ①作業台（素体・編集・ダメージ版。候補カードに計測値）②設定画（多方向＋表情/衣装、ジョブ進捗）③LoRA（教材確認・学習開始・進捗・一覧）④過程（events.ndjson を SSE で流す）⑤記録（過去の生成・設定画・LoRA を辿る）。
- Playwright でコンソールエラー 0 と主要導線 1 周。

### 試験・文書
- `tests/`（pytest、GPU なし）: `audit` 純関数、workflow builder の JSON 形、`box.py` のコマンド文字列、`events` の追記と読み出し。CI は `pytest`。
- `docs/03,04,05` を新スタックに書き換え、`docs/09` に疎通結果。`CLAUDE.md` は `@AGENTS.md` 一行。`HANDOFF.md` 破棄。AGENTS.md に「軸はメインサーバー」「最新一択の価値観」「GPU 機再インストール」を記す。調査結果は `rag/` へ還流。

## Phase 3 — 届ける
- メインサーバーで compose 起動 → Bot 側の `.mcp.json` を `http://192.168.1.2:8765/mcp/` へ → Claude Code から `generate_sprite → generate_character_bible → train_character_lora → generate_sprite(lora)` を1周。
- commit は対象 path 明示。push は sprite-forge repo の正典に push 既定の記載がないため、実行前にオーナーへ一言。

## レーン
①外部完了待ち（モデル DL・GPU 機での第三者コード導入のオーナー操作）と ②多段の受入（土台→疎通→実装→配置）が着手時点で確定しているので**統括レーン**。承認後、`orchestrate` 正典に従い campaign 計画正本を `sprite-forge-mcp/docs/` に置いてから着手する。

## Verification
- Phase 0: `/system_stats`・`/object_info`（Anima・MageFlow・RMBG・SAM3 の node）・`ssh fox python train.py --help`。
- Phase 1: 各段の新顔同士の比較画像と判定が `docs/09` にあり、勝者が一つずつ決まっている。
- Phase 2: `pytest` green、`list_tools` に残すツール、WebUI 5画面が Playwright でエラー 0。
- Phase 3: LoRA 込みの1周が Bot から通り、`.cache/events.ndjson` に全工程が記録され、WebUI の記録画面で辿れる。

## 事後裁定 2026-09-04（設定画の品質）

- オーナーが Bell の設定画（18 枚が全部同じ絵）を「絶望的」と却下。原因は二つ: ①b3 が 6月に検証済みのマスターシート錨の設計（`bible.py` 旧版）を捨てて「素体 1 枚＋短い指示 × 18」に縮め、受入を「出た」で通した ②`workflows.joy_edit` が JoyAI の参照画像を autogrow の入れ子辞書で渡していて黙って捨てられ、参照なしで描いていた（同一性は VAEEncode の潜在漏れ）。
- 是正: 旧設計を JoyAI 版で復元（マスターシート → 種別ごとの指示・否定語で 23 パネル → 節構成の PNG と HTML）、autogrow は `images.image0` … の平坦キーで渡す。FORMAL・ちび・装備は JoyAI で通る文面へ（装備は正面 1 体を参照）。Bell で実走し、方向・体型・表情・アクション・衣装 3 種・ちび・装備が全部違う絵になったことを bell が目視で受入。
- Qwen-Image-Edit-2511 へ戻す判断は保留（JoyAI で 6月水準に戻ったため不要）。
