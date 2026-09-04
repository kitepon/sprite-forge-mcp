# sprite-forge

## Operating model

- The main server owns backend code, WebUI, records, and deployment.  fox is a
  Windows-native GPU appliance reached only through ComfyUI HTTP and SSH.
- Prefer current technology. Compare only contemporary candidates; do not retain
  an older stack merely because it was once stable.
- fox was reinstalled on 2026-08-30. Treat ComfyUI, models, custom nodes, and the
  training environment as rebuilt assets, not inherited state.

## Current stack

Anima Base/Turbo, Anima-Control-Pose, JoyAI-Image-Edit-Plus, ToonOut, SAM 3.1,
FastMCP 4, FastAPI, Python 3.13, and `uv.lock` are the current stack. Mage-Flow
is withdrawn upstream and must not be reintroduced. LoRA training uses
sd-scripts `anima_train_network.py` with bf16.

## Boundaries

Keep GPU image ML in ComfyUI. The main server uses ordinary HTTP, SSH/SCP, and
Pillow/numpy only. Record job state in `.cache/jobs/` and all observable events
in `.cache/events.ndjson`; REST, MCP, and WebUI must use the shared services
layer rather than duplicate workflow logic.
