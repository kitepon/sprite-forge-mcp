"""登録の削除は、素材・作品・共有LoRAを削除しない。"""
import asyncio
import json
from pathlib import Path
import pytest
from tests.test_style import make, png


def test_delete_character_keeps_assets_and_other_records(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        source = tmp_path / "source.png"
        source.write_bytes(png())
        await service.create_character("削除対象", "人物", lora_name="shared.safetensors")
        await service.create_character("保持対象", "人物", lora_name="shared.safetensors")
        original = await service.add_samples("削除対象", str(source))
        result = await service.delete_character(original["key"])
        assert [r["name"] for r in await service.list_characters()] == ["保持対象"]
        assert source.is_file() and Path(original["samples"][0]["path"]).is_file()
        assert json.loads(Path(result["backup_path"]).read_text()) == original
        assert (await service.character_info("保持対象"))["lora_name"] == "shared.safetensors"
        with pytest.raises(FileNotFoundError):
            await service.character_info("削除対象")
    asyncio.run(scenario())


def test_delete_character_refuses_active_work(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await service.create_character("probe", "人物")
        service.events.save_job({"job_id": "running", "name": "probe", "status": "running"})
        with pytest.raises(ValueError, match="処理中"):
            await service.delete_character("probe")
        assert len(await service.list_characters()) == 1
    asyncio.run(scenario())
