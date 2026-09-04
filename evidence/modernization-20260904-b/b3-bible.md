# b3-bible acceptance evidence

`Services.generate_character_bible` is the single implementation exposed by
the `generate_character_bible` MCP tool and `POST /api/bible`.  It accepts an
existing candidate ID or an image path, produces the required eight turnaround,
six expression, three costume, and chibi panels through JoyAI, records the UUID
job under `.cache/jobs/`, and uses Pillow to make an RGBA model sheet and an
offline, self-contained HTML gallery.  Pronouns are inferred from `char_desc`;
there is no fixed `her` prompt.

## Focused tests

```sh
PYTHONPATH=. uv run --no-project --python /opt/homebrew/bin/python3.14 \
  --with pillow --with pytest --with httpx \
  pytest -q tests/test_bible.py tests/test_services.py tests/test_workflows.py tests/test_events.py
```

Result: `14 passed`.

## fox MCP acceptance

A local FastMCP 4 server was run on port 8768.  A Streamable HTTP MCP session
sent `initialize`, `notifications/initialized`, and then
`tools/call(generate_character_bible)`.  The source was the b2 generated RGBA
candidate `0e431b48-d7fe-4b50-a974-10a5c2516bbc-0.png` and the call used
`name=Azure Mage`, `char_desc=they/them silver-haired mage in teal and navy
robes`, and `seed=5300`.

Fox ComfyUI completed all 18 JoyAI prompt IDs.  The resulting MCP job ID was
`4e270bf2-f38f-420b-9445-ee582db40b64`; an MCP `bible_status` call returned
`status=completed` and `completed_panels=18`.

- Panels: `.cache/generated/bible_Azure_Mage_panels/` (18 PNG files)
- Model sheet: `.cache/generated/bible_Azure_Mage.png` — `RGBA`, `1024x1430`
- Self-contained gallery: `.cache/generated/bible_Azure_Mage.html`

The append-only job events include 18 `panel_completed` records and the final
`completed` record.  The local MCP server and fox GPU queue were stopped and
released after verification.
