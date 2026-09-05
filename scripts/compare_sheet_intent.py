"""確認した構成と注文を隔離台帳へ移し、同じLoRAで設定画を比較する。"""
import argparse
import asyncio
import base64
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx

from scripts.check_intent import apply_retained


async def prepare(service, original, native):
    from backend.sheet_layout import LayoutUpdate
    name = original["name"]
    await service.create_character(name, native["record_description"], original.get("attr", ""),
                                   original["trigger"], original["lora_name"])
    for ref in native["references"]:
        await service.add_samples(name, ref["path"])
    before = await service.get_sheet_layout(name)
    await service.save_sheet_layout(name, LayoutUpdate.model_validate({"expected": before, "panels": native["sheet_layout"]}))
    return name


async def main(args):
    if not args.baseline_job:
        args.output.mkdir(parents=True, exist_ok=False)
    root = args.output.resolve()
    os.environ["SPRITEFORGE_CACHE"] = str(root)
    from backend.comfy import Comfy
    from backend.services import Services

    def save(name, data):
        (root / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    class ObservedComfy(Comfy):
        async def submit(self, graph, client_id):
            save(f"workflow-{client_id}-{len(list(root.glob('workflow-*.json')))}.json", graph)
            return await super().submit(graph, client_id)

    native = json.loads(args.interpretation.read_text())
    if native["stage"] != "sheet" or native["proposal"]["questions"] or native["base_conditions"]:
        raise ValueError("共通条件のない隔離台帳で、親が確認した設定画の解釈を指定してください。")
    service = Services(comfy=ObservedComfy())
    async with httpx.AsyncClient(timeout=60) as client:
        url = f"{args.source}/api/characters/{quote(args.name)}"
        response = await client.get(url)
        response.raise_for_status()
        original = response.json()
        if args.baseline_job:
            if json.loads((root / "source-record.json").read_text()) != original:
                raise ValueError("比較元の台帳が初回から変わっています。")
        else:
            save("source-record.json", original)
        try:
            if not original.get("lora_name"):
                raise ValueError("比較元に学習済みLoRAがありません。")
            queue = await service.comfy.queue()
            if queue["queue_running"] or queue["queue_pending"]:
                raise RuntimeError("GPU使用中です。比較は開始していません。")
            save("gpu.json", await service.comfy.stats())
            name = original["name"] if args.baseline_job else await prepare(service, original, native)
            if original.get("style") and not args.baseline_job:
                response = await client.get(f"{args.source}/api/styles/{quote(original['style'])}")
                response.raise_for_status()
                service._save_style(response.json())
                record = service._load_character(name)
                record.update(style=original["style"], style_strength=original.get("style_strength", 0.7))
                service._save_character(record)
            if args.baseline_job:
                baseline = recover_baseline(service, args.baseline_job, native, root)
            else:
                baseline = await service.generate_character_bible(name, seed=args.seed)
            save("baseline.json", baseline)
            print(f"構成のみ: {baseline['completed_panels']}枚完了", flush=True)
            accepted = await apply_retained(service, name, native, stage="sheet")
            save("accepted.json", accepted)
            changed = await service.generate_character_bible(name, seed=args.seed, intent_job_id=accepted["job_id"])
            save("changed.json", changed)
            save("record-after.json", await service.character_info(name))
            print(f"注文を反映: {changed['completed_panels']}枚完了", flush=True)
        finally:
            await service.comfy.close()
            response = await client.get(url)
            response.raise_for_status()
            after = response.json()
            save("source-record-after.json", after)
            if after != original:
                raise RuntimeError("本番台帳が比較中に更新されています。前後の記録を確認してください。")

    cards = []
    for index, panel in enumerate(changed["layout"]):
        for title, job in (("構成のみ", baseline), ("注文を反映", changed)):
            data = base64.b64encode(Path(job["panels"][index]).read_bytes()).decode("ascii")
            request = job["panel_requests"][index]
            cards.append(f'<figure><figcaption>{escape(panel["label"])}・{title}・Seed {request["seed"]}</figcaption><img src="data:image/png;base64,{data}"><details><summary>実際の生成条件</summary><pre>{escape(json.dumps(request, ensure_ascii=False, indent=2))}</pre></details></figure>')
    page = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>人間の設定画・注文反映の比較</title><style>body{max-width:1100px;margin:24px auto;padding:18px;background:#f4f3ee;color:#183c32;font:16px/1.7 system-ui}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}figure{margin:0;background:white;padding:12px;border-radius:16px}img{width:100%;height:520px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}@media(max-width:600px){img{height:300px}.grid{gap:8px}figure{padding:6px}}</style><h1>人間の設定画・注文反映の比較</h1><p>左は確定した構成、右は今回の注文を反映。同じAnima・LoRA・Seed。再学習なし、本番台帳無変更。</p><p>' + escape(native["original_comment"]) + '</p><div class="grid">' + ''.join(cards) + '</div><p>生成の完走と、画像の品質は別に判定します。別キャラクターの画像品質は未検証です。</p></html>'
    (root / "comparison.html").write_text(page, encoding="utf-8")
    print(root / "comparison.html", flush=True)


def recover_baseline(service, job_id, native, root):
    """生成済み画像を回収し、共通の合成処理だけ実行する。元の失敗ジョブは変更しない。"""
    from backend import bible
    from backend.sheet_layout import panel_from
    job = service.events.load_job(job_id)
    if (job["kind"] != "character_bible" or job["status"] != "failed"
            or job["layout"] != native["sheet_layout"]
            or job["completed_panels"] != len(job["layout"])
            or len(job["panels"]) != len(job["layout"])):
        raise ValueError("全画像が生成済みの、同じ構成の失敗ジョブだけを回収できます。")
    record = service._load_character(job["name"])
    panels = [(p["key"], Path(path)) for p, path in zip(job["layout"], job["panels"])]
    specs = [panel_from(p) for p in job["layout"]]
    path = bible.compose_model_sheet(job["name"], record.get("attr", ""), panels,
                                    Path(record["samples_sheet"]), root / "baseline-recovered.png", specs)
    return {**job, "comparison_recovery": {"operation": "compose_only", "sheet_path": str(path)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interpretation", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--baseline-job", default="", help="全画像生成後に合成で失敗した比較元を、再生成せず回収する。")
    asyncio.run(main(parser.parse_args()))
