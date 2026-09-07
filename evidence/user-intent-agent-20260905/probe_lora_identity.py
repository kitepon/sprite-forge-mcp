"""保存された一枚生成と同条件でLoRAだけを外す診断。台帳と学習は変更しない。"""
import asyncio
import json
from pathlib import Path
import uuid
import sys

from backend.services import Services
from backend.workflows import anima_txt2img


async def main():
    root = Path(__file__).parent / "private"
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    original = json.loads((root / "identity-v1/generation.json").read_text())["job"]
    graph = anima_txt2img(original["prompt"], original["seed"], turbo=False,
                         loras=[], negative=original["negative"], width=1024, height=1024)
    service = Services()
    try:
        raw, elapsed = await service._run_edit("identity-ablation-" + uuid.uuid4().hex, graph)
        (output / "without-lora.png").write_bytes(raw)
        evidence = {"source_job": original["job_id"], "workflow": graph, "elapsed_s": elapsed,
                    "changed": "LoRAのみ除去。トリガー語を含め生成文・除外・seed・寸法・モデル・samplerは維持。"}
        (output / "result.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
        print(json.dumps({"source_job": original["job_id"], "elapsed_s": elapsed, "output": str(output)}, ensure_ascii=False))
    finally:
        await service.comfy.close()


if __name__ == "__main__":
    asyncio.run(main())
