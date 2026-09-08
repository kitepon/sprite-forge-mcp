"""同じノイズと時刻で得たOK／NGのflow誤差を比較する。"""


def spatial_errors(prediction, target, mask=None):
    """画素ごとの二乗誤差。mask があるときはマスク内の加重平均。空マスクは落とさない。"""
    squared = (prediction.float() - target.float()).square()
    if mask is None:
        return squared.flatten(1).mean(1)
    weights = mask.float().expand_as(squared)
    denom = weights.flatten(1).sum(1)
    if (denom <= 0).any():
        raise ValueError('マスクが空です')
    return (squared * weights).flatten(1).sum(1) / denom


def preference_loss(policy_errors, reference_errors, beta):
    import torch.nn.functional as functional

    improvement = reference_errors.detach() - policy_errors
    margin = beta / 2 * (improvement[0] - improvement[1])
    return -functional.logsigmoid(margin)
