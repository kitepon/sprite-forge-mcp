# b2-sprite acceptance evidence

Date: 2026-09-04

`generate_sprite` is one `Services.generate_sprite` use case exposed unchanged
through the `generate_sprite` MCP tool and `POST /api/generate`.  Each candidate
submits the b1 Anima builder to fox, reads its output, uploads it, submits the
b1 ToonOut builder, then persists the returned RGBA PNG below `.cache/generated`.
The response measures PNG dimensions, the four corner alpha values, and the
non-transparent bounding box from the emitted PNG bytes (without a hidden image
library dependency).  `list_loras` reads fox's `LoraLoader` options from
`/object_info`.

## Local MCP → fox acceptance

The app was started locally on port 8768 with the Homebrew Python runtime (the
project's uv-managed Python cannot route to the LAN host in this environment):

```sh
PYTHONPATH=. uv run --no-project --python /opt/homebrew/bin/python3.14 \
  --with fastapi --with fastmcp --with uvicorn --with httpx \
  uvicorn backend.app:app --host 127.0.0.1 --port 8768
```

A Streamable HTTP MCP session (`initialize`, `notifications/initialized`, then
`tools/call`) called `generate_sprite` with `count=4`, `seed=4201`, and a
front-facing silver-haired teal/navy mage prompt.  Fox ComfyUI completed the
four Anima Turbo → ToonOut pairs.  The MCP `structuredContent` reported:

| seed | stored RGBA PNG | ToonOut prompt id | canvas | corner alpha | bbox |
| --- | --- | --- | --- | --- | --- |
| 4201 | `.cache/generated/0e431b48-d7fe-4b50-a974-10a5c2516bbc-0.png` | `8ba2abf8-5411-4aa9-8325-26b93c25cae3` | 1024×1024 | `[0,0,0,0]` | `82,50–711,995` |
| 4202 | `.cache/generated/0e431b48-d7fe-4b50-a974-10a5c2516bbc-1.png` | `4e853a0a-429d-4e60-8841-16d15949894d` | 1024×1024 | `[0,0,0,0]` | `0,40–1024,1008` |
| 4203 | `.cache/generated/0e431b48-d7fe-4b50-a974-10a5c2516bbc-2.png` | `c7f951d3-8c82-4cd2-98cc-b5701d252930` | 1024×1024 | `[0,0,0,0]` | `7,32–986,1010` |
| 4204 | `.cache/generated/0e431b48-d7fe-4b50-a974-10a5c2516bbc-3.png` | `ad9b8a5d-743e-4657-ae78-d76e1d4d7d79` | 1024×1024 | `[0,0,0,0]` | `18,52–987,1002` |

Thus all four emitted artifacts are 1024px RGBA PNGs and at least one (in fact,
all four) has transparent corners.  In the same MCP session, `list_loras`
returned `anima_joy_sprite_lora.safetensors` and `anima_pose_preview2.safetensors`
from fox `/object_info`.

## Focused verification

```sh
PYTHONPATH=. uv run --no-project --python /opt/homebrew/bin/python3.14 \
  --with pytest --with httpx pytest -q tests/test_services.py tests/test_workflows.py
# 10 passed
```

The focused tests cover cache-scoped artifact paths, Comfy history image
selection, count validation before any network call, deterministic RGBA PNG
measurement, and the six b1 workflow shapes.
