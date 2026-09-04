# b7-web acceptance evidence

Date: 2026-09-04

The existing five-route vanilla UI was connected to the current b2–b6 REST
surface: workbench calls `POST /api/generate`; settings calls `POST /api/bible`;
LoRA calls `POST /api/lora`; process subscribes to `GET /api/events`; and records
retain each resulting job id.  The old per-job SSE URL was removed in favour of
the b6 append-only event stream.

## Playwright verification

A local fixture served `web/` and deterministic b2–b6-shaped API/SSE responses
on port 8767. Playwright 1.62.1 drove headless Chrome through every major
interaction rather than only visiting routes. Its `console` and `pageerror`
collectors remained empty. Final result:

`{"screenshots":7,"consoleErrors":[]}`

- Workbench: filled prompt, submitted generation, observed candidate 42, clicked
  transparent, observed `transparent.png`, clicked pixelize, observed
  `pixel.png`: `.cache/b7-playwright/01-workbench-candidate.png`,
  `02-workbench-transparent.png`, `03-workbench-pixel.png`.
- Character bible: filled source and costume, submitted, observed progress then
  completed PNG/HTML paths: `.cache/b7-playwright/04-settings-complete.png`.
- LoRA: filled bible name, started training, observed `12/12` completion and
  LoRA list: `.cache/b7-playwright/05-lora-complete.png`.
- Process: filled job id, subscribed, observed the persisted SSE event in the
  timeline: `.cache/b7-playwright/06-process-sse.png`.
- Records: opened the record list and clicked `詳細`, observing its timestamp,
  job and artifact detail: `.cache/b7-playwright/07-record-detail.png`.

Focused static verification:

```sh
node --check web/api.js
node --check web/main.js
curl -fsS http://127.0.0.1:8767/   # module entrypoint served
```

The fixture uses the exact REST paths and response shapes implemented by b2–b6;
the underlying GPU/MCP artifact production was already executed and recorded by
those accepted tasks. This browser acceptance isolates and verifies the UI
control-to-result behavior without repeating costly model jobs.
