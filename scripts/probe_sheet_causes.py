"""保存済み設定画グラフの指定入力だけを変える診断実験。製品設定は更新しない。"""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path

from scripts.probe_intent_prompt import replace_positive


def perturb(graph, case):
    if case["factor"] == "positive_phrase":
        return replace_positive(graph, case["old"], case["new"])
    if case["factor"] != "node_inputs":
        raise ValueError("未定義の比較条件です。")
    result = deepcopy(graph)
    for change in case["changes"]:
        value = result[change["node"]]["inputs"]
        if value[change["input"]] != change["before"]:
            raise ValueError("比較元の入力が事前条件と一致しません。")
        value[change["input"]] = change["after"]
    return result


async def main(args):
    cases = json.loads(args.cases.read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(args.output.resolve())
    from backend.services import Services
    service = Services()
    results = []
    def save(name, data):
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        queue = await service.comfy.queue()
        if queue["queue_running"] or queue["queue_pending"]:
            raise RuntimeError("GPU使用中です。診断生成は開始していません。")
        save("gpu.json", await service.comfy.stats())
        for case in cases:
            graph = json.loads((args.root / case["graph"]).read_text())
            changed = perturb(graph, case)
            save(case["key"] + "-workflow.json", changed)
            raw, elapsed = await service._run_edit(case["key"], changed)
            (args.output / (case["key"] + ".png")).write_bytes(raw)
            results.append({**case, "seed": changed["23"]["inputs"]["seed"], "elapsed_s": elapsed,
                            "image": case["key"] + ".png"})
            save("results.json", results)
            print(f"{case['key']}: {elapsed}秒で完了", flush=True)
    finally:
        await service.comfy.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
