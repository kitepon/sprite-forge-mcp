"""元の生成文のまま、元LoRAと作り直しLoRAを未使用seedで並べる。髪の語句は足さない。"""
import argparse
import asyncio
from html import escape
import json
from pathlib import Path
from pathlib import PureWindowsPath
import sys
from urllib.parse import quote
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import workflows
from backend.config import CACHE
from backend.events import EventStore
from backend.services import Services


def file_url(path):
    return "/api/file?path=" + quote(str(Path(path).resolve().relative_to(CACHE.resolve())))


def lora_name(path):
    return PureWindowsPath(path).name


def save(root, report):
    root.mkdir(parents=True, exist_ok=True)
    (root / "compare.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    for seed in report["seeds"]:
        before = next((item for item in report["pictures"] if item["seed"] == seed and item["role"] == "before"), None)
        after = next((item for item in report["pictures"] if item["seed"] == seed and item["role"] == "after"), None)
        if not before or not after:
            continue
        rows.append(
            f"<section><h2>seed {seed}</h2><div class=\"pair\">"
            f"<figure><figcaption>元LoRA</figcaption><a href=\"{file_url(before['path'])}\">"
            f"<img src=\"{file_url(before['path'])}\" alt=\"元 {seed}\"></a></figure>"
            f"<figure><figcaption>作り直し</figcaption><a href=\"{file_url(after['path'])}\">"
            f"<img src=\"{file_url(after['path'])}\" alt=\"作り直し {seed}\"></a></figure>"
            "</div></section>")
    review = (root / "compare-review.txt").read_text(encoding="utf-8") if (root / "compare-review.txt").exists() else "生成画像の評価は未完了です。ユーザーの採否と実験担当の分類は分けて記録します。"
    (root / "compare.html").write_text(
        '<!doctype html><html lang="ja"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>教材作り直しの比較</title>"
        "<style>body{font:17px/1.5 system-ui;margin:20px;background:#faf8f5}"
        ".pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}img{width:100%;height:auto}"
        "figure{margin:0;background:#fff;border:1px solid #ccc;padding:8px}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>"
        "<h1>教材作り直しの比較</h1>"
        "<p>生成文は作り直し前と同じです。髪の指定は足していません。元LoRAと本番台帳は維持しています。</p>"
        f"<p>{escape(report.get('status') or '')}</p>"
        f"<pre>{escape(review)}</pre>"
        + "".join(rows)
        + f"<details><summary>生成条件</summary><pre>{escape(json.dumps(report.get('input') or {}, ensure_ascii=False, indent=2))}</pre></details>"
        + "</html>",
        encoding="utf-8")


async def main(args):
    root = args.output.resolve()
    baseline = json.loads(args.baseline.read_text())["input"]
    remake = json.loads(args.remake.read_text())
    seeds = list(range(args.first_seed, args.first_seed + args.count))
    report = {
        "status": "比較生成の準備",
        "seeds": seeds,
        "pictures": [],
        "input": {
            "prompt": baseline["prompt"],
            "negative": baseline["negative"],
            "strength": baseline["strength"],
            "width": 832,
            "height": 1216,
            "before_lora": lora_name(baseline["lora"]),
            "after_lora": remake["lora_name"],
            "first_seed": args.first_seed,
        },
    }
    if (root / "compare.json").exists():
        report = json.loads((root / "compare.json").read_text())
    service = Services(events=EventStore(root / "events.ndjson", root / "jobs"),
                       generated_root=root / "generated", uploads_root=root / "uploads",
                       characters_root=root / "characters", styles_root=root / "styles")
    save(root, report)
    try:
        for seed in seeds:
            for role, lora in (("before", report["input"]["before_lora"]), ("after", report["input"]["after_lora"])):
                name = f"compare-{role}-{seed}"
                if any(item["name"] == name for item in report["pictures"]):
                    continue
                report["status"] = f"{role} seed {seed} を生成中"
                save(root, report)
                graph = workflows.anima_txt2img(
                    baseline["prompt"], seed, loras=[(lora, baseline["strength"])],
                    negative=baseline["negative"], width=832, height=1216)
                content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
                path = service._write_generated(f"{name}.png", content)
                report["pictures"].append({
                    "name": name, "role": role, "seed": seed, "lora": lora,
                    "path": str(path), "elapsed_s": elapsed,
                })
                save(root, report)
        report["status"] = f"{len(seeds)} seed・2条件の比較生成完了。目視評価前。"
        save(root, report)
        print(json.dumps({"status": report["status"], "pictures": len(report["pictures"])}, ensure_ascii=False))
    except Exception as error:
        report.update(status="比較生成に失敗", error=str(error))
        save(root, report)
        raise
    finally:
        await service.comfy.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--remake", type=Path, required=True)
    parser.add_argument("--first-seed", type=int, default=601)
    parser.add_argument("--count", type=int, default=10)
    asyncio.run(main(parser.parse_args()))
