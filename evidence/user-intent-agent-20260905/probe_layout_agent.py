"""構成専用の実解釈を隔離台帳で確認し、原文と全案をHTMLへ出す。"""
import argparse
import asyncio
from html import escape
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--case", choices=["outfit", "creature"], required=True)
    args = parser.parse_args()
    root = args.cache.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(root)
    from backend.services import Services
    from backend.intent import IntentRequest
    from backend.sheet_layout import LayoutUpdate
    service = Services()

    async def run():
        name = "構成の実解釈確認"
        description = "an adult man" if args.case == "outfit" else "a limbless blue slime"
        comment = "鎧の項目は水着に変更して、下着の項目を一つ追加。側面はそのまま。合計3項目で。水着は青いトランクス、下着は白いボクサーブリーフにして。" if args.case == "outfit" else "手足も衣装もない青いスライムのシートを作りたい。正面、側面、跳ねている姿の3項目だけに構成を作り直して。全項目で手足と服はなし。"
        await service.create_character(name, description)
        before = await service.get_sheet_layout(name)
        if args.case == "outfit":
            await service.save_sheet_layout(name, LayoutUpdate.model_validate({"expected": before, "panels": [before[16], before[2]]}))
        job = await service.interpret_comment(IntentRequest(name=name, stage="layout", comment=comment))
        (root / "interpretation.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))
        content = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>構成案の実解釈</title><style>body{font:16px/1.7 system-ui;background:#f4f3ee;color:#193e32;max-width:1040px;margin:24px auto;padding:20px}article{padding:20px;border-radius:16px;background:white;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>構成案の実解釈</h1><p>既存の契約ログインで一回解釈した結果です。構成は未確定で、画像生成・学習は実行していません。</p>'
        content += f'<article><h2>注文</h2><p>{escape(comment)}</p><p>{escape(description)}</p><p>{escape(str(job["interpreter"]))}</p></article>'
        content += f'<article><h2>案の全項目</h2><pre>{escape(json.dumps(job["proposal"], ensure_ascii=False, indent=2))}</pre></article></html>'
        (root / "report.html").write_text(content)
        print(json.dumps({"result": str(root / "interpretation.json"), "status": job["status"], "panels": len(job["proposal"]["panels"]), "questions": job["proposal"]["questions"], "interpreter": job["interpreter"]}, ensure_ascii=False), flush=True)
    asyncio.run(run())


if __name__ == "__main__":
    main()
