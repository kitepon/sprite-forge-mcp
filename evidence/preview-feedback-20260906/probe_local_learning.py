"""本人承認済みの生成画像で、局所選好学習とOK通常学習を隔離比較する。"""
import argparse
import asyncio
import hashlib
from html import escape
import json
from pathlib import Path
import sys
from urllib.parse import quote
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import box, workflows
from backend.config import BOX_LORAS
from backend.events import EventStore
from backend.services import Services


def save(root, report):
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    names = {'before': '学習前', 'ok_only': '承認画像のみ通常学習', 'local': '局所選好学習'}
    labels = {'twintails': 'ツインテール', 'violet_eyes': '紫系の瞳', 'outfit_family': '衣装の基本構成', 'single_figure': '単体の全身像'}
    assessment = '<p>目視評価は未記録です。</p>'
    status_display = report['status']
    if (root / 'review.json').exists():
        review = json.loads((root / 'review.json').read_text())
        status_display = '比較と目視評価を記録済み（製品の合格判定ではありません）'
        assessed = []
        for name, row in review['conditions'].items():
            if set(row['reviewed_seeds']) != set(report['seeds']):
                raise ValueError('目視評価に未掲載または未評価のseedがあります。')
            counts = '、'.join(f'{labels[key]} {len(row[key])}/{len(row["reviewed_seeds"])}' for key in review['criteria'])
            assessed.append(f'<li>{names[name]}：{counts}<p>{escape(row["notes"])}</p></li>')
        assessment = f'<h2>目視評価</h2><p>{escape(review["evaluator"])}</p><p>{escape(review["summary"])}</p><ul>{"".join(assessed)}</ul>'
        assessment += f'<details><summary>評価項目の意味</summary><pre>{escape(json.dumps(review["criteria"], ensure_ascii=False, indent=2))}</pre></details>'
    def link(path):
        return '/api/file?path=' + quote(str(Path(path).relative_to(Path.cwd() / '.cache')))
    rows = []
    for seed in report['seeds']:
        cells = []
        for name in names:
            picture = next((item for item in report['conditions'][name]['pictures'] if item['seed'] == seed), None)
            cells.append(f'<td><a href="{link(picture["path"])}"><img src="{link(picture["path"])}"></a></td>' if picture else '<td>未生成</td>')
        rows.append(f'<tr><th>{seed}</th>{"".join(cells)}</tr>')
    source = report['approval_root']
    document = ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>LoRA更新後の新しい出力</title><style>body{font:16px sans-serif;margin:24px;background:#faf8f5}'
                'table{width:100%;border-collapse:collapse}td{width:32%}img{width:100%}td,th{border:1px solid #ccc;padding:6px}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>LoRA更新後の新しい出力</h1>'
                '<p>これは教材の修正画像ではなく、各LoRAで新たに生成した画像の比較です。髪型の改善と顔・衣装の維持を確認します。</p>'
                f'<p>状態：{escape(status_display)}。追加学習 {report["steps"]} 回。</p>'
                f'<p><a href="{link(Path(source) / "source.png")}">教材の元NG画像</a> ／ '
                f'<a href="{link(Path(source) / "raw.png")}">本人承認済みの生成画像</a>（合成画像は使用しません）</p>'
                f'<p>{escape(report.get("error", ""))}</p>{assessment}<table><tr><th>seed</th>{"".join(f"<th>{value}</th>" for value in names.values())}</tr>{"".join(rows)}</table>'
                f'<details><summary>学習と生成の記録</summary><pre>{escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></html>')
    (root / 'report.html').write_text(document)


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=args.resume)
    approval_root = args.approval.resolve()
    approved = json.loads((approval_root / 'approved-pair.json').read_text())
    for image in approved['pair'].values():
        if hashlib.sha256((approval_root / image['path']).read_bytes()).hexdigest() != image['sha256']:
            raise ValueError('本人が評価した画像と教材のハッシュが一致しません。')
    data = json.loads(args.baseline.read_text())['input']
    remote = 'C:/sf/' + root.name
    source_lora = Path(data['lora']).name
    data.update(pairs=[[remote + '/raw.png', remote + '/source.png']], masks=[remote + '/mask.png'], fixed_loras=[])
    report = {'status': '教材準備中', 'approval_root': str(approval_root), 'approval': approved,
              'steps': args.steps, 'seeds': list(range(args.seed, args.seed + 10)),
              'conditions': {name: {'pictures': [], 'status': '未実行'} for name in ('before', 'ok_only', 'local')}}
    if args.resume:
        report = json.loads((root / 'report.json').read_text())
        if report['approval'] != approved or report['steps'] != args.steps:
            raise ValueError('再開時の教材または学習条件が元の実験と一致しません。')
        report.pop('error', None)
    if getattr(args, 'evaluate_trained', None):
        trained = json.loads(args.evaluate_trained.read_text())
        if trained['approval'] != approved or any(row['status'] != '生成完了' for row in trained['conditions'].values()):
            raise ValueError('完了済みの同じ教材による比較記録が必要です。')
        report['steps'] = trained['steps']
        report['trained_report'] = str(args.evaluate_trained)
        report['conditions'] = {name: {**row, 'pictures': [], 'status': '未生成'} for name, row in trained['conditions'].items()}
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    save(root, report)
    async def command(arguments, logfile):
        with logfile.open('wb') as output:
            process = await asyncio.create_subprocess_exec(*arguments, stdout=output, stderr=asyncio.subprocess.STDOUT)
            if await process.wait():
                raise RuntimeError(f'処理失敗。記録: {logfile}')
    async def transfer(local, destination):
        code, message = await box.copy_to_box(local, destination)
        if code:
            raise RuntimeError(message)
    try:
        await command(['ssh', 'fox', 'pwsh.exe', '-NoProfile', '-Command', 'New-Item', '-ItemType', 'Directory', '-Force', '-Path', remote], root / 'prepare.log')
        for filename in ('raw.png', 'source.png', 'mask.png'):
            await transfer(approval_root / filename, remote + '/' + filename)
        for filename in ('preference_train.py', 'preference_loss.py'):
            await transfer(Path('box') / filename, remote + '/' + filename)
        config = root / 'input.json'
        config.write_text(json.dumps(data))
        await transfer(config, remote + '/input.json')
        for condition, row in report['conditions'].items():
            if row['status'] == '生成完了':
                continue
            lora = row.get('lora', source_lora)
            if condition != 'before':
                lora = row.get('lora', f'{root.name}_{condition}.safetensors')
                output = BOX_LORAS.replace('\\', '/') + '/' + lora
                if condition == args.recover_trained:
                    code, message = await box.copy_from_box(output.replace('.safetensors', '.json'), root / f'{condition}.json')
                    if code:
                        raise RuntimeError(message)
                    row['training'] = json.loads((root / f'{condition}.json').read_text())
                    save(root, report)
                if row['status'] == '学習中' and 'training' not in row:
                    raise RuntimeError('前回の学習終了状態が不明です。結果確認後に --recover-trained で回収してください。')
            if condition != 'before' and 'training' not in row:
                report['status'] = f'{condition}の学習中'
                row['status'] = '学習中'
                save(root, report)
                response = await service.comfy.client.post(service.comfy.base_url + '/free', json={'unload_models': True, 'free_memory': True})
                response.raise_for_status()
                await command(['ssh', 'fox', 'C:/sf/venv/Scripts/python.exe', remote + '/preference_train.py',
                               '--sd-scripts', 'C:/sd-scripts', '--input', remote + '/input.json', '--output', output,
                               '--steps', str(args.steps), '--learning-rate', '1e-5', '--beta', '1',
                               '--objective', 'ok_only' if condition == 'ok_only' else 'preference'], root / f'{condition}.log')
                code, message = await box.copy_from_box(output.replace('.safetensors', '.json'), root / f'{condition}.json')
                if code:
                    raise RuntimeError(message)
                row['training'] = json.loads((root / f'{condition}.json').read_text())
            row['lora'] = lora
            row['status'] = '生成中'
            for seed in report['seeds']:
                if any(item['seed'] == seed for item in row['pictures']):
                    continue
                report['status'] = f'{condition}の新しい出力を生成中（seed {seed}）'
                save(root, report)
                graph = workflows.anima_txt2img(data['prompt'], seed, loras=[(lora, data['strength'])],
                                               negative=data['negative'], width=832, height=1216)
                content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
                path = service._write_generated(f'{condition}-{seed}.png', content)
                row['pictures'].append({'seed': seed, 'path': str(path), 'elapsed_s': elapsed})
                save(root, report)
            row['status'] = '生成完了'
        report['status'] = '全条件の生成完了・目視評価待ち'
        save(root, report)
    except Exception as error:
        report.update(status='処理失敗', error=str(error))
        save(root, report)
        raise
    finally:
        await service.comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--recover-trained', choices=('ok_only', 'local'))
    parser.add_argument('--evaluate-trained', type=Path)
    asyncio.run(main(parser.parse_args()))
