"""学習器から独立して、保存済みLoRAの実体と変更箇所を読み取る。"""
import hashlib
import json
from pathlib import Path
import torch
from safetensors import safe_open
from safetensors.torch import load_file

root = Path('C:/Users/kite_/ComfyUI/ComfyUI')
source = root / 'models/loras/ndac1de01_97404490.safetensors'
torch.set_num_threads(4)
original = load_file(source)
result = {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'files': []}
for name in ['owner', 'collar', 'layout']:
    path = root / ('models/loras/ng-generalization-training-20260907-' + name + '.safetensors')
    state = load_file(path)
    with safe_open(path, framework='pt') as f:
        metadata = f.metadata()
    receipt = json.loads(path.with_suffix('.json').read_text())
    row = {'name': name, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
           'bytes': path.stat().st_size, 'metadata': metadata, 'keys_equal': state.keys() == original.keys(),
           'source_hash_matches_receipt': receipt['source_sha256'] == result['source_sha256'],
           'tensors': [], 'effective_updates': []}
    for key, value in state.items():
        old = original[key].float()
        diff = value.float() - old
        row['tensors'].append({'key': key, 'dtype': str(value.dtype), 'source_dtype': str(original[key].dtype),
            'shape': list(value.shape), 'changed': int(torch.count_nonzero(diff)),
            'squared_delta': float(diff.square().sum()), 'max_abs_delta': float(diff.abs().max())})
        if key.endswith('.lora_down.weight'):
            prefix = key.removesuffix('.lora_down.weight')
            up = prefix + '.lora_up.weight'
            rank = value.shape[0]
            scale = float(state[prefix + '.alpha']) / rank * .8
            old_scale = float(original[prefix + '.alpha']) / rank * .8
            current = state[up].float() @ value.float() * scale
            previous = original[up].float() @ old * old_scale
            d = current - previous
            row['effective_updates'].append({'key': prefix, 'changed': int(torch.count_nonzero(d)),
                'squared_delta': float(d.square().sum()), 'max_abs_delta': float(d.abs().max()),
                'relative_l2': float(d.norm() / previous.norm())})
    result['files'].append(row)
    print(json.dumps({k:v for k,v in row.items() if k not in ['tensors','effective_updates']},ensure_ascii=False), flush=True)
out = Path('C:/sf/ng-generalization-weight-audit-20260907.json')
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
for path, start, stop in [('comfy/sd.py','def load_lora_for_models','def '),('comfy/lora.py','def model_lora_keys_unet','def '),('nodes.py','class LoraLoader:', 'class LoraLoaderModelOnly')]:
    text = (root / path).read_text(encoding='utf-8')
    begin = text.index(start)
    end = text.find('\n' + stop, begin + len(start))
    print('\nSOURCE ' + path + '\n' + text[begin:end if end >= 0 else None], flush=True)
