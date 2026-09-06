"""成立試作のLoRAを、製品と同じComfyUIグラフで単独読込みする。"""
import argparse
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path.cwd()))
from backend.workflows import anima_txt2img

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('action', choices=['submit', 'collect'])
parser.add_argument('--url', required=True)
parser.add_argument('--directory', type=Path, required=True)
args = parser.parse_args()
directory = args.directory


def request(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    with urlopen(Request(args.url + path, data=body, headers={'Content-Type': 'application/json'}), timeout=60) as response:
        return response.read()


if args.action == 'submit':
    data = json.loads((directory / 'sprite-preference-input.json').read_text())
    graph = anima_txt2img(data['prompt'], 37, lora_name='spriteforge-preference-probe.safetensors',
                         lora_strength=data['strength'], width=416, height=608, negative=data['negative'])
    graph['25']['inputs']['filename_prefix'] = 'sprite-forge/preference-probe'
    result = json.loads(request('/prompt', {'prompt': graph, 'client_id': 'spriteforge-preference-probe'}))
    (directory / 'comfy-submit.json').write_text(json.dumps({'workflow': graph, 'response': result}, indent=2))
    print(json.dumps(result))
else:
    submitted = json.loads((directory / 'comfy-submit.json').read_text())
    prompt_id = submitted['response']['prompt_id']
    result = json.loads(request('/history/' + prompt_id))
    (directory / 'comfy-history.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
