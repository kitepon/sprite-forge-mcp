# b1-workflows evidence

`backend/workflows.py` now builds the four accepted paths using node names,
inputs, and model names read from fox `GET /object_info` on 2026-09-04.

## Tests

`PYTHONPATH=<worktree> uv run --no-project --with pytest pytest -q tests/test_workflows.py`

Result: `6 passed`.

## fox ComfyUI execution

All requests were submitted to `http://192.168.1.11:8188/prompt` and their
`/history/{prompt_id}` status was `success`.

| Builder | Prompt ID | Output under fox ComfyUI output |
| --- | --- | --- |
| Anima Turbo txt2img | `928f6a99-1b3e-46b5-9410-c7f940a98088` | `sprite-forge/anima_00001_.png` |
| JoyAI Image Edit Plus | `3ddd3bc8-e75e-4293-bc5c-bf9b9ecc9bf9` | `sprite-forge/joy-edit_00001_.png` |
| ToonOut RGBA | `d1489fec-8d0d-41a0-82ad-3e042e5b3f29` | `sprite-forge/toonout_00001_.png` |
| SAM 3.1 mask | `e488cd5c-7df6-4129-9a78-0029df37aa24` | `sprite-forge/sam3-mask_00001_.png` |

The initial ToonOut request `21d920fa-1ac3-4d26-ac94-61de26cab2e3` exposed an
implementation mismatch: its node advertised `invert_output` as optional but
raised when the key was omitted. The final builder explicitly supplies
`invert_output=false`, `refine_foreground=false`, and `background_color`, and
the retry above succeeded.

The final history excerpts each contain `execution_success` and a `SaveImage`
output. The fox paths are the generated-artifact source for later services;
those services copy selected outputs into `.cache/generated`.
