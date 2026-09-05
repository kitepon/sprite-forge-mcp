"""保存済み実グラフの肯定文だけを変更し、生成側の応答を切り分ける実験。"""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path


def replace_positive(graph, old, new):
    """対象句が一つだけある保存済みグラフを扱う。元の記録は変更しない。"""
    text = graph["20"]["inputs"]["text"]
    if not old or text.count(old) != 1:
        raise ValueError("置換対象は肯定文に一箇所だけ必要です。")
    result = deepcopy(graph)
    result["20"]["inputs"]["text"] = text.replace(old, new, 1)
    return result


async def main(args):
    cases = json.loads(args.cases.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(args.output.resolve())
    from backend.services import Services

    service = Services()
    results = []

    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        queue = await service.comfy.queue()
        if queue["queue_running"] or queue["queue_pending"]:
            raise RuntimeError("GPUは使用中です。実験を開始していません。")
        save(args.output / "gpu.json", await service.comfy.stats())
        for case in cases:
            source = args.root / case["source"]
            previous = json.loads((source / "changed.json").read_text())
            graphs = sorted(source.glob(f"workflow-{previous['job_id']}-*.json"))
            if len(graphs) != len(previous["pictures"]):
                raise ValueError("比較元の画像と実グラフの件数が異なります。")
            for graph_path in graphs:
                graph = json.loads(graph_path.read_text())
                changed = replace_positive(graph, case["old"], case["new"])
                seed = graph["23"]["inputs"]["seed"]
                name = f"{case['key']}-{seed}"
                save(args.output / f"{name}-workflow.json", changed)
                raw, elapsed = await service._run_edit(name, changed)
                (args.output / f"{name}.png").write_bytes(raw)
                results.append({"case": case["key"], "seed": seed, "elapsed_s": elapsed,
                                "source_graph": str(graph_path.relative_to(args.root)),
                                "image": f"{name}.png", "old": case["old"], "new": case["new"]})
                save(args.output / "results.json", results)
                print(f"{name}: {elapsed:.2f}秒で完了", flush=True)
    finally:
        await service.comfy.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
