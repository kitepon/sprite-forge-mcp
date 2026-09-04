"""Pure JSON builders for the four accepted Phase 1 paths."""
from __future__ import annotations
from typing import Any


def anima_base(prompt: str, seed: int, width: int = 1024, height: int = 1024) -> dict[str, Any]:
    return {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "anima_base_v1.0.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_06b_base.safetensors", "type": "anima"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["4", 0], "latent_image": ["5", 0], "seed": seed, "steps": 28, "cfg": 4, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "sprite-forge/base"}}}


def joy_edit(image_name: str, prompt: str, seed: int) -> dict[str, Any]:
    return {"1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "joyai_image_edit_plus_int8.safetensors", "weight_dtype": "default"}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_8b_joyimage_edit.safetensors", "type": "joyai"}},
            "4": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
            "5": {"class_type": "TextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
            "6": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["5", 0], "negative": ["5", 0], "latent_image": ["1", 0], "seed": seed, "steps": 30, "cfg": 4, "sampler_name": "euler", "scheduler": "normal", "denoise": 1}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["4", 0]}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "sprite-forge/edit"}}}


def toonout(image_name: str) -> dict[str, Any]:
    return {"1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
            "2": {"class_type": "BiRefNetRMBG", "inputs": {"image": ["1", 0], "model": "BiRefNet_toonout"}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "sprite-forge/matte"}}}


def damage(image_name: str, prompt: str, seed: int) -> dict[str, Any]:
    """SAM clothing selection + JoyAI edit + base restoration outside the mask."""
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sam3.1_multiplex_fp16.safetensors"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "clothing", "clip": ["2", 1]}},
        "4": {"class_type": "SAM3_Detect", "inputs": {"model": ["2", 0], "image": ["1", 0], "conditioning": ["3", 0], "threshold": 0.45, "refine_iterations": 2, "individual_masks": False}},
        "5": {"class_type": "UNETLoader", "inputs": {"unet_name": "joyai_image_edit_plus_int8.safetensors", "weight_dtype": "default"}},
        "6": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_8b_joyimage_edit.safetensors", "type": "joyai"}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "8": {"class_type": "TextEncode", "inputs": {"text": prompt, "clip": ["6", 0]}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["5", 0], "positive": ["8", 0], "negative": ["8", 0], "latent_image": ["1", 0], "seed": seed, "steps": 30, "cfg": 4, "sampler_name": "euler", "scheduler": "normal", "denoise": 1}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["7", 0]}},
        "11": {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["1", 0], "source": ["10", 0], "mask": ["4", 0], "x": 0, "y": 0, "resize_source": False}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "sprite-forge/damage"}},
    }
