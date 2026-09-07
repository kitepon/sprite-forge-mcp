"""実機ComfyUIの読込み関数で、各LoRAの対応と適用値をCPU上で確認する。"""
import hashlib
import json
from pathlib import Path
import sys
import shutil

root = Path('C:/Users/kite_/ComfyUI/ComfyUI')
sys.path.insert(0, str(root))
sys.argv = [sys.argv[0], '--cpu']
import torch
import comfy.sd
import comfy.lora
import comfy.utils
import folder_paths

torch.set_num_threads(4)
model = comfy.sd.load_diffusion_model(str(root / 'models/diffusion_models/anima-base-v1.0.safetensors'))
mapping = comfy.lora.model_lora_keys_unet(model.model, {})
source = 'ndac1de01_97404490.safetensors'
rows = []
original = None
for name, filename in [('before', source)] + [(x, 'ng-generalization-training-20260907-' + x + '.safetensors') for x in ['owner','collar','layout']]:
    path = folder_paths.get_full_path_or_raise('loras', filename)
    state = comfy.utils.load_torch_file(path, safe_load=True)
    patched, _ = comfy.sd.load_lora_for_models(model, None, state, .8, .8)
    keys = [k for k in state if k.startswith('lora_unet_') and k.endswith('.lora_down.weight')]
    missing = [k for k in keys if mapping.get(k.removesuffix('.lora_down.weight')) not in patched.patches]
    row = {'name':name, 'resolved_path':path, 'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
           'unet_modules':len(keys), 'patches':len(patched.patches), 'unmapped_unet':missing,
           'applied_layers':[]}
    if name == 'before':
        original = patched
    else:
        for k in sorted(patched.patches):
            base = model.model.state_dict()[k].float()
            old = comfy.lora.calculate_weight(original.patches[k], base.clone(), k)
            new = comfy.lora.calculate_weight(patched.patches[k], base.clone(), k)
            delta = new - old
            row['applied_layers'].append({'key':k, 'squared_delta':float(delta.square().sum()),
                'changed':int(torch.count_nonzero(delta)),
                'changed_after_bfloat16':int(torch.count_nonzero(new.bfloat16() != old.bfloat16()))})
    rows.append(row)
    print(json.dumps({k:v for k,v in row.items() if k != 'applied_layers'}), flush=True)
    if name in ['before','owner']:
        copy = Path(path).parent / ('ng-load-audit-20260907-' + name + '.safetensors')
        if copy.exists():
            raise FileExistsError(copy)
        shutil.copyfile(path, copy)
Path('C:/sf/ng-comfy-audit-20260907.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
