# 03 — Architecture

sprite-forge はメインサーバー上の一つの Python サービスを、人向け WebUI と
エージェント向け MCP から利用する。画像生成・編集・透過・学習は GPU 機 fox の
Windows ネイティブ ComfyUI／学習器だけで実行する。

```
browser ── WebUI (vanilla ESM) ─┐
                                ├─ FastAPI + FastMCP 4 ─ services ─ HTTP ─ fox:8188
Claude Code ── /mcp/ ───────────┘                         │
                                                         .cache/
                                              jobs/*.json + events.ndjson
```

## 配置と責務

- メインサーバーは `compose.yaml` の `sprite-forge` 一サービスを `:8765` に公開する。
  `.cache`、SSH 鍵、`.env` は volume として渡す。
- `backend/app.py` は同じ `Services` インスタンスを REST と FastMCP に投影する。
  重複したビジネスロジックは置かない。
- `backend/comfy.py` は ComfyUI の HTTP (`/system_stats`, `/prompt`, `/history`,
  `/upload/image`) だけを扱う。WebSocket、再接続、サービス側ポーリングは持たない。
- `backend/box.py` は `ssh fox py -3.13 C:\sf\train.py ...` と `scp` の実行境界である。
  Windows の PowerShell 文字列やシェルスクリプトを生成しない。
- `backend/events.py` は append-only の `.cache/events.ndjson` とジョブごとの JSON
  を所有する。イベントには `event_id`, `job_id`, `seq`, `schema_version`, `at`,
  `kind`, `payload` があり、WebUI は選択した一つのジョブだけを SSE で購読する。

## 実装済み API 面

REST は `GET /api/gpu`, `POST /api/base`, `GET /api/jobs/{job_id}`、MCP は
`gpu_status`, `generate_base`, `job_status` である。いずれも `Services` を呼び、
base ジョブは UUID を発行して queued/submitted のイベントを記録する。

WebUI はビルドなしの `web/` ESM で、作業台・設定画・LoRA・過程・記録を hash route
で表示する。旧 rpgdev 連携、採用画面、採用ゲートはこの構造に存在しない。
