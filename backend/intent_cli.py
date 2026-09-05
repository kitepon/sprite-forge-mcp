"""正式な契約ログインを持つホストで、一回の画像解釈を実行する。"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .intent import Proposal
from .sheet_layout import LayoutProposal

MODEL = "gpt-5.6-terra"


def command(root: Path, images: list[Path]) -> list[str]:
    args = ["codex", "exec", "--ignore-user-config", "--ephemeral", "--json",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", MODEL,
            "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"',
            "-c", 'model_reasoning_effort="medium"', "-c", 'web_search="disabled"',
            "-c", "project_doc_max_bytes=0"]
    for feature in ("shell_tool", "unified_exec", "multi_agent", "apps", "remote_plugin", "image_generation", "view_image", "hooks"):
        args += ["--disable", feature]
    args += ["--output-schema", str(root / "schema.json"), "--output-last-message", str(root / "result.json")]
    for image in images:
        args += ["--image", str(image)]
    return args + ["-"]


def check_events(stdout: str) -> None:
    """CLI境界で完了と、画像読解以外のツール実行がないことを確認する。"""
    completed = False
    for line in stdout.splitlines():
        event = json.loads(line)
        if event["type"] in ("turn.failed", "error"):
            raise RuntimeError(f"解釈に失敗しました: {event.get('error', event.get('message', event['type']))}")
        item = event.get("item")
        if item and item["type"] not in ("agent_message", "reasoning"):
            raise RuntimeError(f"画像解釈以外の操作が返りました: {item['type']}")
        completed |= event["type"] == "turn.completed"
    if not completed:
        raise RuntimeError("解釈の完了応答を受け取れませんでした。")


def run(packet: dict) -> dict:
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="sprite-intent-") as directory:
        root = Path(directory)
        images = []
        for index, encoded in enumerate(packet["images"]):
            path = root / f"{index + 1}.png"
            path.write_bytes(base64.b64decode(encoded, validate=True))
            images.append(path)
        is_layout = packet["input"].get("stage") == "layout"
        model = LayoutProposal if is_layout else Proposal
        schema = model.model_json_schema()
        # 保存済みの旧応答の省略は読めるが、新しいCLI出力では全項目を返す。
        def require_properties(value):
            if isinstance(value, dict):
                value.pop("default", None)
                if "properties" in value:
                    value["required"] = list(value["properties"])
                for nested in value.values():
                    require_properties(nested)
            elif isinstance(value, list):
                for nested in value:
                    require_properties(nested)
        require_properties(schema)
        (root / "schema.json").write_text(json.dumps(schema))
        instruction = Path(__file__).with_name("layout_instructions.txt" if is_layout else "intent_instructions.txt").read_text()
        prompt = instruction + "\n入力:\n" + json.dumps(packet["input"], ensure_ascii=False)
        started = time.monotonic()
        result = subprocess.run(command(root, images), input=prompt, text=True,
                                capture_output=True, cwd=root, env=env)
        if result.returncode:
            if result.stdout.strip():
                check_events(result.stdout)
            raise RuntimeError(f"Codexで解釈できませんでした（終了値{result.returncode}）: {result.stderr.strip()}")
        check_events(result.stdout)
        proposal = model.model_validate_json((root / "result.json").read_text())
        return {"proposal": proposal.model_dump(), "model": MODEL,
                "elapsed_seconds": round(time.monotonic() - started, 2), "auth": "chatgpt"}


def main():
    try:
        result = run(json.load(sys.stdin))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
