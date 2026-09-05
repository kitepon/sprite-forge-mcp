"""実画像検証の目録と実行記録から、欠落のない比較ページを生成する。"""
import argparse
import base64
import html
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(cache, observations, output):
    cases = read(observations)
    listed = [case["file"] for case in cases]
    actual = {path.name for path in (cache / "generated").glob("*.png")}
    if len(set(listed)) != len(listed) or set(listed) != actual:
        raise ValueError("画像目録不一致: " + str(set(listed) ^ actual))
    groups = {}
    for case in cases:
        picture = cache / "generated" / case["file"]
        diagnostic = "job" not in case
        record = read(picture.with_suffix(".json")) if diagnostic else read(cache / "jobs" / (case["job"] + ".json"))
        source = read(cache / "jobs" / (record["source_job"] + ".json")) if diagnostic else record
        if source["status"] != "completed":
            raise ValueError("未完了の生成: " + source["job_id"])
        intent = read(cache / "jobs" / (source["intent_job_id"] + ".json"))
        if not intent["accepted"]:
            raise ValueError("注文が未採用: " + intent["job_id"])
        evidence = {"生成記録": record, "元コメント": intent["original_comment"],
                    "提案": intent["proposal"], "確定条件": intent["effective_conditions"],
                    "解釈の実行情報": intent["interpreter"]}
        data = base64.b64encode(picture.read_bytes()).decode()
        card = f'''<figure><figcaption><h3>{html.escape(case["title"])}</h3>
<p>{html.escape(case["observation"])}</p></figcaption>
<img width="832" height="1216" alt="{html.escape(case["title"])}の生成画像" src="data:image/png;base64,{data}" loading="lazy">
<details><summary>実行条件・注文・生成命令</summary><pre>{html.escape(json.dumps(evidence, ensure_ascii=False, indent=2))}</pre></details></figure>'''
        groups.setdefault(case["group"], []).append(card)
    sections = "".join(f'<section><h2>{html.escape(title)}</h2><div class="grid">{"".join(cards)}</div></section>' for title, cards in groups.items())
    output.write_text('''<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>コメント反映・実画像の比較</title>
<style>body{margin:0;background:#f7f5f0;color:#243c36;font:16px/1.7 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:32px 24px}h1{font-size:30px;line-height:1.4}h2{font-size:23px;margin-top:48px}h3{font-size:17px;margin:0}header{max-width:850px}.status{border-left:4px solid #ac6b23;padding-left:16px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px}figure{margin:0;min-width:0;border-top:1px solid #c9d5d0;padding-top:18px}figcaption{min-height:150px}img{display:block;width:100%;height:auto;border-radius:8px}summary{cursor:pointer;padding:14px 0;text-decoration:underline}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace;background:#e9eee9;padding:16px}footer{margin-top:40px}@media(max-width:600px){main{padding:20px 16px}.grid{grid-template-columns:1fr}figcaption{min-height:0}h1{font-size:25px}}</style>
<main><header><p>Sprite Forge ／ 実画像検証</p><h1>注文は届く。学習の強さによって、絵への反映が変わる。</h1>
<p class="status">検証は未完了。本番の設定変更・再学習はしていません。通常経路の3枚と、原因を調べるための比較7枚を全件掲載しています。</p>
<p>通常の強度では衣装や背景が元の学習画像に引かれる例を確認。弱めると注文に近づきますが、顔・髪の描かれ方も変わります。この結果だけで全キャラクターの既定値を変更することはしません。</p>
<p>全画像は同じ seed 73・Anima Base・832×1216。通常経路では公式Codex CLIがコメントを解釈し、提案を確認・採用して生成しました。診断画像は同じ生成命令を基にLoRA強度や方向の語句を変えたもので、製品の完成済み機能ではありません。各例1 seedの観察で、成功率の測定ではありません。</p>
<p>比較の読み方：衣装変更の通常条件から、画風だけを外した例／キャラクターだけを弱めた例を比較できます。キャラクター0.4の例から画風も0.3に下げた結果が、先頭の右の画像です。横向きは強度と語句を分けて比較しています。</p></header>'''
                      + sections + '<footer>全10枚の目録一致を確認済み。見た目の記述は開発担当の観察であり、自動の採用判定やオーナーによる承認ではありません。</footer></main></html>', encoding="utf-8")
    return {"status": "生成済み", "images": len(cases), "inventory_matched": True, "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.cache, args.observations, args.output), ensure_ascii=False))
