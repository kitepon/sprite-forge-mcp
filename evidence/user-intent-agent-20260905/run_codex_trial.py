"""Local, owner-run interpretation experiment; never used by the application/CI.

Run with Python and pass four images in display order. Uses the existing native
ChatGPT login, not an API key. Outputs are private experiment artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["gpt-5.6-terra", "gpt-5.6-luna"], required=True)
    parser.add_argument("--case", type=int, choices=range(3), required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--instruction-revision", choices=["baseline", "v2"], default="baseline")
    parser.add_argument("images", type=Path, nargs=4)
    args = parser.parse_args()
    casebook = json.loads((ROOT / "representative-cases.json").read_text())
    case = casebook["cases"][args.case]
    output = ROOT / "private" / args.run
    output.mkdir(parents=True, exist_ok=False)
    # No evaluator expectations or previously diagnosed outfit words are sent.
    payload = {
        "instruction": casebook["instruction"],
        "case": {k: case[k] for k in ("comment", "existing_conditions")},
        "images_in_attachment_order": [
            {"display_number": i + 1, "sample_index": i}
            for i in range(4)
        ],
    }
    if args.instruction_revision == "v2":
        payload["instruction"] += "\n" + (ROOT / "instruction-v2.txt").read_text()
    prompt = (
        "This is an image interpretation experiment, not a coding task. "
        "Use only the four attached images and the input below. Do not use tools, "
        "read files, search, edit anything, or generate images. Return concise JSON. "
        "Describe visible details in Japanese and the generation description in English.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    # Pilot schema only: proposal text and explanations, not a production API.
    properties = {
        field: ({"type": "string"} if field in (
            "original_comment", "proposed_generation_description_en"
        ) else {"type": "array", "items": {"type": "string"}})
        for field in casebook["required_output_fields"]
    }
    schema = {"type": "object", "properties": properties,
              "required": list(properties), "additionalProperties": False}
    (output / "input.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    schema_path = output / "schema.json"
    schema_path.write_text(json.dumps(schema))
    images = [p.resolve(strict=True) for p in args.images]
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    command = [
        "codex", "exec", "--ignore-user-config", "--ephemeral", "--json",
        "--sandbox", "read-only", "--model", args.model,
        "--disable", "shell_tool", "--disable", "multi_agent",
        "-c", 'forced_login_method="chatgpt"',
        "-c", 'model_provider="openai"',
        "-c", 'model_reasoning_effort="medium"',
        "-c", 'web_search="disabled"',
        "-c", "project_doc_max_bytes=0",
        "--output-schema", str(schema_path),
        "--output-last-message", str(output / "result.json"),
    ]
    for path in images:
        command.extend(["--image", str(path)])
    command.append("-")
    start = time.monotonic()
    with (output / "events.jsonl").open("w") as events, (output / "stderr.log").open("w") as stderr:
        completed = subprocess.run(command, input=prompt, text=True, cwd=output,
                                   env=env, stdout=events, stderr=stderr)
    metadata = {
        "model_requested": args.model, "reasoning_effort": "medium",
        "case": case["name"], "exit_code": completed.returncode,
        "instruction_revision": args.instruction_revision,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "images": [{"display_number": i + 1, "sample_index": i,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                   for i, p in enumerate(images)],
        "command_without_image_paths": command[:-9],
        "auth": "native ChatGPT login; API key environment overrides removed",
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({k: metadata[k] for k in (
        "model_requested", "case", "exit_code", "elapsed_seconds"
    )}))
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
