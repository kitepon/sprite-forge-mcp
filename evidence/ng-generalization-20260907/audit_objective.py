"""保存済みLoRAが学習目標へ近づいたか、固定した未使用入力で測る。再学習しない。"""
import gc
import hashlib
import json
from pathlib import Path
import sys
import argparse
import torch
from safetensors.torch import load_file

sys.path.insert(0, 'C:/sd-scripts')
from library import anima_utils, strategy_anima
from networks import lora_anima

device, dtype = 'cuda', torch.bfloat16
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seed', type=int, default=904)
args = parser.parse_args()
torch.set_num_threads(4)
groups = ['owner', 'collar', 'layout']
inputs = {g:json.loads(Path('C:/sf/ng-generalization-training-20260907-' + g + '/input.json').read_text(encoding='utf-8')) for g in groups}
data = inputs['owner']
torch.manual_seed(data['seed'])
tokenizer = strategy_anima.AnimaTokenizeStrategy(qwen3_path=data['qwen3'])
encoder, _ = anima_utils.load_qwen3_text_encoder(data['qwen3'], dtype=dtype, device='cpu')
model = anima_utils.load_anima_model(torch.device(device), data['model'], 'torch', False, torch.device('cpu'), torch.float32, False)
model.requires_grad_(False)
weights = load_file(data['lora'])
reference, _ = lora_anima.create_network_from_weights(data['strength'], None, None, [encoder], model, weights_sd=weights)
policy, _ = lora_anima.create_network_from_weights(0, None, None, [encoder], model, weights_sd=weights)
for adapter in [reference, policy]:
    adapter.apply_to([encoder], model)
    adapter.load_state_dict(weights, strict=True)
    adapter.to(device).requires_grad_(False)
encoder.to(device).eval().requires_grad_(False)
texts = list(dict.fromkeys([data['prompt'], '', *[c for g in groups for c in inputs[g]['erase_concepts']]]))
conditions = {}
with torch.no_grad(), torch.autocast('cuda', dtype=dtype):
    for text in texts:
        conditions[text] = [v.to(device) for v in strategy_anima.AnimaTextEncodingStrategy().encode_tokens(tokenizer, [encoder], tokenizer.tokenize([text]))]
encoder.to('cpu')
del encoder, tokenizer
gc.collect()
torch.cuda.empty_cache()
model.to(device).eval()

@torch.no_grad()
def predict(latent, t, text):
    prompt, mask, tokens, token_mask = conditions[text]
    with torch.autocast('cuda', dtype=dtype):
        return model(latent.unsqueeze(2).to(dtype), t, prompt,
            padding_mask=torch.zeros(1, 1, *latent.shape[-2:], device=device, dtype=dtype),
            target_input_ids=tokens, target_attention_mask=token_mask, source_attention_mask=mask).squeeze(2).float()

torch.manual_seed(args.seed)
latent = torch.randn(data['latent_shape'], device=device)
grid = torch.linspace(1, 0, data['sampling_steps'] + 1, device=device)
probes = []
for index in range(data['sampling_steps']):
    t = grid[index:index+1]
    before = predict(latent, t, data['prompt'])
    empty = predict(latent, t, '')
    if index in [0,2,4,6]:
        targets = {text: -(predict(latent, t, text) - empty) for text in texts if text not in [data['prompt'], '']}
        probes.append((latent.clone(), t.clone(), before.clone(), targets))
    latent += (grid[index+1] - grid[index]) * (empty + data['sampling_cfg'] * (before-empty))

reference.set_multiplier(0)
policy.set_multiplier(data['strength'])
branch_error = max(float((predict(x,t,data['prompt'])-before).abs().max()) for x,t,before,targets in probes)
result = {'seed':args.seed, 'training_performed':False, 'same_weights_branch_max_error':branch_error, 'rows':[], 'files':{}}
for group in groups:
    path = Path(data['lora']).parent / ('ng-generalization-training-20260907-' + group + '.safetensors')
    result['files'][group] = {'path':str(path), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    policy.load_state_dict(load_file(path), strict=True)
    for x,t,before,targets in probes:
        change = predict(x,t,data['prompt']) - before
        for concept in inputs[group]['erase_concepts']:
            direction = targets[concept] * inputs[group]['negative_guidance']
            before_error = direction.square().mean()
            after_error = (change-direction).square().mean()
            dot = (change*direction).sum()
            row = {'group':group, 'timestep':float(t.item()), 'concept':concept,
                'before_error':float(before_error), 'after_error':float(after_error),
                'error_ratio':float(after_error/before_error),
                'cosine':float(dot/(change.norm()*direction.norm())),
                'target_fraction':float(dot/direction.square().sum()),
                'change_to_target_norm':float(change.norm()/direction.norm())}
            result['rows'].append(row)
    selected=[r for r in result['rows'] if r['group']==group]
    print(json.dumps({'group':group,'closer':sum(r['error_ratio']<1 for r in selected),'total':len(selected),
        'ratios':[round(r['error_ratio'],4) for r in selected], 'branch_max_error':branch_error}), flush=True)
Path(f'C:/sf/ng-objective-audit-20260907-{args.seed}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
