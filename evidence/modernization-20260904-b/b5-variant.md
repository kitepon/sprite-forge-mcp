# b5-variant acceptance evidence

Date: 2026-09-04

`make_mask`, `generate_variant`, `make_transparent`, and `pixelize` are shared
`Services` use cases exposed by MCP and matching REST endpoints.  Comfy output
is normalized to RGBA PNG before its canvas, alpha corners, and bounding box are
measured.  `generate_variant` composites the JoyAI output with the original
base outside the supplied SAM mask; it also reports the bounding-box centre
delta.  Pixelization uses Pillow nearest-neighbour resampling and optional
posterization while preserving alpha.

## Local MCP → fox acceptance

The local ASGI app ran on port 8768 and was called through a Streamable HTTP MCP
session.  The source was the accepted b4 Azure Mage LoRA output:

`.lattice/runs/modernization-20260904-b-tsumugi-20260904t0335/worktrees/scripted-wt-b4057a925ff7af095d4e5d4a/tree/.cache/generated/7560bc87-b72d-441c-9b7d-8180b9fedf41-0.png`.

| MCP tool | output path | fox prompt id | result |
| --- | --- | --- | --- |
| `make_mask` | `.cache/generated/6bb253bf-bfb8-4ba6-9fe4-d8bf4f0461ec-mask.png` | `3c7aafcc-a1c2-44c1-8354-7d5039ccb15e` | SAM 3.1 mask, 1024×1024 |
| `generate_variant` | `.cache/generated/3ed08b43-1221-46a5-81eb-89b5e934c26b-variant.png` | `5bd6b74e-4be2-44ec-a39f-d0a5c0b627dc` | JoyAI damage edit; bbox centre delta `{x:0.0,y:0.5}` |
| `make_transparent` | `.cache/generated/e80a85da-6f7a-482f-a7ad-7326e381e741-transparent.png` | `6078c762-3a38-454e-ab9f-2f0e64813f0a` | ToonOut RGBA, corner alpha `[0,0,0,0]` |
| `pixelize` | `.cache/generated/b910baea-b930-4b30-9882-46118b6908f7-pixel.png` | local Pillow | block 8, posterize 4, RGBA corners `[0,0,0,0]` |

The full MCP chain was source → SAM mask → JoyAI masked damage variant → ToonOut
transparent PNG → Pillow pixel PNG.  All artifacts are 1024×1024; the last
three have transparent corners, and each output path is emitted by MCP.

## Focused verification

```sh
PYTHONPATH=. uv run --no-project --python /opt/homebrew/bin/python3.14 \
  --with pytest --with httpx --with pillow \
  pytest -q tests/test_variant.py tests/test_services.py tests/test_workflows.py
# 14 passed
```

The focused tests exercise mask-limited compositing, pixelization dimensions and
alpha preservation, RGB-to-RGBA normalization, bbox-centre measurement, cached
paths, history selection, validation, and b1 workflow contracts.
