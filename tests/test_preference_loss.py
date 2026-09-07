"""GPU学習環境のPyTorchで実行する、選好更新の方向と固定基準の試験。"""
import math
import importlib.util
import unittest

if importlib.util.find_spec('torch') is not None:
    import torch

from box.preference_loss import flow_errors, preference_loss


@unittest.skipUnless(importlib.util.find_spec('torch'), 'PyTorchを持つGPU学習環境で実行する')
class PreferenceLossTest(unittest.TestCase):
    def test_mask_excludes_other_regions_and_normalizes_channels(self):
        prediction = torch.tensor([[[[2., 100.]], [[2., 100.]]]], requires_grad=True)
        target = torch.zeros_like(prediction)
        mask = torch.tensor([[[[1., 0.]]]])
        loss = flow_errors(prediction, target, mask)
        self.assertEqual(loss.item(), 4.)
        loss.sum().backward()
        self.assertTrue(torch.equal(prediction.grad[..., 1], torch.zeros_like(prediction.grad[..., 1])))
        self.assertTrue(torch.equal(flow_errors(prediction, target), flow_errors(prediction, target, torch.ones_like(mask))))

    def test_common_soft_mask_keeps_each_pair_error_separate(self):
        prediction = torch.tensor([[[[2., 4.]]], [[[1., 3.]]]])
        mask = torch.tensor([[[[.5, 1.]]]])
        result = flow_errors(prediction, torch.zeros_like(prediction), mask)
        self.assertTrue(torch.allclose(result, torch.tensor([12., 9.5 / 1.5])))

    def test_updates_both_labels_without_training_reference(self):
        policy = torch.tensor([1., 1.], requires_grad=True)
        reference = torch.tensor([1., 1.], requires_grad=True)
        loss = preference_loss(policy, reference, 1.)
        self.assertAlmostEqual(loss.item(), math.log(2), places=6)
        loss.backward()
        self.assertGreater(policy.grad[0].item(), 0)
        self.assertLess(policy.grad[1].item(), 0)
        self.assertIsNone(reference.grad)
        updated = policy.detach() - .1 * policy.grad
        self.assertLess(preference_loss(updated, reference, 1.).item(), loss.item())

    def test_swapping_labels_reverses_the_update(self):
        policy = torch.tensor([.8, 1.2], requires_grad=True)
        reference = torch.tensor([1., 1.])
        original = preference_loss(policy, reference, 1.)
        swapped = preference_loss(policy.flip(0), reference.flip(0), 1.)
        self.assertGreater(swapped.item(), original.item())
        swapped.backward()
        self.assertLess(policy.grad[0].item(), 0)
        self.assertGreater(policy.grad[1].item(), 0)


if __name__ == '__main__':
    unittest.main()
