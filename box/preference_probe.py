"""foxで一組のOK／NGから既存LoRAを修正する成立確認。画質の合格は判定しない。"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time

from preference_loss import preference_loss


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sd-scripts', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=1)
    parser.add_argument('--learning-rate', type=float, default=1e-5)
    parser.add_argument('--beta', type=float, default=1.0)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    if args.output.resolve() == Path(data['lora']).resolve():
        raise ValueError('試作の出力には元LoRAと異なるパスを指定してください。')
    sys.path.insert(0, str(args.sd_scripts))
    import numpy as np
    from PIL import Image
    import torch
    from safetensors.torch import load_file
    from library import anima_utils, anima_train_utils, strategy_anima
    from networks import lora_anima

    started = time.monotonic()
    torch.manual_seed(data['seed'])
    device, dtype = 'cuda', torch.bfloat16
    source_sha = hashlib.sha256(Path(data['lora']).read_bytes()).hexdigest()
    tokenizer = strategy_anima.AnimaTokenizeStrategy(qwen3_path=data['qwen3'])
    encoder, _ = anima_utils.load_qwen3_text_encoder(data['qwen3'], dtype=dtype, device='cpu')
    model = anima_utils.load_anima_model(
        torch.device(device), data['model'], 'torch', False, torch.device('cpu'), torch.float32, False)
    model.requires_grad_(False).train()
    model.enable_gradient_checkpointing()
    weights = load_file(data['lora'])
    reference, _ = lora_anima.create_network_from_weights(
        data['strength'], None, None, [encoder], model, weights_sd=weights)
    policy, _ = lora_anima.create_network_from_weights(
        0, None, None, [encoder], model, weights_sd=weights)
    for adapter in (reference, policy):
        adapter.apply_to([encoder], model)
        adapter.load_state_dict(weights, strict=True)
        adapter.to(device)
    reference.requires_grad_(False)
    policy.requires_grad_(True)
    # 元LoRAのテキスト重みは双方で保持し、追加学習はDiTだけ行う。
    for layer in policy.text_encoder_loras:
        layer.requires_grad_(False)
    encoder.to(device).eval().requires_grad_(False)
    with torch.no_grad(), torch.autocast('cuda', dtype=dtype):
        conditions = strategy_anima.AnimaTextEncodingStrategy().encode_tokens(
            tokenizer, [encoder], tokenizer.tokenize([data['prompt']] * 2))
        conditions = [value.to(device) for value in conditions]
    encoder.to('cpu')
    del encoder, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    vae = anima_train_utils.load_qwen_image_vae(
        argparse.Namespace(vae=data['vae'], vae_chunk_size=None, vae_disable_cache=False),
        device='cpu', disable_mmap=True)
    vae.to(device, dtype=dtype).eval().requires_grad_(False)
    pixels = []
    for key in ('ok', 'ng'):
        with Image.open(data[key]) as source:
            picture = source.convert('RGB').resize(tuple(data['size']), Image.Resampling.LANCZOS)
            pixels.append(torch.from_numpy(np.array(picture)).permute(2, 0, 1).float() / 127.5 - 1)
    with torch.no_grad():
        latents = vae.encode_pixels_to_latents(torch.stack(pixels).to(device, dtype=dtype))
    del vae, pixels
    gc.collect()
    torch.cuda.empty_cache()
    model.to(device)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=args.learning_rate, weight_decay=0)
    prompt, mask, tokens, token_mask = conditions

    def predict(noisy, times):
        with torch.autocast('cuda', dtype=dtype):
            return model(
                noisy.unsqueeze(2), times, prompt,
                padding_mask=torch.zeros(noisy.shape[0], 1, *noisy.shape[-2:], device=device, dtype=dtype),
                target_input_ids=tokens, target_attention_mask=token_mask, source_attention_mask=mask,
            ).squeeze(2)

    def errors(prediction, target):
        return (prediction.float() - target.float()).square().flatten(1).mean(1)

    torch.cuda.reset_peak_memory_stats()
    rows = []
    for step in range(args.steps):
        # OK／NGと固定基準・更新対象で同じ時刻とノイズを使う。
        noise = torch.randn_like(latents[:1]).expand_as(latents)
        times = torch.rand(1, device=device).expand(2)
        sigma = times[:, None, None, None]
        noisy = ((1 - sigma) * latents + sigma * noise).to(dtype)
        target = noise - latents
        reference.set_multiplier(data['strength'])
        policy.set_multiplier(0)
        with torch.no_grad():
            fixed_errors = errors(predict(noisy, times), target)
        reference.set_multiplier(0)
        policy.set_multiplier(data['strength'])
        optimizer.zero_grad(set_to_none=True)
        model_errors = errors(predict(noisy.detach().requires_grad_(True), times), target)
        loss = preference_loss(model_errors, fixed_errors, args.beta)
        loss.backward()
        gradient_norm = torch.stack([p.grad.float().square().sum() for p in policy.parameters() if p.grad is not None]).sum().sqrt()
        if not torch.isfinite(loss) or not torch.isfinite(gradient_norm):
            raise RuntimeError('学習の損失または勾配が非有限値になりました。')
        optimizer.step()
        row = {'step': step + 1, 'loss': loss.item(), 'gradient_norm': gradient_norm.item(),
               'policy_errors': model_errors.detach().tolist(), 'reference_errors': fixed_errors.tolist()}
        rows.append(row)
        print(json.dumps(row), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    policy.save_weights(str(args.output), torch.float32, {'spriteforge_source_sha256': source_sha})
    saved = load_file(str(args.output))
    delta = sum((saved[k].float() - weights[k].float()).square().sum().item() for k in saved)
    reference_unchanged = all(torch.equal(value.cpu(), weights[key]) for key, value in reference.state_dict().items())
    model.eval()
    with torch.no_grad():
        before_reload = predict(noisy, times)
        policy.load_state_dict(saved, strict=True)
        reload_error = (before_reload - predict(noisy, times)).abs().max().item()
    result = {'steps': rows, 'source_sha256': source_sha, 'lora_delta_squared': delta,
              'reference_unchanged': reference_unchanged, 'reload_max_error': reload_error,
              'elapsed_seconds': time.monotonic() - started,
              'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
              'input': data, 'learning_rate': args.learning_rate, 'beta': args.beta,
              'output': str(args.output)}
    args.output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('lora_delta_squared', 'reference_unchanged', 'reload_max_error', 'elapsed_seconds', 'peak_allocated_bytes')}), flush=True)


if __name__ == '__main__':
    main()
