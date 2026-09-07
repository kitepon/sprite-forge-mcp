"""ComfyUI内でAnimeTimmの全属性スコアを返す実測用ノード。"""
import csv
import json
from pathlib import Path
import time


def pad_picture(picture, size, background_color):
    from PIL import Image

    width, height = size
    ratio = min(width / picture.width, height / picture.height)
    scaled = picture.resize((round(picture.width * ratio), round(picture.height * ratio)), Image.Resampling.BILINEAR)
    canvas = Image.new('RGB', (width, height), background_color)
    canvas.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
    return canvas


def preprocess(picture, specification):
    from torchvision import transforms

    pad, resize, crop, tensor, normalize = specification
    if [step['type'] for step in specification] != ['pad_to_size', 'resize', 'center_crop', 'maybe_to_tensor', 'normalize']:
        raise ValueError('未対応のモデル前処理です。')
    if pad['interpolation'] != 'bilinear':
        raise ValueError('未対応の余白処理です。')
    picture = pad_picture(picture, pad['size'], pad['background_color'])
    return transforms.Compose([
        transforms.Resize(resize['size'], interpolation=transforms.InterpolationMode(resize['interpolation']),
                          max_size=resize['max_size'], antialias=resize['antialias']),
        transforms.CenterCrop(crop['size']), transforms.ToTensor(),
        transforms.Normalize(normalize['mean'], normalize['std']),
    ])(picture)


class SpriteAnimeTimm:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('IMAGE',)}}

    RETURN_TYPES = ('STRING',)
    FUNCTION = 'analyze'
    CATEGORY = 'SpriteForge/解析'

    def analyze(self, image):
        import folder_paths
        import numpy as np
        from PIL import Image
        import torch
        import timm
        from safetensors.torch import load_file

        root = Path(folder_paths.models_dir) / 'animetimm/convnextv2_huge.dbv4-full'
        config = json.loads((root / 'config.json').read_text(encoding='utf-8'))
        with (root / 'selected_tags.csv').open(encoding='utf-8', newline='') as source:
            tags = list(csv.DictReader(source))
        specification = json.loads((root / 'preprocess.json').read_text(encoding='utf-8'))['test']
        started = time.monotonic()
        model = timm.create_model(config['architecture'], pretrained=False, num_classes=len(tags))
        model.load_state_dict(load_file(str(root / 'model.safetensors')), strict=True)
        model = model.eval().to('cuda')
        torch.cuda.reset_peak_memory_stats()
        results = []
        with torch.inference_mode():
            for frame in image:
                picture = Image.fromarray(np.rint(frame.cpu().numpy() * 255).clip(0, 255).astype(np.uint8))
                inputs = preprocess(picture, specification).unsqueeze(0).to('cuda')
                scores = model(inputs).sigmoid()[0].cpu().tolist()
                results.append({tag['name']: score for tag, score in zip(tags, scores, strict=True)})
        output = {'model': 'animetimm/convnextv2_huge.dbv4-full',
                  'revision': '18177355d1448a69bafb0410a0608e144f714e8b',
                  'elapsed_s': round(time.monotonic() - started, 3),
                  'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                  'scores': results}
        return (json.dumps(output, ensure_ascii=False),)


NODE_CLASS_MAPPINGS = {'SpriteAnimeTimm': SpriteAnimeTimm}
NODE_DISPLAY_NAME_MAPPINGS = {'SpriteAnimeTimm': 'AnimeTimm 全属性解析'}
