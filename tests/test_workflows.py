from __future__ import annotations

import pytest

from backend import workflows


@pytest.mark.parametrize(
    ("builder", "args", "output_prefix"),
    [
        (workflows.anima_base, ("fire mage", 42), "sprite-forge/base"),
        (workflows.joy_edit, ("hero.png", "turn left", 43), "sprite-forge/edit"),
        (workflows.toonout, ("hero.png",), "sprite-forge/matte"),
        (workflows.damage, ("hero.png", "torn robe", 44), "sprite-forge/damage"),
    ],
)
def test_accepted_workflow_builders_return_json_graphs(builder, args, output_prefix):
    graph = builder(*args)

    assert isinstance(graph, dict)
    assert graph
    assert all(isinstance(node["class_type"], str) and isinstance(node["inputs"], dict)
               for node in graph.values())
    saved = [node for node in graph.values() if node["class_type"] == "SaveImage"]
    assert len(saved) == 1
    assert saved[0]["inputs"]["filename_prefix"] == output_prefix


def test_anima_base_uses_requested_dimensions_and_seed():
    graph = workflows.anima_base("full body mage", 99, width=768, height=1024)

    assert graph["5"]["inputs"] == {"width": 768, "height": 1024, "batch_size": 1}
    assert graph["6"]["inputs"]["seed"] == 99
    assert graph["6"]["inputs"]["latent_image"] == ["5", 0]


def test_damage_restores_only_the_clothing_mask():
    graph = workflows.damage("hero.png", "battle damaged robe", 123)

    composite = graph["11"]
    assert composite["class_type"] == "ImageCompositeMasked"
    assert composite["inputs"]["destination"] == ["1", 0]
    assert composite["inputs"]["source"] == ["10", 0]
    assert composite["inputs"]["mask"] == ["4", 0]
