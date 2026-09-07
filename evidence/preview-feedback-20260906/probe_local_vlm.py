"""Windows ComfyUIの視覚言語モデルで20枚を読み、NG特徴を比較する。"""
import argparse
import asyncio
from html import escape
import json
from pathlib import Path
import sys
import time
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.comfy import Comfy


OBSERVE = """この画像の髪型だけを観察してください。衣装・顔・背景の説明は不要です。
確認したい違いは『ツインテールではない髪型』と『長い髪』です。画像をNGと決めつけず、見えている事実を日本語で具体的に記述してください。
髪を結んだ位置、左右に垂れる束の有無、下ろした後ろ髪の長さ（顎・肩・腰など）、頭頂の短い束と下がる束の区別を含めてください。
見えない結び目は推測と明示してください。複数人物がいれば髪型の相違だけ書いてください。200字程度。"""


def graph(model, prompt, image=None, keep=True):
    inputs = dict(model_name=model, quantization='None (FP16)', attention_mode='sdpa',
                  use_torch_compile=False, device='cuda:0', preset_prompt='🖼️ Detailed Description',
                  custom_prompt=prompt, max_tokens=768 if image else 2048, temperature=.1,
                  top_p=.9, num_beams=1, repetition_penalty=1.1, frame_count=16,
                  video_frame_size='auto', keep_model_loaded=keep, seed=42)
    workflow = {'2': {'class_type': 'AILab_QwenVL_Advanced', 'inputs': inputs},
                '3': {'class_type': 'PreviewAny', 'inputs': {'source': ['2', 0]}}}
    if image:
        workflow['1'] = {'class_type': 'LoadImage', 'inputs': {'image': image}}
        inputs['image'] = ['1', 0]
    return workflow


def comparison_prompt(selection, observations):
    return ('次の20枚の髪型観察を比較し、ユーザーが指定したNGに特有の形状を抽出してください。'
            'per_image_reasonsは該当画像について全体reasonより優先する確定済みの理由です。矛盾扱いや除外をしてはいけません。'
            '未選択は未判定であり、OK教材ではありません。NGの種類が違う場合は分けてください。'
            '候補番号、観察による根拠、比較で共通だったため除去しない特徴、ESDへ渡す英語の具体的な髪型の概念句を示してください。'
            '否定句だけのnot twintailsや、衣装・瞳・体形・画風・人数を除去概念に含めないでください。'
            '入力の観察が矛盾する場合は矛盾を報告し、ユーザーのNG指定を訂正しないでください。\n'
            + json.dumps({'selection': selection, 'observations': observations}, ensure_ascii=False))


def save(root, report):
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    sections = []
    for model in report['models']:
        rows = []
        for item in report['results']:
            if item['model'] != model:
                continue
            title = f"候補 {item['number']:02}" if item['number'] else '20枚の比較・NG特徴'
            picture = ''
            if item['number']:
                path = quote(report['batch'] + f"/generated/candidate-{item['number']:02}.png")
                picture = f'<img loading="lazy" src="/api/file?path={path}" alt="{title}">'
            rows.append(f'<article><h3>{title}</h3>{picture}<p>{escape(item["status"])}</p>'
                        f'<p>所要時間：{item.get("elapsed_s", "計測中")} 秒（初回は取得・読込を含む）</p>'
                        f'<pre>{escape(item.get("text", ""))}</pre></article>')
        sections.append(f'<section><h2>{escape(model)}</h2>{"".join(rows)}</section>')
    (root / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>ローカル画像解析の比較</title>'
        '<style>body{font:17px/1.6 sans-serif;margin:24px;background:#faf8f5}article{background:white;padding:16px;margin:12px 0;display:flow-root}'
        'img{width:180px;max-width:40%;height:auto;float:left;margin-right:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>Windowsローカル画像解析の比較</h1><p>同じ20枚・同じ指示。外部画像解析APIは使いません。学習は開始しません。</p>'
        f'<p><strong>{escape(report["status"])}</strong></p><p>{escape(report.get("error", ""))}</p>'
        + ''.join(sections) + '</html>')


async def execute(comfy, root, report, model, number, workflow):
    item = next((item for item in report['results'] if (item['model'], item['number']) == (model, number)), None)
    if item and item['status'] == '完了':
        return
    if item is None:
        item = dict(model=model, number=number, workflow=workflow, status='投入前', started=time.time())
        report['results'].append(item)
        save(root, report)
        item['prompt_id'] = await comfy.submit(workflow, 'sprite-local-vlm')
        item['status'] = '実行待ち／モデル取得・解析中'
        save(root, report)
    if 'prompt_id' not in item:
        raise RuntimeError('投入結果が不明です。ComfyUIのキューを確認してください。自動再投入はしません。')
    while True:
        history = await comfy.history(item['prompt_id'])
        if history:
            item['history'] = history
            if history['status']['status_str'] == 'error':
                raise RuntimeError(json.dumps(history['status'], ensure_ascii=False))
            if history['status']['completed']:
                item.update(text='\n'.join(history['outputs']['3']['text']), status='完了',
                            elapsed_s=round(time.time() - item['started'], 2))
                save(root, report)
                return
        await asyncio.sleep(3)


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = json.loads((args.batch / 'report.json').read_text())
    if args.single_image is not None:
        source['pictures'] = [item for item in source['pictures'] if item['number'] == args.single_image]
        if not source['pictures']:
            raise ValueError('指定画像がありません。')
    selection = json.loads((args.batch / 'selection.json').read_text())
    report = json.loads((root / 'report.json').read_text()) if (root / 'report.json').exists() else {
        'batch': args.batch.name, 'models': args.models, 'selection': selection, 'results': [], 'training_started': False}
    comfy = Comfy()
    try:
        report['status'] = '画像解析を準備中'
        save(root, report)
        for model in report['models']:
            for picture in source['pictures']:
                number = picture['number']
                report['status'] = f'{model}：候補{number:02}を解析中'
                save(root, report)
                if not any(item['model'] == model and item['number'] == number for item in report['results']):
                    uploaded = await comfy.upload(Path(picture['path']).read_bytes(), f'local-vlm-{args.batch.name}-{number:02}.png')
                    workflow = graph(model, args.observation, uploaded, keep=args.single_image is None)
                else:
                    workflow = next(item['workflow'] for item in report['results'] if item['model'] == model and item['number'] == number)
                await execute(comfy, root, report, model, number, workflow)
            if args.single_image is not None:
                continue
            observations = [{'number': item['number'], 'text': item['text']} for item in report['results']
                            if item['model'] == model and item['number']]
            report['status'] = f'{model}：20枚の観察を比較中'
            await execute(comfy, root, report, model, 0, graph(model, comparison_prompt(selection, observations), keep=False))
        report['status'] = '指定した解析が完了。抽出品質の確認待ち。'
        save(root, report)
    except Exception as error:
        report.update(status='解析失敗', error=str(error))
        save(root, report)
        raise
    finally:
        await comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models', nargs='+', default=['Qwen3-VL-4B-Instruct', 'Qwen3-VL-8B-Instruct'])
    parser.add_argument('--single-image', type=int)
    parser.add_argument('--observation', default=OBSERVE)
    asyncio.run(main(parser.parse_args()))
