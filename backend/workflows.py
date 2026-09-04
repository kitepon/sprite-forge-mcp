"""ComfyUI graphs with node contracts observed from fox /object_info."""
from __future__ import annotations
from typing import Any

Graph = dict[str, dict[str, Any]]


def anima_txt2img(prompt: str, seed: int, *, turbo: bool = False, lora_name: str | None = None,
                  lora_strength: float = .8, pose_image: str | None = None,
                  width: int = 1024, height: int = 1024) -> Graph:
    graph: Graph = {
        "1": {"class_type":"UNETLoader","inputs":{"unet_name":"anima-turbo-v1.1.safetensors" if turbo else "anima-base-v1.0.safetensors","weight_dtype":"default"}},
        "2": {"class_type":"CLIPLoader","inputs":{"clip_name":"qwen_3_06b_base.safetensors","type":"qwen_image"}},
        "3": {"class_type":"VAELoader","inputs":{"vae_name":"qwen_image_vae.safetensors"}},
    }
    model, clip = ["1", 0], ["2", 0]
    if lora_name:
        graph["4"]={"class_type":"LoraLoader","inputs":{"model":model,"clip":clip,"lora_name":lora_name,"strength_model":lora_strength,"strength_clip":lora_strength}}
        model, clip = ["4",0], ["4",1]
    if pose_image:
        graph.update({
            "5":{"class_type":"LoadImage","inputs":{"image":pose_image}},
            "6":{"class_type":"AnimaPoseControl","inputs":{"image":["5",0],"style":"R0_thin","hands":True,"face":True,"feet":True,"redetect":True,"resolution":min(width,height),"pose_json":""}},
            "7":{"class_type":"VAEEncode","inputs":{"pixels":["6",0],"vae":["3",0]}},
            "8":{"class_type":"AnimaControlApply","inputs":{"model":model,"control_latent":["7",0],"control_embedder_path":"anima_pose_preview2.safetensors","strength":1.0}},
        }); model=["8",0]
    graph.update({
        "20":{"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":clip}},
        "21":{"class_type":"CLIPTextEncode","inputs":{"text":"","clip":clip}},
        "22":{"class_type":"EmptyLatentImage","inputs":{"width":width,"height":height,"batch_size":1}},
        "23":{"class_type":"KSampler","inputs":{"model":model,"seed":seed,"steps":4 if turbo else 28,"cfg":1.0 if turbo else 4.0,"sampler_name":"euler","scheduler":"simple","positive":["20",0],"negative":["21",0],"latent_image":["22",0],"denoise":1.0}},
        "24":{"class_type":"VAEDecode","inputs":{"samples":["23",0],"vae":["3",0]}},
        "25":{"class_type":"SaveImage","inputs":{"images":["24",0],"filename_prefix":"sprite-forge/anima"}},
    }); return graph


def joy_edit(images: list[str] | str, prompt: str, seed: int, *, negative: str = "",
             size: tuple[int, int] | None = None) -> Graph:
    """JoyAI edit. ``size`` picks an empty latent of that size; otherwise the output follows image 1."""
    names = [images] if isinstance(images, str) else images
    if not 1 <= len(names) <= 6: raise ValueError("JoyAI requires one to six reference images")
    graph: Graph = {
        "1":{"class_type":"UNETLoader","inputs":{"unet_name":"joyai_image_edit_plus_int8_convrot.safetensors","weight_dtype":"default"}},
        "2":{"class_type":"CLIPLoader","inputs":{"clip_name":"qwen3vl_8b_joyimage_edit_plus_int8_convrot.safetensors","type":"joyimage"}},
        "3":{"class_type":"VAELoader","inputs":{"vae_name":"wan_2.1_vae.safetensors"}},
    }
    refs={}
    for i,name in enumerate(names,10): graph[str(i)]={"class_type":"LoadImage","inputs":{"image":name}}; refs[f"image{i-9}"]=[str(i),0]
    graph.update({
        "20":{"class_type":"TextEncodeJoyImageEdit","inputs":{"clip":["2",0],"vae":["3",0],"prompt":prompt,"images":refs}},
        "21":{"class_type":"TextEncodeJoyImageEdit","inputs":{"clip":["2",0],"vae":["3",0],"prompt":negative,"images":refs}},
        "22":{"class_type":"EmptySD3LatentImage","inputs":{"width":size[0],"height":size[1],"batch_size":1}} if size else {"class_type":"VAEEncode","inputs":{"pixels":["10",0],"vae":["3",0]}},
        "23":{"class_type":"KSampler","inputs":{"model":["1",0],"seed":seed,"steps":30,"cfg":4.0,"sampler_name":"euler","scheduler":"normal","positive":["20",0],"negative":["21",0],"latent_image":["22",0],"denoise":1.0}},
        "24":{"class_type":"VAEDecode","inputs":{"samples":["23",0],"vae":["3",0]}},
        "25":{"class_type":"SaveImage","inputs":{"images":["24",0],"filename_prefix":"sprite-forge/joy-edit"}},
    }); return graph


def toonout(image_name: str) -> Graph:
    return {"1":{"class_type":"LoadImage","inputs":{"image":image_name}},"2":{"class_type":"BiRefNetRMBG","inputs":{"image":["1",0],"model":"BiRefNet_toonout","sensitivity":1.0,"mask_blur":0,"mask_offset":0,"invert_output":False,"refine_foreground":False,"background":"Alpha","background_color":"#222222"}},"3":{"class_type":"SaveImage","inputs":{"images":["2",0],"filename_prefix":"sprite-forge/toonout"}}}


def sam3_mask(image_name: str, prompt: str = "character", points: str | None = None) -> Graph:
    detect: dict[str, Any]={"model":["1",0],"image":["3",0],"threshold":.5,"refine_iterations":2,"individual_masks":False,"conditioning":["2",0]}
    if points: detect["positive_coords"]=points
    return {"1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":"sam3.1_multiplex_fp16.safetensors"}},"2":{"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":["1",1]}},"3":{"class_type":"LoadImage","inputs":{"image":image_name}},"4":{"class_type":"SAM3_Detect","inputs":detect},"5":{"class_type":"MaskToImage","inputs":{"mask":["4",0]}},"6":{"class_type":"SaveImage","inputs":{"images":["5",0],"filename_prefix":"sprite-forge/sam3-mask"}}}


def anima_base(prompt: str, seed: int, width: int = 1024, height: int = 1024) -> Graph:
    return anima_txt2img(prompt, seed, width=width, height=height)
