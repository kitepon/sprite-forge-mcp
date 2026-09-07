"""同じノイズと時刻で得たOK／NGのflow誤差を比較する。"""


def flow_errors(prediction, target, spatial_mask=None):
    squared = (prediction.float() - target.float()).square()
    if spatial_mask is None:
        return squared.flatten(1).mean(1)
    return (squared * spatial_mask).flatten(1).sum(1) / (spatial_mask.sum() * squared.shape[1])


def preference_loss(policy_errors, reference_errors, beta):
    import torch.nn.functional as functional

    improvement = reference_errors.detach() - policy_errors
    margin = beta / 2 * (improvement[0] - improvement[1])
    return -functional.logsigmoid(margin)
