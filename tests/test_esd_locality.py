import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from box.esd_locality import token_positions, outside_preservation_loss, capture_spatial_weight


def test_localization_token_must_exist_without_matching_padding():
    assert token_positions([9, 2, 3, 1, 0, 0], [2, 3]) == [1, 2]
    with pytest.raises(ValueError):
        token_positions([9, 1, 0], [2, 3])


def test_preservation_penalizes_outside_without_training_on_target_region():
    torch = pytest.importorskip('torch')
    value = torch.tensor([[[[9., 2.]]]], requires_grad=True)
    reference = torch.zeros_like(value)
    weight = torch.tensor([[[[1., 0.]]]])
    loss = outside_preservation_loss(value, reference, weight)
    assert loss.item() == pytest.approx(4.)
    loss.backward()
    assert value.grad.tolist() == [[[[0., 4.]]]]


def test_attention_capture_observes_without_changing_prediction_or_leaving_hooks():
    torch = pytest.importorskip('torch')
    from types import SimpleNamespace

    class Attention(torch.nn.Module):
        head_dim = 1

        def compute_qkv(self, x, context):
            return x, context, context

        def forward(self, x, attn_params, context):
            return x + context.mean()

    attention = Attention()
    model = SimpleNamespace(blocks=[SimpleNamespace(cross_attn=attention)], patch_spatial=1)
    latent = torch.zeros(1, 1, 1, 2)
    context = torch.tensor([[[[3.]], [[-3.]]]])
    queries = torch.tensor([[[[1.]], [[-1.]]]])

    def predict(*args):
        return attention(queries, None, context)

    before = predict()
    weight = capture_spatial_weight(model, predict, latent, None, None, [0])
    assert torch.equal(before, predict())
    assert not attention._forward_pre_hooks
    assert weight.shape == latent.shape
    assert weight[0, 0, 0, 0] == 1
    assert weight[0, 0, 0, 1] < .01
