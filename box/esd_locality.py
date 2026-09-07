"""凍結Animaの注意から空間重みを求め、対象外の予測変化を計測する。"""


def token_positions(sequence, phrase):
    """token列に存在する句だけを位置へ変換する。"""
    positions = [i + j for i in range(len(sequence) - len(phrase) + 1)
                 if sequence[i:i + len(phrase)] == phrase for j in range(len(phrase))]
    if not phrase or not positions:
        raise ValueError('定位する句がAnimaの条件token列に存在しません。')
    return positions


def outside_preservation_loss(prediction, reference, spatial_weight):
    outside = 1 - spatial_weight
    return ((prediction - reference).square() * outside).sum() / (outside.sum() * prediction.shape[1])


def capture_spatial_weight(model, predict, latent, timestep, condition, positions):
    """通常の順伝播を変えず、全DiT blockのcross-attentionを観測する。"""
    import torch
    import torch.nn.functional as F
    maps, handles = [], []

    def capture(module, args, kwargs):
        q, k, _ = module.compute_qkv(args[0], context=args[2])
        scores = torch.einsum('bqhd,bkhd->bhqk', q.float(), k.float()) * module.head_dim ** -0.5
        maps.append(scores.softmax(-1)[..., positions].sum(-1).mean(1))

    try:
        for block in model.blocks:
            handles.append(block.cross_attn.register_forward_pre_hook(capture, with_kwargs=True))
        with torch.no_grad():
            predict(latent, timestep, condition)
    finally:
        for handle in handles:
            handle.remove()
    attention = torch.stack(maps).mean(0)
    height, width = latent.shape[-2:]
    attention = attention.reshape(latent.shape[0], 1, height // model.patch_spatial, width // model.patch_spatial)
    # 二値閾値を置かず、注意の最大値を1として連続的に対象外の重みを付ける。
    attention = attention / attention.amax(dim=(-2, -1), keepdim=True)
    return F.interpolate(attention, size=(height, width), mode='bilinear', align_corners=False).detach()
