# p2-mcp — FastMCP 4 と REST の薄層

## 実施内容

FastMCP 4.0.x の streamable HTTP app を `/mcp` に mount し、`combine_lifespans` で
親 FastAPI app と MCP session manager の lifespan を結合した。MCP の `gpu_status`、
`generate_base`、`job_status` と REST の `/api/gpu`、`/api/base`、`/api/jobs/{job_id}` は、
同一の `backend.services.Services` instance を呼ぶだけの薄層である。

`compose.yaml` は port 8765 の単一サービス、`.cache` volume、SSH directory と `.env` の
read-only mount を定義した。依存は `pyproject.toml` / `uv.lock` で FastMCP 4、FastAPI、
uvicorn、httpx に固定した。

## 最終試験と結果

1. `python3 -m compileall -q backend` が成功した。
2. FastMCP 4.0.2 / FastAPI を一時実行環境へ解決し、`uvicorn backend.app:app` を
   localhost:8766 で実際に起動した。REST `GET /api/jobs/does-not-exist` は
   `{"job_id":"does-not-exist","status":"unknown"}` を返した。
3. 同じ ASGI server の `/mcp/` へ Streamable HTTP の initialize → initialized →
   `tools/call(job_status, job_id=does-not-exist)` を送った。MCP は同じ
   `{"job_id":"does-not-exist","status":"unknown"}` を structured content として返した。
   両方とも `Services.status` の unknown-job 分岐を通るため、REST/MCP の共通 services 呼出しを
   実リクエストで確認した。検証後は tmux session と localhost:8766 を停止した。
4. `git diff --check` が成功した。
