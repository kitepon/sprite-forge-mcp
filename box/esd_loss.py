"""属性を避けるESD教師信号。画像のOK／NG対は使わない。"""


def erasure_target(subject_prediction, erase_prediction, empty_prediction, strength):
    return subject_prediction - strength * (erase_prediction - empty_prediction)


def weighted_erasure_delta(predictions, empty_prediction):
    return sum(weight * (prediction - empty_prediction) for weight, prediction in predictions)
