"""同じノイズと時刻で得たOK／NGのflow誤差を比較する。"""


def preference_loss(policy_errors, reference_errors, beta):
    import torch.nn.functional as functional

    improvement = reference_errors.detach() - policy_errors
    margin = beta / 2 * (improvement[0] - improvement[1])
    return -functional.logsigmoid(margin)
