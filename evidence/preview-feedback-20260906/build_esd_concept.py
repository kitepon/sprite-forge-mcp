"""正の差がある髪型属性を削除せず、一つのESD入力文にする。"""
import argparse
import json
from pathlib import Path


def build(weights):
    strengths = {}
    for image in weights['images']:
        for feature in image['features']:
            if feature['weight'] > 0:
                strengths[feature['tag']] = max(strengths.get(feature['tag'], 0), feature['weight'])
    tags = sorted(strengths, key=lambda tag: (-strengths[tag], tag))
    return 'Hairstyle with the following features: ' + ', '.join(tag.replace('_', ' ') for tag in tags) + '.'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('weights', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(build(json.loads(args.weights.read_text())) + '\n')
