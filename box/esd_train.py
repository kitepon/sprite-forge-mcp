"""Animaの既存LoRAをESDの属性除去で更新する実証入口。"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time

from esd_loss import erasure_target, weighted_erasure_delta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sd-scripts', required=True)
    parser.add_argument('--localize-only', action='store_true')
    parser.add_argument('--diagnostics', type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    if args.output.resolve() == Path(data['lora']).resolve() or args.output.exists():
        raise ValueError('出力には未使用のLoRAパスが必要です。')
    sys.path.insert(0, args.sd_scripts)
    import torch
    from safetensors.torch import load_file, save_file
    from library import anima_utils, strategy_anima
    from networks import lora_anima

    started = time.monotonic()
    torch.manual_seed(data['seed'])
    device, dtype = 'cuda', torch.bfloat16
    source_sha = hashlib.sha256(Path(data['lora']).read_bytes()).hexdigest()
    tokenizer = strategy_anima.AnimaTokenizeStrategy(qwen3_path=data['qwen3'])
    encoder, _ = anima_utils.load_qwen3_text_encoder(data['qwen3'], dtype=dtype, device='cpu')
    model = anima_utils.load_anima_model(torch.device(device), data['model'], 'torch', False,
                                         torch.device('cpu'), torch.float32, False)
    model.requires_grad_(False)
    model.enable_gradient_checkpointing()
    weights = load_file(data['lora'])
    reference, _ = lora_anima.create_network_from_weights(data['strength'], None, None, [encoder], model, weights_sd=weights)
    policy, _ = lora_anima.create_network_from_weights(0, None, None, [encoder], model, weights_sd=weights)
    for adapter in (reference, policy):
        adapter.apply_to([encoder], model)
        adapter.load_state_dict(weights, strict=True)
        adapter.to(device)
    reference.requires_grad_(False)
    policy.requires_grad_(True)
    for layer in policy.text_encoder_loras:
        layer.requires_grad_(False)
    encoder.to(device).eval().requires_grad_(False)
    feature_images = data.get('feature_weights', {}).get('images', [])
    feature_tags = sorted({feature['tag'] for image in feature_images for feature in image['features']})
    erase_concepts = data.get('erase_concepts', [data['erase_concept']])
    locality = data.get('locality')
    texts = [data['prompt'], erase_concepts[0], '', *[tag.replace('_', ' ') for tag in feature_tags], *erase_concepts[1:]]
    erase_indices = [1, *range(3 + len(feature_tags), len(texts))]
    if locality:
        from esd_locality import token_positions, capture_spatial_weight, outside_preservation_loss
        texts.append(data['prompt'] + ', ' + locality['phrase'])
    conditions = []
    with torch.no_grad(), torch.autocast('cuda', dtype=dtype):
        for text in texts:
            encoded = strategy_anima.AnimaTextEncodingStrategy().encode_tokens(
                tokenizer, [encoder], tokenizer.tokenize([text]))
            conditions.append([value.to(device) for value in encoded])
    if locality:
        phrase_ids = tokenizer.t5_tokenizer(locality['phrase'], add_special_tokens=False)['input_ids']
        positions = token_positions(conditions[-1][2][0].tolist(), phrase_ids)
        if args.diagnostics is None:
            raise ValueError('空間保持の実験には診断出力先が必要です。')
        args.diagnostics.mkdir(parents=True, exist_ok=True)
        # 画像への復号はComfyUIで行い、ここでは公式の潜在形式へ戻して保存する。
        sys.path.insert(0, str(Path(data['lora']).parents[2]))
        from comfy.latent_formats import Wan21
        latent_format = Wan21()
    encoder.to('cpu')
    del encoder, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    model.to(device)
    optimizer = torch.optim.AdamW([param for param in policy.parameters() if param.requires_grad],
                                  lr=data['learning_rate'], weight_decay=0)

    def predict(latents, timestep, condition):
        prompt, mask, tokens, token_mask = condition
        with torch.autocast('cuda', dtype=dtype):
            return model(latents.unsqueeze(2).to(dtype), timestep, prompt,
                         padding_mask=torch.zeros(1, 1, *latents.shape[-2:], device=device, dtype=dtype),
                         target_input_ids=tokens, target_attention_mask=token_mask,
                         source_attention_mask=mask).squeeze(2)

    rows = []
    torch.cuda.reset_peak_memory_stats()
    for step in range(len(erase_concepts) if args.localize_only else data['steps']):
        reference.set_multiplier(data['strength'])
        policy.set_multiplier(0)
        model.eval()
        grid = torch.linspace(1, 0, data['sampling_steps'] + 1, device=device)
        stop = torch.randint(data['sampling_steps'], (1,)).item()
        latent = torch.randn(data['latent_shape'], device=device)
        with torch.no_grad():
            for index in range(stop):
                timestep = grid[index:index + 1]
                subject = predict(latent, timestep, conditions[0]).float()
                empty = predict(latent, timestep, conditions[2]).float()
                velocity = empty + data['sampling_cfg'] * (subject - empty)
                latent = latent + (grid[index + 1] - grid[index]) * velocity
            timestep = grid[stop:stop + 1]
            subject = predict(latent, timestep, conditions[0]).float()
            empty = predict(latent, timestep, conditions[2]).float()
            if feature_images:
                feature_image = feature_images[step % len(feature_images)]
                delta = weighted_erasure_delta(
                    ((feature['weight'], predict(latent, timestep,
                       conditions[3 + feature_tags.index(feature['tag'])]).float())
                     for feature in feature_image['features']), empty)
                erase = empty + delta
            else:
                erase = predict(latent, timestep, conditions[erase_indices[step % len(erase_indices)]]).float()
            target = erasure_target(subject, erase, empty, data['negative_guidance']).detach()
            if locality:
                complete = latent.clone()
                for index in range(stop, data['sampling_steps']):
                    if index == data['sampling_steps'] - 1:
                        mask_latent = complete.clone()
                    full_subject = predict(complete, grid[index:index + 1], conditions[0]).float()
                    full_empty = predict(complete, grid[index:index + 1], conditions[2]).float()
                    complete += (grid[index + 1] - grid[index]) * (full_empty + data['sampling_cfg'] * (full_subject - full_empty))
                spatial_weight = capture_spatial_weight(model, predict, mask_latent, grid[-2:-1], conditions[-1], positions)
                diagnostic = args.diagnostics / f'step-{step + 1:03}'
                save_file({'latent_tensor': latent_format.process_out(complete.unsqueeze(2)).cpu().contiguous(),
                           'latent_format_version_0': torch.tensor(0)}, str(diagnostic.with_suffix('.latent')))
                save_file({'weight': spatial_weight.cpu()}, str(diagnostic.with_suffix('.safetensors')))
                from PIL import Image
                Image.fromarray((spatial_weight[0, 0].cpu().numpy() * 255).round().astype('uint8')).save(diagnostic.with_suffix('.png'))
                if args.localize_only:
                    rows.append({'step': step + 1, 'concept': erase_concepts[step % len(erase_concepts)],
                                 'timestep': timestep.item(), 'diagnostic': str(diagnostic),
                                 'spatial_weight_mean': spatial_weight.mean().item(), 'positions': positions})
                    continue
        reference.set_multiplier(0)
        policy.set_multiplier(data['strength'])
        model.train()
        optimizer.zero_grad(set_to_none=True)
        prediction = predict(latent.detach().requires_grad_(True), timestep, conditions[0]).float()
        erase_loss = (prediction - target).square().mean()
        preserve_loss = outside_preservation_loss(prediction, subject, spatial_weight) if locality else prediction.new_zeros(())
        loss = erase_loss + (locality['weight'] if locality else 0) * preserve_loss
        loss.backward()
        gradient = torch.stack([param.grad.float().square().sum() for param in policy.parameters()
                                if param.grad is not None]).sum().sqrt()
        if not torch.isfinite(loss) or not torch.isfinite(gradient):
            raise RuntimeError('ESDの損失または勾配が非有限です。')
        optimizer.step()
        row = {'step': step + 1, 'loss': loss.item(), 'gradient_norm': gradient.item(),
               'timestep': timestep.item(), 'concept_delta_mse': (erase - empty).square().mean().item()}
        rows.append(row)
        if locality:
            row.update(erase_loss=erase_loss.item(), preserve_loss=preserve_loss.item(),
                       concept=erase_concepts[step % len(erase_concepts)], spatial_weight_mean=spatial_weight.mean().item())
        if feature_images:
            row['ng_number'] = feature_image['number']
            row['feature_count'] = len(feature_image['features'])
            row['weight_sum'] = sum(feature['weight'] for feature in feature_image['features'])
        print(json.dumps(row), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.localize_only:
        result = {'input': data, 'steps': rows, 'training_performed': False,
                  'source_file_unchanged': source_sha == hashlib.sha256(Path(data['lora']).read_bytes()).hexdigest(),
                  'reference_unchanged': all(torch.equal(value.cpu(), weights[key]) for key, value in reference.state_dict().items()),
                  'elapsed_seconds': time.monotonic() - started}
        args.output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    policy.save_weights(str(args.output), torch.float32, {'spriteforge_source_sha256': source_sha, 'objective': 'esd'})
    saved = load_file(str(args.output))
    model.eval()
    with torch.no_grad():
        original = predict(latent, timestep, conditions[0])
        policy.load_state_dict(saved, strict=True)
        reload_error = (original - predict(latent, timestep, conditions[0])).abs().max().item()
    result = {'input': data, 'steps': rows, 'source_sha256': source_sha,
              'source_file_unchanged': source_sha == hashlib.sha256(Path(data['lora']).read_bytes()).hexdigest(),
              'reference_unchanged': all(torch.equal(value.cpu(), weights[key]) for key, value in reference.state_dict().items()),
              'lora_delta_squared': sum((saved[key].float() - weights[key].float()).square().sum().item() for key in saved),
              'reload_max_error': reload_error, 'elapsed_seconds': time.monotonic() - started,
              'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'output': str(args.output)}
    args.output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'saved': str(args.output), 'reload_max_error': reload_error}), flush=True)


if __name__ == '__main__':
    main()
