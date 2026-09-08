import pytest
from backend import workflows

@pytest.mark.parametrize("graph", [workflows.anima_txt2img("mage",1,lora_name="anima_joy_sprite_lora.safetensors",pose_image="p1_pose_casting_skeleton.png"), workflows.joy_edit("p1_edit_firemage_front.png","turn",2), workflows.toonout("p1_edit_firemage_front.png"), workflows.sam3_mask("p1_edit_firemage_front.png")])
def test_four_builders_are_comfy_graphs(graph):
    assert graph and all(isinstance(x["class_type"],str) and isinstance(x["inputs"],dict) for x in graph.values())
    assert any(x["class_type"]=="SaveImage" for x in graph.values())

def test_optional_anima_and_joy_inputs():
    graph=workflows.anima_txt2img("m",3,turbo=True,lora_name="x",pose_image="p",width=768,height=1024)
    assert graph["1"]["inputs"]["unet_name"]=="anima-turbo-v1.1.safetensors"
    assert graph["8"]["class_type"]=="AnimaControlApply"
    assert graph["22"]["inputs"]["width"]==768
    assert workflows.joy_edit(["a","b"],"p",4)["20"]["inputs"]["images.image1"]==["11",0] and "images" not in workflows.joy_edit(["a","b"],"p",4)["20"]["inputs"]
    with pytest.raises(ValueError): workflows.joy_edit([str(x) for x in range(7)],"p",4)

def test_observed_toonout_and_sam3_names():
    assert workflows.toonout("a")["2"]["inputs"]["model"]=="BiRefNet_toonout"
    assert workflows.sam3_mask("a","robe",'[{"x":1,"y":2}]')["4"]["inputs"]["positive_coords"]=='[{"x":1,"y":2}]'


def test_anima_refine_is_img2img_with_lora():
    graph = workflows.anima_refine("draft.png", "bell_idol, waving", 3, lora_name="bell.safetensors", denoise=0.4)
    assert graph["23"]["inputs"]["latent_image"] == ["11", 0] and graph["23"]["inputs"]["denoise"] == 0.4
    assert graph["11"]["inputs"]["pixels"] == ["10", 0] and graph["4"]["inputs"]["lora_name"] == "bell.safetensors"
    assert graph["20"]["inputs"]["clip"] == ["4", 1] and graph["23"]["inputs"]["model"] == ["4", 0]


def test_anima_txt2img_stacks_loras_in_order():
    graph = workflows.anima_txt2img("p", 1, loras=[("char.safetensors", 0.8), ("style.safetensors", 0.6)])
    assert graph["4"]["inputs"]["lora_name"] == "char.safetensors" and graph["40"]["inputs"]["lora_name"] == "style.safetensors"
    assert graph["40"]["inputs"]["model"] == ["4", 0] and graph["40"]["inputs"]["strength_model"] == 0.6
    assert graph["23"]["inputs"]["model"] == ["40", 0] and graph["20"]["inputs"]["clip"] == ["40", 1]


def test_qwen_vl_interpret_uses_32b_4bit_without_video():
    text = workflows.qwen_vl_interpret("hello")
    qwen = text["2"]["inputs"]
    assert qwen["model_name"] == "Qwen3-VL-32B-Instruct"
    assert qwen["quantization"] == "4-bit (VRAM-friendly)"
    assert qwen["max_tokens"] == 1024
    assert qwen["video_frame_size"] == "auto"
    assert qwen["keep_model_loaded"] is False
    assert qwen["custom_prompt"] == "hello"
    assert "video" not in qwen
    assert "1" not in text
    with_image = workflows.qwen_vl_interpret("hello", image="a.png", keep_model_loaded=True)
    assert with_image["1"]["class_type"] == "LoadImage"
    assert with_image["1"]["inputs"]["image"] == "a.png"
    assert with_image["2"]["inputs"]["image"] == ["1", 0]
    assert with_image["2"]["inputs"]["keep_model_loaded"] is True
    assert "video" not in with_image["2"]["inputs"]
