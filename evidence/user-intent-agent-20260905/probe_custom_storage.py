"""可変構成の保存・生成・旧シート修正を、GPUなしで閲覧可能な実例へする。"""
import argparse
import asyncio
from copy import deepcopy
from html import escape
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    root = args.cache.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(root)
    from backend import app
    from backend.sheet_layout import LayoutUpdate
    from tests.test_bible import ComfyFixture, png
    service = app.services
    service.comfy = ComfyFixture()

    async def view(_image):
        return png(["#66aacb", "#e3bc78", "#bba2d3"][len(service.comfy.submitted) % 3])

    async def stats():
        return {"devices": [{"name": "構成試験・GPU未接続", "vram_total": 0, "vram_free": 0}]}

    service._view = view
    service.comfy.stats = stats

    async def setup():
        name = "構成の動作確認"
        await service.create_character(name, "he/him", lora_name="fixture.safetensors")
        before = await service.get_sheet_layout(name)
        first_layout = deepcopy([before[16], before[2]])
        first_layout[0].update(label="元の衣装", section="衣装")
        first_layout[1].update(label="側面", section="向き")
        await service.save_sheet_layout(name, LayoutUpdate.model_validate({"expected": before, "panels": first_layout}))
        first = await service.generate_character_bible(name, seed=7)
        chosen = deepcopy(first_layout[::-1])
        chosen[1]["label"] = "水着"
        chosen[1]["parts"][-1]["description_en"] = "blue one-piece swimsuit"
        added = deepcopy(chosen[1])
        added.update(key="custom_underwear", label="下着", seed_offset=23)
        added["parts"][-1]["description_en"] = "white underwear"
        chosen.append(added)
        await service.save_sheet_layout(name, LayoutUpdate.model_validate({"expected": first_layout, "panels": chosen}))
        await service.redraw_panel(name, "cos_armor", "a suit of armor", input_mode="english")
        old_html = Path(first["html_path"]).read_text()
        assert "元の衣装" in old_html and "水着" not in old_html
        second = await service.generate_character_bible(name, seed=7)
        assert [r["seed"] for r in second["panel_requests"]] == [9, 23, 30]
        assert "a suit of armor" not in second["panel_requests"][1]["prompt"]
        data = {"first": first, "second": second, "current": await service.character_info(name)}
        (root / "result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
        report = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>シート構成の保存・生成の確認</title><style>body{font:16px/1.8 system-ui;margin:24px auto;padding:16px;max-width:1080px;background:#f4f3ee;color:#183c32}section{background:white;padding:22px;border-radius:16px;margin:18px 0}iframe{width:100%;height:820px;border:0;border-radius:12px}code{overflow-wrap:anywhere}.notice{background:#f5e8cf;padding:20px;border-radius:12px}</style><h1>シートの項目を変えても、旧画像の対応を保つ</h1><p class="notice">保存・生成経路の動作試験です。色の四角は試験画像で、AIが衣装を描いた結果ではありません。GPU・実解釈・学習・本番機能配備は未実施です。</p><section><h2>確認した操作</h2><p>元の2項目を保存して生成。その後、順序を入れ替え、衣装を水着へ変更し、下着の項目を追加して3項目を保存しました。旧シートを描き直しても見出しは元のままで、新しい構成には旧鎧の修正が混入していません。</p></section>'
        for heading, result, source in [("旧シートは旧構成を保持", first, old_html), ("新しい構成の3項目", second, Path(second["html_path"]).read_text())]:
            report += f'<section><h2>{heading}</h2><iframe title="{heading}" srcdoc="{escape(source, quote=True)}"></iframe>'
            for panel, request in zip(result["layout"], result["panel_requests"]):
                report += f'<p>{escape(panel["label"])} · Seed {request["seed"]}<br><code>{escape(request["prompt"])}</code></p>'
            report += '</section>'
        report += '<p>構成の提案・編集画面は後続で接続します。このページは機能全体の完成報告ではありません。</p></html>'
        (root / "report.html").write_text(report)
        # ブラウザーでは通常の制作工程を通るため、試験画像を参考画像にする。
        await service.add_samples(name, str(Path(second["panels_dir"]) / "custom_underwear.png"))
        print(json.dumps({"report": str(root / "report.html"), "panels": second["total_panels"]}, ensure_ascii=False), flush=True)
    asyncio.run(setup())
    if args.serve:
        import uvicorn
        uvicorn.run(app.app, host="127.0.0.1", port=8767)


if __name__ == "__main__":
    main()
