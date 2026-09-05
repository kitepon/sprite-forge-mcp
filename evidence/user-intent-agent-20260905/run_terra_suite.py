"""Explicit local subscription-only experiment. One invocation per case/repeat.

No retries, alternate models, application imports or production writes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from intent_experiment import ROOT, SCHEMA, cases, payload, check_bindings


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def trial(case, repeat, batch, revision="v3"):
    output = batch / f'{case["name"]}-{repeat}'
    output.mkdir(exist_ok=False)
    request = payload(case, revision)
    images = [(ROOT / "private" / "inputs" / f"{index + 1:02d}.png").resolve(strict=True)
              for index in case["order"]]
    write_json(output / "input.json", request)
    write_json(output / "schema.json", SCHEMA)
    prompt = (
        "This is an image interpretation experiment, not a coding task. "
        "Use only the attached images and input below. Do not use tools, read files, "
        "search, edit anything or generate images. Return concise JSON conforming "
        "to the output schema. Japanese explanations and English generation text.\n"
        + json.dumps(request, ensure_ascii=False)
    )
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    command = [
        "codex", "exec", "--ignore-user-config", "--ephemeral", "--json",
        "--sandbox", "read-only", "--model", "gpt-5.6-terra",
        "--disable", "shell_tool", "--disable", "multi_agent",
        "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"',
        "-c", 'model_reasoning_effort="medium"', "-c", 'web_search="disabled"',
        "-c", "project_doc_max_bytes=0",
        "--output-schema", str(output / "schema.json"),
        "--output-last-message", str(output / "result.json"),
    ]
    for path in images:
        command.extend(["--image", str(path)])
    command.append("-")
    metadata = {
        "case": case["name"], "repeat": repeat, "revision": revision,
        "model_requested": "gpt-5.6-terra", "effort": "medium",
        "auth": "native ChatGPT login; API environment overrides removed",
        "images": [{**item, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for item, path in zip(request["images_in_attachment_order"], images)],
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest(),
        "command": command,
    }
    write_json(output / "metadata.json", metadata)
    start = time.monotonic()
    with (output / "events.jsonl").open("w") as events, (output / "stderr.log").open("w") as stderr:
        completed = subprocess.run(command, input=prompt, text=True, cwd=output,
                                   env=env, stdout=events, stderr=stderr)
    metadata.update(exit_code=completed.returncode,
                    elapsed_seconds=round(time.monotonic() - start, 2))
    errors = []
    try:
        result = json.loads((output / "result.json").read_text())
        errors.extend(check_bindings(result, request))
    except (ValueError, OSError) as error:
        errors.append(str(error))
    if completed.returncode:
        errors.append(f"CLI exited {completed.returncode}")
    metadata["mechanical_errors"] = errors
    write_json(output / "metadata.json", metadata)
    summary = {key: metadata[key] for key in
               ("case", "repeat", "elapsed_seconds", "exit_code", "mechanical_errors")}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--cases", nargs="*", help="Explicit case names; default all 12")
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--workers", type=int, choices=[1, 2], default=2)
    parser.add_argument("--revision", choices=["v3", "v4"], default="v3")
    args = parser.parse_args()
    if Path(args.batch).name != args.batch or args.batch in (".", ".."):
        parser.error("batch must be a new single directory name")
    all_cases = cases()
    if args.cases and set(args.cases) - {case["name"] for case in all_cases}:
        parser.error("unknown case")
    selected = [case for case in all_cases if not args.cases or case["name"] in args.cases]
    batch = ROOT / "private" / args.batch
    batch.mkdir(exist_ok=False)
    write_json(batch / "batch.json", {"cases": [c["name"] for c in selected],
                                    "repeats": args.repeats, "workers": args.workers, "revision": args.revision,
                                    "cli_version": subprocess.check_output(["codex", "--version"], text=True).strip()})
    summaries = []
    # Bounded waves: if a call fails (including quota), don't launch the next wave.
    # A failure is retained, not re-prompted or switched to another provider.
    jobs = [(case, repeat) for repeat in range(1, args.repeats + 1) for case in selected]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(jobs), args.workers):
            futures = [pool.submit(trial, case, repeat, batch, args.revision)
                       for case, repeat in jobs[offset:offset + args.workers]]
            wave = [future.result() for future in futures]
            summaries.extend(wave)
            write_json(batch / "summary.json", summaries)
            if any(item["exit_code"] or item["mechanical_errors"] for item in wave):
                raise SystemExit(1)


if __name__ == "__main__":
    main()
