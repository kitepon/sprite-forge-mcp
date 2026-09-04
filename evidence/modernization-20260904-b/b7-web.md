# b7-web acceptance evidence

Date: 2026-09-04

The existing five-route vanilla UI was connected to the current b2–b6 REST
surface: workbench calls `POST /api/generate`; settings calls `POST /api/bible`;
LoRA calls `POST /api/lora`; process subscribes to `GET /api/events`; and records
retain each resulting job id.  The old per-job SSE URL was removed in favour of
the b6 append-only event stream.

## Browser verification

`python3 -m http.server 8767 --bind 127.0.0.1` served `web/`.  Headless Chrome
loaded each hash route at 1280×900 with no console syntax error; screenshots:

- `.cache/b7-screenshots/workbench.png`
- `.cache/b7-screenshots/settings.png`
- `.cache/b7-screenshots/lora.png`
- `.cache/b7-screenshots/process.png`
- `.cache/b7-screenshots/records.png`

Focused static verification:

```sh
node --check web/api.js
node --check web/main.js
curl -fsS http://127.0.0.1:8767/   # module entrypoint served
```

The major controls resolve to the actual b2–b6 endpoints rather than the Phase
2 placeholder-only actions.  Image-creating controls remain explicit user
actions; the browser check does not enqueue GPU work.
