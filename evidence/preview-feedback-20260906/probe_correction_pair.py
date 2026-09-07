"""指摘に基づく修正候補と範囲を隔離領域へ保存する。学習・採否は行わない。"""
import argparse
import asyncio
import base64
import hashlib
from html import escape
import json
from pathlib import Path
import sys
import time

from PIL import Image, ImageChops, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.events import EventStore
from backend.services import Services
from backend import workflows


def save_report(root, result):
    if all((root / name).exists() for name in ('source.png', 'candidate.png', 'mask.png')):
        with Image.open(root / 'source.png') as source, Image.open(root / 'candidate.png') as candidate, Image.open(root / 'mask.png') as mask:
            differences = ImageChops.difference(source.convert('RGB'), candidate.convert('RGB'))
            result['measurements'] = {
                'size': list(source.size),
                'outside_mask_changed_pixels': sum(
                    value == 0 and pixel != (0, 0, 0)
                    for value, pixel in zip(mask.convert('L').get_flattened_data(), differences.get_flattened_data())
                ),
            }
    cards, historical_cards = [], []
    approved = result.get('user_approval') is not None
    for filename, title in (
        ('source.png', '修正前・ユーザーのNG画像'),
        ('raw.png', '生成した修正候補・本人承認済み' if approved else '生成した修正候補・未承認'),
        ('reference.png', '元の参考画像'),
        ('candidate.png', '過去の合成実験・教材には使用しない'),
        ('mask.png', '過去の合成範囲・採否の評価対象外'),
    ):
        path = root / filename
        if path.exists():
            encoded = base64.b64encode(path.read_bytes()).decode()
            target = historical_cards if filename in ('candidate.png', 'mask.png') else cards
            target.append(f'<figure><figcaption>{title}</figcaption><img src="data:image/png;base64,{encoded}"></figure>')
    document = ('<!doctype html><html lang="ja"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>指摘に基づく修正候補</title><style>'
                'body{font:16px sans-serif;background:#faf8f5;color:#292421;margin:24px}'
                'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}'
                'figure{margin:0;background:white;padding:12px;border:1px solid #ddd;border-radius:12px}'
                'img{width:100%;height:65vh;object-fit:contain}figcaption{font-weight:bold;margin-bottom:12px}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
                '<h1>指摘に基づく修正候補</h1>'
                + ('<p>生成した修正候補は本人承認済みです。LoRA学習はまだ行っていません。</p>' if approved
                   else '<p>未承認・LoRA学習は行っていません。</p>')
                + (f'<p>本人の評価：{escape(result["user_approval"]["comment"])}</p>' if approved else '')
                + '<p>元のNG画像と、描き直して生成した画像を比較します。合成画像は教材に使いません。</p>'
                f'<p>元の指摘：{escape(result["comment"])}</p>'
                f'<p>状態：{escape(result["status"])}</p>'
                + f'<main>{"".join(cards)}</main>'
                f'<details><summary>過去の合成実験（不採用）</summary><main>{"".join(historical_cards)}</main></details>'
                f'<details><summary>処理記録</summary><pre>{escape(json.dumps(result, ensure_ascii=False, indent=2))}</pre></details></html>')
    (root / 'report.html').write_text(document)
    (root / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))


def approve_generated(root, comment):
    result = json.loads((root / 'result.json').read_text())
    pair = {
        label: {'path': filename, 'sha256': hashlib.sha256((root / filename).read_bytes()).hexdigest()}
        for label, filename in (('preferred', 'raw.png'), ('rejected', 'source.png'))
    }
    result['user_approval'] = {'comment': comment, 'image': pair['preferred'], 'recorded_at_ns': time.time_ns()}
    result['approved_pair'] = pair
    result['status'] = '生成した修正候補を本人承認済み・学習は未実行'
    save_report(root, result)
    (root / 'approved-pair.json').write_text(json.dumps({
        'pair': pair, 'user_approval': result['user_approval'], 'ng_comment': result['comment'],
        'training_started': False,
    }, ensure_ascii=False, indent=2))


