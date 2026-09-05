"""既存LoRAと同じseedで新旧2枚ずつ比較する。教材・本番台帳は変更しない。"""
import argparse
import asyncio
import base64
from copy import deepcopy
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx


async def main(args):
    args.cache.mkdir(parents=True, exist_ok=False)
    root = args.cache.resolve()
    os.environ["SPRITEFORGE_CACHE"] = str(root)
    from backend.comfy import Comfy
    from backend.services import Services
    from backend.intent import IntentRequest, Proposal

    def save(name, value):
        (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    class ObservedComfy(Comfy):
        async def submit(self, workflow, client_id):
            save(f"workflow-{client_id}-{len(list(root.glob('workflow-*.json')))}.json", workflow)
            return await super().submit(workflow, client_id)

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{args.source}/api/characters/{quote(args.name)}")
        response.raise_for_status()
        original = response.json()
        save("source-record.json", original)
        native = json.loads(args.interpretation.read_text())
        comfy = ObservedComfy()
        service = Services(comfy=comfy)
        save("gpu.json", await comfy.stats())
        queue = await comfy.queue()
        if queue["queue_running"] or queue["queue_pending"]:
            raise RuntimeError("GPUは他の処理に使われています。比較はまだ開始していません。")
        await service.create_character(original["name"], original["char_desc"], original.get("attr", ""), original["trigger"], original["lora_name"])
        if len(args.reference) != len(native["references"]):
            raise ValueError("解釈時と同じ順序・枚数の参考画像を指定してください。")
        for path in args.reference:
            await service.add_samples(args.name, str(path.resolve()))
        if original.get("style"):
            response = await client.get(f"{args.source}/api/styles/{quote(original['style'])}")
            response.raise_for_status()
            style = response.json()
            service._save_style(style)
            rec = service._load_character(args.name)
            rec.update(style=original["style"], style_strength=original.get("style_strength", 0.7))
            service._save_character(rec)
        baseline = await service.preview_character(args.name, seed=1, count=2)
        save("baseline.json", baseline)
        print("従来の条件: 2枚完了", flush=True)

        async def retained_proposal(job, images):
            result = deepcopy(native["proposal"])
            references = {ref["sample_index"]: job["references"][i] for i, ref in enumerate(native["references"])}
            for item in [*result["observations"], *result["changes"]]:
                if item["reference"] is not None:
                    item["reference"] = references[item["reference"]["sample_index"]]
            job["interpreter"] = native["interpreter"]
            return result

        # 開発実験で確認した既存応答を使う。ここでモデルを再度呼ばない。
        service.intent_interpreter = retained_proposal
        job = await service.interpret_comment(IntentRequest(name=args.name, stage="preview", comment=native["original_comment"]))
        await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(job["proposal"]))
        changed = await service.preview_character(args.name, seed=1, count=2, intent_job_id=job["job_id"])
        save("changed.json", changed)
        await comfy.close()
        print("解釈した条件: 2枚完了", flush=True)

    cards = []
    for i in range(2):
        for label, result in (("従来", baseline), ("解釈を反映", changed)):
            picture = result["pictures"][i]
            url = "data:image/png;base64," + base64.b64encode(Path(picture["path"]).read_bytes()).decode()
            cards.append(f'<figure><figcaption>{label} · Seed {picture["seed"]} · {picture["elapsed_s"]:.1f}秒</figcaption><img src="{html.escape(url)}"></figure>')
    content = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>衣装の注文・新旧比較</title><style>body{max-width:1100px;margin:24px auto;padding:20px;background:#f4f3ee;color:#183c32;font:16px system-ui}h1{font-size:26px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}figure{margin:0}img{width:100%;border-radius:16px}figcaption{padding:12px}pre{white-space:pre-wrap;background:white;padding:20px;border-radius:16px}</style><h1>衣装の注文・新旧比較</h1><p>完了：同じLoRA・強度・Seed 1 / 2。再学習なし。左が従来、右が解釈を反映。</p><p>' + html.escape(native["original_comment"]) + '</p><div class="grid">' + ''.join(cards) + '</div><h2>生成へ渡した変更</h2><pre>' + html.escape(changed["intent_positive"]) + '</pre><p>観察結果と画像の好みは別です。この比較は自動採用しません。</p></html>'
    (root / "comparison.html").write_text(content, encoding="utf-8")
    print(root / "comparison.html", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--interpretation", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    asyncio.run(main(parser.parse_args()))
