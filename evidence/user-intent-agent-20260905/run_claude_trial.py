"""Compare native Claude Max login against a recorded Codex pilot input.

Owner-run experiment only; no product wiring, API key, fallback, or retry.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    source = ROOT / "private" / args.source_run
    payload = json.loads((source / "input.json").read_text())
    schema = json.loads((source / "schema.json").read_text())
    source_metadata = json.loads((source / "metadata.json").read_text())
    images = [(ROOT / "private" / "inputs" / f"{i:02d}.png").read_bytes()
              for i in range(1, 5)]
    hashes = [hashlib.sha256(data).hexdigest() for data in images]
    if hashes != [item["sha256"] for item in source_metadata["images"]]:
        raise ValueError("comparison images differ from the source run")
    output = ROOT / "private" / args.run
    output.mkdir(parents=True, exist_ok=False)
    (output / "input.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (output / "schema.json").write_text(json.dumps(schema))
    prompt = (
        "This is an image interpretation experiment, not a coding task. "
        "Use only the four attached images and the input below. Do not use tools, "
        "read files, search, edit anything, or generate images. Return concise JSON. "
        "Describe visible details in Japanese and the generation description in English.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                      "data": base64.b64encode(data).decode("ascii")}}
        for data in images
    ]
    message = {"type": "user", "message": {"role": "user", "content": content},
               "parent_tool_use_id": None}
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        env.pop(key, None)
    env["CLAUDE_CODE_DISABLE_FAST_MODE"] = "1"
    command = [
        "claude", "--print", "--safe-mode", "--strict-mcp-config",
        "--setting-sources", "", "--tools", "", "--permission-mode", "dontAsk",
        "--no-session-persistence", "--model", "sonnet", "--effort", "medium",
        "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
        "--json-schema", json.dumps(schema),
    ]
    start = time.monotonic()
    with (output / "events.jsonl").open("w") as events, (output / "stderr.log").open("w") as stderr:
        completed = subprocess.run(command, input=json.dumps(message) + "\n", text=True,
                                   cwd=output, env=env, stdout=events, stderr=stderr)
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines() if line.strip()]
    results = [event for event in events if event.get("type") == "result"]
    result = results[-1] if results else {}
    actual_models = sorted({event["message"]["model"] for event in events
                            if event.get("type") == "assistant" and event.get("message", {}).get("model")})
    structured = result.get("structured_output")
    if structured is not None:
        (output / "result.json").write_text(json.dumps(structured, ensure_ascii=False, indent=2))
    metadata = {
        "model_requested": "sonnet", "models_observed": actual_models,
        "reasoning_effort": "medium", "source_run": args.source_run,
        "case": source_metadata["case"],
        "instruction_revision": source_metadata.get("instruction_revision", "baseline"),
        "exit_code": completed.returncode, "result_subtype": result.get("subtype"),
        "is_error": result.get("is_error"), "has_structured_output": structured is not None,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "images": source_metadata["images"],
        "auth": "native claude.ai Max login; API/provider overrides removed",
        "command": command,
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({key: metadata[key] for key in (
        "models_observed", "case", "elapsed_seconds", "exit_code",
        "result_subtype", "is_error", "has_structured_output"
    )}))
    raise SystemExit(completed.returncode or (0 if structured is not None and not result.get("is_error") else 1))


if __name__ == "__main__":
    main()
