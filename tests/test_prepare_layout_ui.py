"""保存済み実応答の再配置は、確定や生成の代わりにしない。"""
import asyncio
from copy import deepcopy

from scripts.prepare_layout_ui import prepare
from tests.test_layout_intent import proposal
from tests.test_style import make, png


def test_prepare_retains_pending_proposal_and_remaps_references(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        from backend.sheet_layout import legacy_layout
        image = tmp_path / "reference.png"
        image.write_bytes(png())
        reference = {"record_key": "original", "sample_index": 7, "path": "/original/image.png"}
        native = {"job_id": "source-job", "stage": "layout", "record_description": "she/her",
                  "original_comment": "同じ顔と衣装で二方向", "sheet_layout": legacy_layout(),
                  "references": [reference], "proposal": proposal(legacy_layout()),
                  "interpreter": {"model": "fixture", "auth": "fixture", "elapsed_seconds": 0}}
        native["proposal"]["panels"][0]["reference"] = reference
        before = deepcopy(native)
        original = {"name": "確認用", "trigger": "source_trigger", "lora_name": "source.safetensors"}
        job = await prepare(service, original, native, [image])
        assert native == before
        assert job["status"] == "awaiting_confirmation"
        assert job["proposal"]["panels"][0]["reference"] == job["references"][0]
        assert job["probe_replay"]["source_job_id"] == native["job_id"]
        assert await service.get_sheet_layout(original["name"]) == native["sheet_layout"]
        record = await service.character_info(original["name"])
        assert record["trigger"] == original["trigger"] and record["lora_name"] == original["lora_name"]
        assert not record.get("bible") and not comfy.submitted

    asyncio.run(scenario())
