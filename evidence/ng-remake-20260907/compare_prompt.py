"""作り直しLoRAと同一seedで、指摘の被写体を生成文へ足した列を並べる。学習しない。"""
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend import workflows
from backend.config import CACHE
from backend.events import EventStore
from backend.services import Services
from prompt_content import SUBJECT_FROM_NG, with_subject


def file_url(path):
    return "/api/file?path=" + quote(str(Path(path).resolve().relative_to(CACHE.resolve())))


def lora_name(path):
    return PureWindowsPath(path).name


def save(root, report):
    root.mkdir(parents=True, exist_ok=True)
    (root / "compare-prompt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    for seed in report["seeds"]:
        cells = []
        complete = True
        for role, label in (("plain", "作り直し・髪なし"), ("subject", "作り直し・指摘の内容")):
            item = next((p for p in report["pictures"] if p["seed"] == seed and p["role"] == role), None)
            if not item:
                complete = False
                break
            cells.append(
                f"<figure><figcaption>{escape(label)}</figcaption><a href=\"{file_url(item['path'])}\">"
                f"<img src=\"{file_url(item['path'])}\" alt=\"{escape(label)} {seed}\"></a></figure>")
        if complete:
            rows.append(f"<section><h2>seed {seed}</h2><div class=\"row\">{''.join(cells)}</div></section>")
    review = (root / "compare-prompt-review.txt").read_text(encoding="utf-8") if (root / "compare-prompt-review.txt").exists() else "生成画像の評価は未完了です。ユーザーの採否と実験担当の分類は分けて記録します。"
    (root / "compare-prompt.html").write_text(
        '<!doctype html><html lang="ja"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>生成文へ被写体を足した比較</title>"
        "<style>body{font:17px/1.5 system-ui;margin:20px;background:#faf8f5}"
        ".row{display:grid;grid-template-columns:1fr 1fr;gap:12px}img{width:100%;height:auto}"
        "figure{margin:0;background:#fff;border:1px solid #ccc;padding:8px}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        "@media(max-width:800px){.row{grid-template-columns:1fr}}</style>"
        "<h1>生成文へ被写体を足した比較</h1>"
        "<p>LoRAとseedは作り直し比較と同じです。学習していません。足したのは指摘の被写体だけです。画風語句は入れていません。本番台帳は維持しています。</p>"
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
    prompt = with_subject(baseline["prompt"])
    lora = remake["lora_name"]
    seeds = list(range(args.first_seed, args.first_seed + args.count))
    report = {
        "status": "比較生成の準備",
        "seeds": seeds,
        "pictures": [],
        "input": {
            "plain_prompt": baseline["prompt"],
            "subject_prompt": prompt,
            "subject": SUBJECT_FROM_NG,
            "negative": baseline["negative"],
            "strength": baseline["strength"],
            "width": 832,
            "height": 1216,
            "lora": lora_name(lora) if "/" in str(lora) or "\\" in str(lora) else lora,
            "first_seed": args.first_seed,
        },
    }
    if (root / "compare-prompt.json").exists():
        report = json.loads((root / "compare-prompt.json").read_text())
    for seed in seeds:
        plain = root / "generated" / f"compare-after-{seed}.png"
        if not plain.is_file():
            raise SystemExit(f"作り直し側の既存画像がありません: {plain}")
        name = f"compare-after-{seed}"
        if not any(item["name"] == name for item in report["pictures"]):
            report["pictures"].append({
                "name": name, "role": "plain", "seed": seed, "lora": report["input"]["lora"],
                "path": str(plain), "elapsed_s": 0, "prompt": "plain",
            })
    service = Services(events=EventStore(root / "events.ndjson", root / "jobs"),
                       generated_root=root / "generated", uploads_root=root / "uploads",
                       characters_root=root / "characters", styles_root=root / "styles")
    save(root, report)
    try:
        for seed in seeds:
            name = f"compare-prompt-{seed}"
            if any(item["name"] == name for item in report["pictures"]):
                continue
            report["status"] = f"subject seed {seed} を生成中"
            save(root, report)
            graph = workflows.anima_txt2img(
                prompt, seed, loras=[(report["input"]["lora"], baseline["strength"])],
                negative=baseline["negative"], width=832, height=1216)
            content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
            path = service._write_generated(f"{name}.png", content)
            report["pictures"].append({
                "name": name, "role": "subject", "seed": seed, "lora": report["input"]["lora"],
                "path": str(path), "elapsed_s": elapsed, "prompt": "subject",
            })
            save(root, report)
        report["status"] = f"{len(seeds)} seed・生成文2条件の比較完了。目視評価前。"
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