async def main(args):
    root = args.output.resolve()
    remask = getattr(args, 'remask', False)
    padding = getattr(args, 'mask_padding', 0)
    if remask:
        result = json.loads((root / 'result.json').read_text())
        previous = root / 'attempts' / str(time.time_ns())
        previous.mkdir(parents=True)
        for filename in ('result.json', 'report.html', 'mask.png', 'candidate.png'):
            if (root / filename).exists():
                (root / filename).rename(previous / filename)
        result['mask_prompt'] = args.mask_prompt
        result['status'] = '修正前後の範囲を再抽出中'
    else:
        root.mkdir(parents=True, exist_ok=False)
        for source, filename in ((args.source, 'source.png'), (args.reference, 'reference.png')):
            with Image.open(source) as picture:
                picture.convert('RGB').save(root / filename)
        result = {'status': '候補生成中', 'comment': args.comment, 'prompt': args.prompt,
              'mask_prompt': args.mask_prompt, 'seed': args.seed, 'user_approval': None,
              'source': str(args.source), 'reference': str(args.reference),
              'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'graphs': {}, 'elapsed_s': {}}
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'),
                       generated_root=root / 'generated', uploads_root=root / 'uploads',
                       characters_root=root / 'characters', styles_root=root / 'styles')
    save_report(root, result)
    started = time.monotonic()
    try:
        if not remask:
            names = [await service.comfy.upload((root / filename).read_bytes(), f'{root.name}-{filename}')
                     for filename in ('source.png', 'reference.png')]
            graph = workflows.joy_edit(names, args.prompt, args.seed)
            result['graphs']['edit'] = graph
            save_report(root, result)
            content, elapsed = await service._run_edit(root.name, graph)
            (root / 'raw.png').write_bytes(content)
            result['elapsed_s']['edit'] = elapsed
        result['status'] = '修正前後の範囲を抽出中'
        save_report(root, result)
        masks = []
        for filename in ('source.png', 'raw.png'):
            mask_job = await service.make_mask(str(root / filename), args.mask_prompt)
            masks.append(Image.open(mask_job['path']).convert('L'))
        with Image.open(root / 'source.png') as source, Image.open(root / 'raw.png') as candidate:
            if source.size != candidate.size or any(mask.size != source.size for mask in masks):
                raise ValueError('修正前後とマスクの寸法が不一致。位置合わせが必要です。')
            mask = ImageChops.lighter(*masks)
            if not mask.getbbox():
                raise ValueError('指定した変更範囲を検出できませんでした。')
            if padding:
                mask = mask.filter(ImageFilter.MaxFilter(padding * 2 + 1))
            result['mask_padding_px'] = padding
            mask.save(root / 'mask.png')
        content = service._restore_outside_mask((root / 'source.png').read_bytes(),
                                               (root / 'raw.png').read_bytes(),
                                               (root / 'mask.png').read_bytes())
        (root / 'candidate.png').write_bytes(content)
        result['status'] = '候補生成済み・本人の確認待ち'
        result['elapsed_s']['remask' if remask else 'total'] = round(time.monotonic() - started, 1)
        save_report(root, result)
    except Exception as error:
        result['status'] = '処理失敗'
        result['error'] = str(error)
        save_report(root, result)
        raise
    finally:
        await service.comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--comment')
    parser.add_argument('--prompt')
    parser.add_argument('--remask', action='store_true')
    parser.add_argument('--approve-generated', metavar='本人の評価')
    parser.add_argument('--mask-prompt')
    parser.add_argument('--mask-padding', type=int, default=0)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    if args.approve_generated:
        approve_generated(args.output.resolve(), args.approve_generated)
        sys.exit(0)
    if not args.mask_prompt:
        parser.error('--mask-prompt が必要です。')
    if args.mask_padding < 0:
        parser.error('--mask-padding は0以上で指定してください。')
    if not args.remask and not all((args.source, args.reference, args.comment, args.prompt)):
        parser.error('新規生成には --source / --reference / --comment / --prompt が必要です。')
    asyncio.run(main(args))
