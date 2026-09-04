# 00 — Overview

sprite-forge-mcp is a local-GPU sprite production studio with one Python backend and two faces: a human WebUI over FastAPI and an agent surface over FastMCP.

Generation work runs in ComfyUI on a GPU machine. The backend orchestrates ComfyUI over HTTP/WebSocket, applies deterministic Pillow-based gates, serves the vanilla ESM WebUI, and exposes the same service layer to MCP tools.

## Canonical Map

| File | Role |
|---|---|
| [01_context_and_pain.md](01_context_and_pain.md) | Pain points and production rules the tool must enforce |
| [02_research_sota.md](02_research_sota.md) | Research record behind the model/runtime choices |
| [03_architecture.md](03_architecture.md) | Backend, ComfyUI, WebUI, and MCP architecture |
| [04_models_and_runtime.md](04_models_and_runtime.md) | Model/runtime facts and VRAM assumptions |
| [05_tool_surface.md](05_tool_surface.md) | Shared service, HTTP, and MCP tool surface |
| [06_output_contract.md](06_output_contract.md) | Output and adoption gate contract |
| [07_webui_ux.md](07_webui_ux.md) | WebUI flow and UX constraints |
| [08_open_questions_validate_on_box.md](08_open_questions_validate_on_box.md) | Validation history and remaining open questions |
| [adr/](adr/) | Architecture decision records |

## Supporting Docs

| File | Role |
|---|---|
| [../INSTALL.md](../INSTALL.md) | Setup and runtime limits |
| [models.md](models.md) | Model placement and required ComfyUI nodes |
| [../AGENTS.md](../AGENTS.md) | Canonical project instructions, current policy, and commands; CLAUDE.md only imports it |

`models.md` is intentionally kept outside the numbered canon because it is an operational setup reference rather than a design decision document.
