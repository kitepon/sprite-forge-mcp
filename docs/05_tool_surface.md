# 05 — Tool Surface

REST と MCP は同じ `backend.services.Services` を通る。出力・状態の記録もサービス層の
`.cache/events.ndjson` に一本化し、フェイスごとの別実装を置かない。

| Use case | REST | MCP | Result |
| --- | --- | --- | --- |
| GPU 状態 | `GET /api/gpu` | `gpu_status` | ComfyUI の `/system_stats` 応答 |
| 素体生成開始 | `POST /api/base?prompt=&seed=` | `generate_base(prompt, seed)` | UUID、`queued`/`submitted` 状態 |
| ジョブ照会 | `GET /api/jobs/{job_id}` | `job_status(job_id)` | 保存状態、未登録なら `unknown` |

`Services.start_base` は Anima workflow を ComfyUI に送信し、ジョブを JSON とイベントログへ
保存する。`start_edit`、`start_matte`、`start_damage` は同じサービス層にあり、JoyAI、
ToonOut、SAM 3.1 の workflow builder を使う。

WebUI の過程画面は `/api/jobs/{job_id}/events` を EventSource として接続する契約である。
現時点の `backend/app.py` が mount している REST は表の三本であり、このイベント endpoint
は WebUI 統合時に追加する境界である。グローバルな進捗フィードは持たず、利用者が選んだ
job ID 以外の events.ndjson レコードを表示しない。

FastMCP は `combine_lifespans` で FastAPI に同居し、HTTP transport は `/mcp/` に
mount される。長時間処理は start/status 形を保ち、MCP task extension は対応後の別作業とする。
