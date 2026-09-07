"""別名の同一LoRAを実サーバーで再読込みし、過去の生成画像と照合する。"""
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from PIL import Image, ImageChops, ImageStat
import io

api = 'http://192.168.1.11:8188'
root = Path('.cache/ng-load-audit-20260907')
root.mkdir(exist_ok=True)
source = Path('.cache/ng-generalization-training-20260907/generated')
rows = []
for name in ['before', 'owner']:
    old = Image.open(source / (name + '-601.png'))
    graph = json.loads(old.info['prompt'])
    graph['4']['inputs']['lora_name'] = 'ng-load-audit-20260907-' + name + '.safetensors'
    graph['25']['inputs']['filename_prefix'] = 'sprite-forge/ng-load-audit-' + name
    with urlopen(Request(api + '/prompt', data=json.dumps({'prompt':graph}).encode(), headers={'Content-Type':'application/json'}), timeout=15) as f:
        receipt = json.load(f)
    pid = receipt['prompt_id']
    (root / (name + '-submitted.json')).write_text(json.dumps(receipt))
    started = time.monotonic()
    while True:
        with urlopen(api + '/history/' + pid, timeout=15) as f:
            history = json.load(f)
        if pid in history:
            record = history[pid]
            break
        if time.monotonic() - started > 180:
            raise TimeoutError('生成は停止していません。保存済みprompt_idの履歴を確認してください。')
        time.sleep(2)
    if record['status']['status_str'] != 'success':
        raise RuntimeError(record['status'])
    image = record['outputs']['25']['images'][0]
    with urlopen(api + '/view?' + urlencode(image), timeout=15) as f:
        raw = f.read()
    (root / (name + '-601.png')).write_bytes(raw)
    diff = ImageChops.difference(old.convert('RGB'), Image.open(io.BytesIO(raw)).convert('RGB'))
    row = {'name':name, 'prompt_id':pid, 'pixel_identical':diff.getbbox() is None,
           'pixel_mae':sum(ImageStat.Stat(diff).mean)/3, 'history':record}
    rows.append(row)
    print(json.dumps({k:v for k,v in row.items() if k != 'history'}), flush=True)
    (root / 'generation.json').write_text(json.dumps(rows, indent=2))
