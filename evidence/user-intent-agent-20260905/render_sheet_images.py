"""全比較画像へ親の観察と実解釈を併記する。生成処理は呼ばない。"""
import argparse
from html import escape
import json

from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--interpretation", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observations = json.loads(args.observations.read_text())
    notes = '<aside><h2>確認結果</h2><p>' + escape(observations["summary"]) + '</p><ul>'
    notes += ''.join('<li>' + escape(item) + '</li>' for item in observations["observations"]) + '</ul></aside>'
    source = args.comparison.read_text().replace('</h1>', '</h1>' + notes, 1)
    records = ''.join('<details><summary>構成・注文の実解釈記録</summary><pre>' +
                      escape(json.dumps(json.loads(path.read_text()), ensure_ascii=False, indent=2)) +
                      '</pre></details>' for path in args.interpretation)
    args.output.write_text(source.replace('</html>', records + '</html>'), encoding="utf-8")


if __name__ == "__main__":
    main()
