# p2-web evidence

## Delivered

- Rebuilt `web/` as a no-build vanilla ESM application with five hash-routed views:
  workbench, settings, LoRA, process, and records.
- Removed the former rpgdev/adoption-oriented modules and their obsolete endpoint
  assumptions.
- The workbench presents base, JoyAI editing, and SAM 3.1/ToonOut damage cards
  with the measurements to retain.  Base generation records its job and moves to
  the process view.
- The process view constructs an `EventSource` only for
  `/api/jobs/{job_id}/events`; it has no global event feed and therefore cannot
  display another job's `events.ndjson` records.
- Settings and LoRA record their local drafts/starts, and the record view traces
  generation, settings, and LoRA entries in browser local storage.

## Verification

Used a temporary local HTTP fixture on `127.0.0.1:8767` to serve `web/` and
minimal responses for `GET /api/gpu`, `POST /api/base`, and the job-scoped SSE
endpoint.  Connected Playwright 1.62.1 to headless Chrome through CDP
(`127.0.0.1:9227`), then verified:

1. One route loop rendered these headings in order: `作業台`, `設定画`, `LoRA`,
   `過程`, `記録`.
2. Filling the workbench prompt and submitting it navigated to `#/process` with
   `test-job` as the selected job.
3. Clicking `購読` rendered exactly one event from
   `/api/jobs/test-job/events`.
4. The Playwright `console` and `pageerror` collectors both remained empty.

Result: `{"headings":["作業台","設定画","LoRA","過程","記録"],"job":"test-job","eventCount":1,"consoleErrors":[]}`.
