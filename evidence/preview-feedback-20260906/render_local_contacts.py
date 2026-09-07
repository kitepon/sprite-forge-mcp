"""生成済み全画像をseed付き一覧に配置する。画像の内容は修正しない。"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


def render(root, conditions=('before', 'ok_only', 'local')):
    for condition in conditions:
        paths = sorted((root / 'generated').glob(f'{condition}-*.png'))
        if not paths:
            continue
        sheet = Image.new('RGB', (2080, ((len(paths) + 4) // 5) * 638), 'white')
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(paths):
            left, top = (index % 5) * 416, (index // 5) * 638
            with Image.open(path) as image:
                sheet.paste(ImageOps.contain(image.convert('RGB'), (416, 608)), (left, top + 30))
            draw.text((left + 8, top + 6), path.stem, fill='black', font_size=20)
        sheet.save(root / f'{condition}-contact.jpg')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--conditions', nargs='+', default=['before', 'ok_only', 'local'])
    args = parser.parse_args()
    render(args.root, args.conditions)
