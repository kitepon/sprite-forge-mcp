# b6-events acceptance evidence

Date: 2026-09-04

`EventStore` is the sole append-only `.cache/events.ndjson` writer. Every
public `Services` use case writes a `tool_called` event before its work; job
state transitions and generated artifacts write their own events on the same
job id. Each record has `event_id`, per-job `seq`, `schema_version`, UTC `at`,
`kind`, and `payload`.

FastMCP and REST now register the bound `Services` functions directly rather
than copying parameter defaults into adapter functions. `GET /api/events`
returns an SSE stream. Its optional `since=<event_id>` replays records after
that opaque id before following subsequent appends.

## Focused verification

```sh
PYTHONSAFEPATH=1 PYTHONPATH=<b6-worktree> \
  /tmp/sprite-forge-b6-venv/bin/python -m pytest -q <b6-worktree>/tests \
  --import-mode=importlib
```

Result: `26 passed`.

The focused suite covers event schema and per-job sequencing, malformed-line
tolerance, `since` replay, a sprite call's exact `tool_called` then `completed`
events, SSE replay, service status transitions, workflow and image derivation,
and LoRA progress.

## fox MCP → event log acceptance

A local FastMCP server from this worktree was served on port 8768 using the
same Homebrew Python temporary dependency route used for the b2 fox acceptance.
A Streamable HTTP session sent `initialize`, `notifications/initialized`, then
`tools/call(generate_sprite)` with:

```json
{
  "prompt": "full-body silver-haired mage with teal and navy robes, crystal staff, gold trim",
  "count": 1,
  "seed": 6200,
  "turbo": true
}
```

Fox completed Anima Turbo → ToonOut. MCP returned job
`07f39647-958b-4ce9-9702-112c105a781a` and its generated artifact was:

- `.cache/generated/07f39647-958b-4ce9-9702-112c105a781a-0.png`
- RGBA canvas `1024x1024`, corner alpha `[0,0,0,0]`, bbox
  `104,23–950,1010`, ToonOut prompt id
  `59c4f030-1885-41f7-9bd5-9c71de71c94b`

For that same job, `events.ndjson` appended exactly these two records:

| seq | event id | kind | payload |
| --- | --- | --- | --- |
| 1 | `0ed2d378-23e4-4157-9033-8618ddf570d9` | `tool_called` | `tool=generate_sprite`, `count=1`, `seed=6200`, `turbo=true` |
| 2 | `cf0d0261-d59e-4072-8c97-fa5c18d4a563` | `completed` | `count=1` |

`GET /api/events?since=1b83651a-d0c5-4035-b9ea-f8aa814863db` returned
`text/event-stream` and replayed those two event ids in order. The local
server was stopped and the fox GPU/ComfyUI queue released after this check.
