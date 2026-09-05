"""前回の条件から人物・顔だけを新しい実解釈へ差し替え、比較画像を作る。"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import httpx


def main(args):
    original = json.loads((args.baseline / "intent.json").read_text())
    baseline = json.loads((args.baseline / "job.json").read_text())
    interpreted = json.loads((args.output / "result.json").read_text())["proposal"]
    revised = deepcopy(original["accepted"])
    revised["changes"] = [c for c in revised["changes"] if c["feature"] not in ("face", "subject")]
    revised["changes"] += [c for c in interpreted["changes"] if c["feature"] in ("face", "subject")]
    with httpx.Client(base_url=args.url, timeout=180) as client:
        def post(endpoint, **kwargs):
            response = client.post(endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        # 実CLIの結果を使う自由文による診断。通常画面での採用操作と区別して記録する。
        new_face = next(c["description_en"] for c in interpreted["changes"] if c["feature"] == "face")
        new_subject = next(c["description_en"] for c in interpreted["changes"] if c["feature"] == "subject")
        old_face = original["effective_conditions"]["face"]["description_en"]
        prompt = baseline["intent_positive"].replace(old_face, new_subject + ", " + new_face)
        job = post("/api/from-bible", params={"name": original["name"], "prompt": prompt,
                   "seed": baseline["seed"], "style": ""})
        (args.output / "generation.json").write_text(json.dumps({"job": job, "source_intent": original["job_id"],
                     "new_interpretation": interpreted, "changes": revised["changes"]}, ensure_ascii=False, indent=2))
        print(json.dumps(job, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", required=True)
    main(parser.parse_args())
