"""生成済み画像の指定文またはLoRA構成を変える診断。台帳は変更しない。"""
import argparse
import asyncio
import json
import uuid

from backend.app import services
from backend import workflows


async def main(args):
    original = services.events.load_job(args.job)
    if original["kind"] not in ("preview", "from_bible", "image") or original["status"] != "completed":
        raise ValueError("完了した一枚生成かプレビューを指定してください。")
    if args.old and original["prompt"].count(args.old) != 1:
        raise ValueError("置換元の表現が一箇所にありません。")
    prompt = original["prompt"].replace(args.old, args.new) if args.old else original["prompt"]
    chain = original["loras"] if args.loras is None else json.loads(args.loras)
    key = "pose-probe-" + uuid.uuid4().hex
    graph = workflows.anima_txt2img(prompt, original["seed"], turbo=False, loras=chain,
                                   negative=original["negative"], width=832, height=1216)
    raw, elapsed = await services._run_edit(key, graph)
    path = services._write_generated(key + ".png", raw)
    result = {"source_job": args.job, "old": args.old, "new": args.new,
              "workflow": graph, "path": str(path), "elapsed_s": elapsed}
    path.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "workflow"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    parser.add_argument("--old", default="")
    parser.add_argument("--new", default="")
    parser.add_argument("--loras", help="診断用のLoRA構成をJSONで指定。省略時は元の構成。")
    asyncio.run(main(parser.parse_args()))
