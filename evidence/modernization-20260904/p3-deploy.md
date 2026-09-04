# p3-deploy — main-server 配置と Bot 1 周

Date: 2026-09-04 (JST)

## 配置

- main-server `192.168.1.2` の `/home/kite/sprite-forge-mcp` に
  commit `2fb428dbe89cf480e9360364ee9d73916568d457` を配置した。
- `compose.yaml` の単一サービスを `192.168.1.2:8766` へ公開した。
  `:8765` は既存 `ip-mcp` が継続使用しており、停止・変更していない。
- `docker compose ps` は `Up (healthy)`。WebUI `GET /`、MCP
  `/mcp/`、REST `GET /api/gpu` はすべて同じ container から応答した。
- container から fox の `py -3.13 C:\sf\train.py --help` が成功した。
  main-server の現行公開鍵が fox の Administrators 用 authorized keys から
  欠落していたため、既存鍵を保持して一行追加した。
- Bot の `.mcp.json` は `http://192.168.1.2:8766/mcp/` を指す。

実配目前提として、欠けていた Dockerfile、read-only SSH key の container 内権限正規化、
FastAPI の WebUI 配信、永続 job 一覧 API と記録画面の server-side job 表示を追加した。

## Claude Code からの MCP 実走

`claude -p --strict-mcp-config --mcp-config .mcp.json` から、次を同一の
remote MCP に順番に呼んだ。

1. `generate_sprite`
   - job `4d92f65a-62be-4e7f-9336-68f6a1ea2462`
   - `/app/.cache/generated/4d92f65a-62be-4e7f-9336-68f6a1ea2462-0.png`
2. `generate_character_bible`
   - job `6cde6362-7bfe-4204-86a2-7cbb4abeb5bd`
   - 18/18 panels:
     `/app/.cache/generated/bible_p3_azure_mage_panels/`
   - sheet: `/app/.cache/generated/bible_p3_azure_mage.png`
   - self-contained HTML: `/app/.cache/generated/bible_p3_azure_mage.html`
3. `train_character_lora(trigger="p3_azure_mage", steps=12)`
   - job `d56d6c0b-95dd-41aa-bf06-571ea10f9ba5`, progress 12/12
   - `p3_azure_mage_b993b96a.safetensors`
   - fox size 66,232,696 bytes
   - SHA-256 `8f30c886a428658e5afa78fd558f5ee338677e6028074013adb025f0588daaf5`
   - MCP `list_loras` で同名を確認した。
4. `generate_sprite(lora_name="p3_azure_mage_b993b96a.safetensors")`
   - 最終採用 job `e4433d59-f4c0-4f46-8327-2ae88ed18c84`
   - `/app/.cache/generated/e4433d59-f4c0-4f46-8327-2ae88ed18c84-0.png`
   - RGBA 1024x1024、四隅 alpha `[0,0,0,0]`
   - 目視で銀髪の女性、teal/navy のローブ、金縁、ring-shaped crystal staff を
     素体と同じ属性で維持し、casting pose へ変更できた。

最初の LoRA 指定出力 job `96732491-9d63-4f61-8f70-9e564aa8207d` は
prompt が属性を省略して茶髪へ逸脱した。属性を明示して反証し、
`9b86027c-35a5-4029-9337-e0fd0ee14677`、最終採用 `e4433d59-...` で
銀髪・配色・杖を回復した。失敗を隠さず、最終採用 path は上記に固定する。

## 記録と focused verification

- main-server の `.cache/events.ndjson` は 39 行。4 段の
  `tool_called`、18 件の `panel_completed`、学習 running/completed、
  LoRA 指定生成 completed を同じ永続 volume に記録した。
- `GET /api/jobs` は completed job 6 件を返した。
- Playwright で `http://192.168.1.2:8766/#/records` を開き、
  最終 job の「詳細」を実操作した。6 件表示、最終画像 path 表示、
  console/page error `[]`。スクリーンショット:
  `evidence/modernization-20260904/p3-records.png`
- `PYTHONPATH=. /tmp/tsumugi-p3-uv-venv/bin/python -m pytest -q`:
  `27 passed`。
- `node --check web/api.js`、`node --check web/main.js`、
  `sh -n docker-entrypoint.sh`、`git diff --check`: 全て成功。

以上により、main-server compose、Bot MCP 4 段、LoRA 成果物、永続イベント、
WebUI 記録画面まで Phase 3 の一周を実機で確認した。
