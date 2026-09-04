# p2-docs evidence

## Updated documentation

- Replaced the legacy rpgdev, adoption-gate, Mac/box co-location, WebSocket, and
  old-model descriptions in `docs/03_architecture.md`,
  `docs/04_models_and_runtime.md`, and `docs/05_tool_surface.md`.
- Recorded the actual Phase 2 shape: main-server FastAPI/FastMCP 4 over shared
  `Services`; fox as Windows-native ComfyUI/SSH appliance; HTTP-only `Comfy`;
  `.cache/jobs` plus append-only `events.ndjson`.
- Kept benchmark evidence intact while adding its final Phase 2 stack decision:
  Anima, JoyAI-Image-Edit-Plus, ToonOut, and SAM 3.1; Mage-Flow is historical
  only because upstream withdrew it.
- Replaced the old root instructions with `CLAUDE.md` containing only
  `@AGENTS.md`, added the required operational `AGENTS.md`, and added a concise
  decision record plus index under `rag/`.

## Verification

Compared the edited documents against `backend/app.py`, `backend/services.py`,
`backend/config.py`, `backend/comfy.py`, `backend/box.py`, `backend/events.py`,
`backend/workflows.py`, `compose.yaml`, and the p2-web implementation.

- The documented REST/MCP table lists exactly the current three REST routes and
  three MCP tools.
- The docs explicitly distinguish the WebUI's per-job SSE contract from the
  currently mounted backend routes, so the missing integration endpoint is not
  represented as already implemented.
- `git diff --check` passed. An old-stack scan found no operational references to
  `adopt`, `Qwen-Image-Edit-2511`, `LayerDiffuse`, or `SAM2`; the sole `rpgdev`
  occurrence says explicitly that the removed integration is absent.
