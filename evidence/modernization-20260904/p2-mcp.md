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
2. FastMCP 4.0.2 / FastAPI を一時実行環境へ解決し、`backend.app` の import、app title
   `sprite-forge`、MCP HTTP route 1本を確認した。
3. REST と MCP の各入口が独自の GPU client や job store を作らず、module-level の
   `services` を共有することをソース上で確認した。
4. `git diff --check` が成功した。
