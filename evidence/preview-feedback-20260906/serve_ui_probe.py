"""隔離した実機画像でWebUIを確認する。GPUとCLI呼出しだけfixtureにする。"""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
root = Path('.cache/preview-ui').resolve()
for path in root.rglob('*.json'):
    path.write_text(path.read_text().replace('/home/kite/sprite-forge-mcp/.cache/preview-feedback-pipeline', str(root)))
os.environ['SPRITEFORGE_CACHE'] = str(root)

from backend import app as module, box
from tests.test_style import ComfyFixture
from starlette.responses import HTMLResponse
from starlette.routing import Route
import uvicorn

image = next((root / 'generated').glob('*preview-0.png')).read_bytes()
async def view(_image):
    return image
async def copied(*args, **kwargs):
    return 0, ''
async def trained(*args, **kwargs):
    yield '{"step":20,"total":20,"loss":0.69}'
async def metrics(remote, local, **kwargs):
    local.write_text('{"ui_fixture":true}')
    return 0, ''
async def interpreted(packet, images):
    if packet['review_input']['comment'] == '衣装は合っている':
        return {'fix': [], 'preserve': ['衣装'], 'questions': ['NGなのはどの部分ですか？']}
    return {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': []}
module.services.comfy = ComfyFixture()
module.services._view = view
module.services.intent_interpreter = interpreted
box.copy_tree_to_box = copied
box.stream_preference_training = trained
box.copy_from_box = metrics

async def page(request):
    return HTMLResponse('''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/style.css"><title>プレビュー操作の検証</title>
<main style="max-width:1100px;margin:20px auto;padding:16px"><h1>プレビュー操作の検証</h1><p>隔離した台帳と実機の画像を使用。学習操作は画面試験用です。</p><div id="probe"></div><p id="next"></p></main><div id="notice"></div>
<script type="module">import {previewGallery} from '/preview.js?v=studio-2';import {startJobUpdates} from '/jobs.js?v=studio-2';
startJobUpdates();await previewGallery(document.querySelector('#probe'),'LoRA修正・実機検証','',[],()=>{},()=>{document.querySelector('#next').textContent='選んだLoRAを採用し、設定画へ進みました';});</script></html>''')
module.app.router.routes.insert(0, Route('/preview-probe', page))
uvicorn.run(module.app, host='127.0.0.1', port=8877)
