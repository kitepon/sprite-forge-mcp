"""本番の既存台帳を保存し、新規の確認用キャラクターだけを作る。"""
import argparse
import json
from pathlib import Path

import httpx


def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.url, timeout=30) as client:
        def call(method, endpoint, **params):
            response = client.request(method, endpoint, params=params)
            response.raise_for_status()
            return response.json()
        characters = call("GET", "/api/characters")
        styles = call("GET", "/api/styles")
        if any(item["name"] == args.target for item in characters):
            raise ValueError("確認用の名前が既に存在します。上書きしません。")
        source = next(item for item in characters if item["name"] == args.source)
        (args.output / "before.json").write_text(json.dumps({"characters": characters, "styles": styles}, ensure_ascii=False, indent=2))
        record = call("POST", "/api/characters", name=args.target, char_desc=source["char_desc"],
                      attr=source.get("attr", ""), trigger=source["trigger"], lora_name=source["lora_name"])
        record = call("POST", f"/api/characters/{record['key']}/samples",
                      images=source["samples"][args.sample]["path"], captions=source["samples"][args.sample].get("caption", ""))
        (args.output / "fixture.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(json.dumps({"name":record["name"], "key":record["key"], "samples":len(record["samples"])}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
