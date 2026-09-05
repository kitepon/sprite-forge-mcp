"""画像別コメントの本番確認用台帳を新規作成する。既存素材は読取りだけ。"""
import argparse
import json
from pathlib import Path
from urllib.parse import quote
import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--name", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
with httpx.Client(base_url="http://192.168.1.2:8766", timeout=180) as client:
    def call(method, endpoint, **kwargs):
        response = client.request(method, endpoint, **kwargs)
        response.raise_for_status()
        return response.json()
    records = call("GET", "/api/characters")
    assert not any(r["name"] == args.name for r in records)
    original = next(r for r in records if r["name"] == "ベル")
    original = call("GET", f"/api/characters/{quote(original['key'])}")
    record = call("POST", "/api/characters", params={"name": args.name, "char_desc": original["char_desc"],
                  "trigger": original["trigger"], "lora_name": original["lora_name"]})
    call("POST", f"/api/characters/{quote(record['key'])}/samples", params={
        "images": ",".join(s["path"] for s in original["samples"]),
        "captions": "|この画像の顔立ちを強く採用してほしい||この画像の体格・頭身と服装を強く採用してほしい"})
    draft = call("POST", "/api/intents/drafts", json={"name": args.name, "kind": "character", "stage": "samples", "comment": ""})
    job = call("POST", f"/api/intents/{draft['job_id']}/interpret")
    (args.output / "intent.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))
    assert original == call("GET", f"/api/characters/{quote(original['key'])}")
    print(json.dumps({"job_id": job["job_id"], "name": args.name, "status": job["status"],
                      "changes": job.get("proposal", {}).get("changes"), "questions": job.get("proposal", {}).get("questions")}, ensure_ascii=False))
