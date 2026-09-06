"""比較実験専用。製品の学習器と同じ条件でOK画像の通常損失だけを使う。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preference_train


def ok_loss(policy_errors, reference_errors, beta):
    return policy_errors[0]


if __name__ == '__main__':
    preference_train.preference_loss = ok_loss
    preference_train.main()
