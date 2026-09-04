# sprite-forge 近代化改修 追加計画 B（2026-09-04・Phase 2 不合格の是正）

オーナー裁定 2026-09-04: Phase 2（p2-core / p2-mcp）は backend 294 行・MCP ツール 3 つで閉じられ、計画正本の Phase 2・3 の受入（設定画・LoRA 学習・ダメージ版・透過・記録・WebUI 5 画面）を満たさない。統括は Phase 2 の出口を不合格と裁定し、工程を reopen せず、欠けているツールを 1 ツール 1 工程で追加する。受入は全て「fox で実際に呼んで成果物が出る」まで。p3-deploy はこの計画の全工程が閉じてから行う（メインサーバーの 8765 は ip-mcp が使用中のため別の空きポートを選ぶ）。

## 工程

### b1-workflows ComfyUI workflow builder 4 本（Anima txt2img / JoyAI edit / ToonOut / SAM 3.1）

計画正本 docs/plan_modernization-20260904.md Phase 2『構造』の backend/workflows.py。①Anima txt2img（Base/Turbo 選択、LoRA 任意、Anima-Control-Pose の骨格画像任意）②JoyAI-Image-Edit-Plus（参照画像 1〜6 枚＋指示文）③ToonOut（ComfyUI-RMBG、RGB→RGBA）④SAM 3.1（文字プロンプトまたは点で mask 出力）。各 builder は {node_id:{class_type,inputs}} を返し、node 名と入力名は fox の /object_info と一致させる。受入: tests/test_workflows.py で 4 本の JSON 形を固定し、fox の ComfyUI へ 4 本を実際に投げて出力画像／mask が得られた証跡（.cache/generated 配下のパスと /history の抜粋）を evidence に残す。旧世代（Qwen/SDXL）の builder は置かない。

依存: なし

### b2-sprite generate_sprite: Anima（+LoRA +Control-Pose）→ ToonOut で RGBA 候補を返す

MCP ツール generate_sprite(prompt, count, seed, lora_name?, lora_trigger?, pose_image?, turbo=true) と同じ services 関数を REST /api/generate から呼ぶ。b1 の builder ①→③ を連結し、候補ごとに RGBA PNG を .cache/generated に保存、計測（四隅 alpha・bbox・canvas）を数値で付けて返す（ゲートにしない）。list_loras は /object_info の LoraLoader から。受入: Claude Code から MCP を呼んで 4 枚の RGBA が出て、四隅 alpha=0 の候補があることを evidence の画像パスで示す。

依存: b1-workflows

### b3-bible generate_character_bible / bible_status: JoyAI で多方向＋表情＋衣装の設定画

MCP generate_character_bible(source, name, char_desc, attr) と bible_status(job_id)。source は候補 id か画像パス。JoyAI-Image-Edit-Plus（b1 の②）で 8 方向・表情 6・衣装 3・ちび等のパネルを生成し、パネルを .cache/generated/bible_<name>_panels/ に保存（LoRA 教材）、Pillow で 1 枚の設定画と自己完結 HTML を合成。代名詞は char_desc から組み、her 固定にしない。ジョブは uuid4、状態は .cache/jobs/<id>.json。受入: MCP から実行して設定画 PNG と panels が出た証跡（パス）。

依存: b1-workflows

### b4-lora-train train_character_lora / train_status: box.py 経由で fox の sd-scripts（Anima）を回し LoRA を配置

MCP train_character_lora(bible_name, trigger?, steps?) と train_status(job_id)。backend/box.py は `scp` で教材を fox へ送り、`ssh fox python C:\sf\train.py --config <toml>` を起動して stdout を読み進捗（step/total）を job に反映、完了後に LoRA を fox の ComfyUI/models/loras へ配置（ssh の cp ではなく train.py 側に出力先を渡す）。学習前に ComfyUI /free を叩く。PowerShell 文字列を持たない。受入: p1-lora の教材で実際に短時間学習を回し、list_loras に新 LoRA が出て generate_sprite(lora_name=…) で 1 枚出た証跡。

依存: b3-bible

### b5-variant generate_variant / make_mask / make_transparent / pixelize: ダメージ版と派生

MCP make_mask(image_id, prompt|points) は SAM 3.1（b1 の④）で mask 候補を返す。generate_variant(base_id, prompt, mask_id?) は JoyAI 編集→mask 内だけ差し替え（mask 外はベースの画素を復元）→計測（bbox 中心差）を数値で返す。make_transparent(image_id) は ToonOut、pixelize(image_id, block, posterize) は Pillow。受入: 素体 1 枚から mask→ダメージ版→透過→ドット化を MCP で通した証跡（各段の画像パスと bbox 差）。

依存: b1-workflows

### b6-events 記録一本 events.ndjson と SSE、MCP/REST の一本化

backend/events.py: services の全ツール呼び出し・ジョブ状態変化・生成完了で 1 行追記（event_id, job_id, seq, schema_version, at, kind, payload）。REST /api/events は SSE で events.ndjson を追従、/api/events?since= で過去分。MCP ツールと REST は同じ services 関数を呼び、引数・既定値を二重定義しない（既定値は services のシグネチャだけ）。受入: tests/test_events.py と、MCP から generate_sprite を 1 回呼ぶと events.ndjson に呼び出し・完了の 2 行が増える証跡。

依存: b2-sprite, b3-bible, b4-lora-train, b5-variant

### b7-web WebUI 5 画面を新 API に接続して実走確認（作業台・設定画・LoRA・過程・記録）

計画 Phase 2『WebUI 作り直し』の 5 画面が b2〜b6 の API で実際に動くことを確認し、足りない画面・導線を実装する。①作業台: 素体生成→候補カード（計測値表示）→透過・ドット化・ダメージ版 ②設定画: 生成開始→進捗→完成画像と HTML ③LoRA: 教材確認→学習開始→進捗→一覧 ④過程: /api/events の SSE を流す ⑤記録: 過去の生成・設定画・LoRA を辿る。受入: Playwright でコンソールエラー 0、5 画面それぞれの主要導線 1 周の証跡（スクリーンショットのパス）。

依存: b6-events

