"""Transfer ownership and worker lifetime, without GPU work or real SSH."""
import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from backend import box
from backend.events import EventStore
from backend.services import Services

spec = importlib.util.spec_from_file_location("spriteforge_staging", Path(__file__).parents[1] / "box/staging.py")
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


@pytest.fixture
def stage(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "ROOT", tmp_path / "staging")
    identity = str(uuid.uuid4())
    path = Path(staging.prepare(identity)["path"])
    (path / "dataset").mkdir()
    (path / "dataset/sample.png").write_bytes(b"transferred copy")
    return identity, path


@pytest.mark.parametrize("exit_code", [0, 7])
def test_worker_terminal_exit_reclaims_only_stage(stage, tmp_path, exit_code):
    identity, path = stage
    source = tmp_path / "source.png"
    source.write_bytes(b"unique original")
    other_id = str(uuid.uuid4())
    other = Path(staging.prepare(other_id)["path"])
    lora = tmp_path / "result.safetensors"
    staging.transition(identity, "prepared", "launching")
    code = "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'LoRA'); sys.exit(int(sys.argv[2]))"
    assert staging.run(identity, [sys.executable, "-c", code, str(lora), str(exit_code)], tmp_path) == exit_code
    assert not path.exists()
    assert source.read_bytes() == b"unique original"
    assert lora.read_bytes() == b"LoRA"
    assert other.is_dir()


@pytest.mark.parametrize("status", ["launching", "running", "unknown"])
def test_worker_alive_or_unknown_is_preserved(stage, status):
    identity, path = stage
    with staging.locked():
        staging.save(identity, status)
    assert staging.clean(identity) == {"status": "retained_unknown", "stage_state": status}
    assert (path / "dataset/sample.png").is_file()


def test_interrupted_parent_does_not_claim_worker_exit(stage, tmp_path, monkeypatch):
    identity, path = stage
    staging.transition(identity, "prepared", "launching")
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(staging.subprocess, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        staging.run(identity, ["worker"], tmp_path)
    assert staging.clean(identity)["status"] == "retained_unknown"
    assert path.exists()


def test_partial_transfer_is_reclaimed_and_cleanup_is_idempotent(stage):
    identity, path = stage
    assert staging.clean(identity)["status"] == "removed"
    assert staging.clean(identity)["status"] == "absent"
    assert not path.exists()


def test_wrong_marker_and_symlink_cannot_delete_unique_data(stage, tmp_path):
    identity, path = stage
    unique = tmp_path / "unique"
    unique.mkdir()
    (unique / "original.png").write_bytes(b"keep")
    (path / "link").symlink_to(unique, target_is_directory=True)
    with pytest.raises(ValueError, match="link"):
        staging.clean(identity)
    (path / "link").unlink()
    (path / ".spriteforge-stage.json").write_text(json.dumps({"schema": 1, "job_id": "other", "status": "prepared"}))
    with pytest.raises(ValueError, match="ownership"):
        staging.clean(identity)
    assert (unique / "original.png").read_bytes() == b"keep"


def test_invalid_stage_and_external_config_are_rejected(stage, tmp_path):
    identity, path = stage
    with pytest.raises(ValueError):
        staging.prepare("../unique")
    with pytest.raises(ValueError, match="config"):
        staging.validate_config(identity, tmp_path / "unique.toml")
    staging.validate_config(identity, path / "dataset.toml")


def test_global_lifecycle_lock_prevents_concurrent_transitions(stage):
    identity, path = stage
    with staging.locked():
        with pytest.raises(OSError):
            staging.clean(identity)
    assert path.exists()


def test_service_keeps_failure_log_and_cleans_transfer(stage, tmp_path, monkeypatch):
    # Exercise the production service boundary against the real filesystem owner.
    identity, path = stage
    staging.clean(identity)
    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    service = Services(events=events, generated_root=tmp_path / "generated")
    dataset = tmp_path / "dataset_test"
    dataset.mkdir()
    (dataset / "000.png").write_bytes(b"frozen original")
    job = {"job_id": identity, "kind": "lora_train", "status": "queued", "images": 1,
           "steps": 1, "progress": {"step": 0, "total": 1}, "lora_name": "test.safetensors"}
    async def command(action, stage_id, **kwargs):
        return staging.prepare(stage_id) if action == "prepare" else staging.clean(stage_id)
    async def copy(local, remote, **kwargs):
        return 0, ""
    async def worker(*args, **kwargs):
        staging.transition(identity, "prepared", "launching")
        staging.transition(identity, "launching", "running")
        yield "failure evidence from actual worker"
        staging.transition(identity, "running", "finished")
        raise RuntimeError("worker failed")
    class Client:
        async def post(self, *args, **kwargs):
            return None
    service.comfy = type("Comfy", (), {"client": Client(), "base_url": "http://fixture"})()
    monkeypatch.setattr(box, "stage_command", command)
    monkeypatch.setattr(box, "copy_tree_to_box", copy)
    monkeypatch.setattr(box, "copy_to_box", copy)
    monkeypatch.setattr(box, "stream_training", worker)
    async def exercise():
        with service._job_errors(job):
            await service._execute_training(job, dataset, "test", "unused", 1)
    with pytest.raises(RuntimeError, match="worker failed"):
        asyncio.run(exercise())
    assert events.load_job(identity)["status"] == "failed"
    assert events.load_job(identity)["remote_stage_cleanup"]["status"] == "removed"
    assert "failure evidence" in (tmp_path / "generated" / f"{identity}-train.log").read_text()
    assert (dataset / "000.png").read_bytes() == b"frozen original"
    assert not path.exists()


def test_startup_retries_terminal_stage_but_does_not_touch_active_job(stage, tmp_path, monkeypatch):
    identity, path = stage
    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    events.save_job({"job_id": identity, "status": "failed", "remote_stage_id": identity})
    events.save_job({"job_id": "active", "status": "running", "remote_stage_id": "active"})
    calls = []
    async def command(action, stage_id, **kwargs):
        calls.append((action, stage_id))
        return staging.clean(stage_id)
    monkeypatch.setattr(box, "stage_command", command)
    asyncio.run(Services(events=events).recover_training_stages())
    assert calls == [("clean", identity)]
    assert not path.exists()
    assert events.load_job("active")["status"] == "running"


def test_cancelled_transfer_remains_unknown_after_startup_recovery(stage, tmp_path, monkeypatch):
    identity, path = stage
    staging.clean(identity)
    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    service = Services(events=events)
    job = {"job_id": identity, "kind": "lora_train", "status": "running"}
    calls = []

    async def command(action, stage_id, **kwargs):
        calls.append(action)
        return staging.prepare(stage_id) if action == "prepare" else staging.clean(stage_id)

    monkeypatch.setattr(box, "stage_command", command)

    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            async with service._training_stage(job):
                assert events.load_job(identity)["remote_stage_cleanup"]["status"] == "retained_unknown"
                (path / "partial.png").write_bytes(b"writer lifetime unknown")
                raise asyncio.CancelledError
        assert events.load_job(identity)["remote_stage_cleanup"]["status"] == "retained_unknown"
        # Startup can mark the orphan failed without proving its SCP writer ended.
        job["status"] = "failed"
        events.save_job(job)
        await Services(events=events).recover_training_stages()
        with pytest.raises(ValueError, match="lifetime is still unknown"):
            async with Services(events=events)._training_stage(events.load_job(identity)):
                pytest.fail("an unknown writer must not be replaced")

    asyncio.run(exercise())
    assert calls == ["prepare"]
    assert staging.state(identity)["status"] == "prepared"
    assert (path / "partial.png").read_bytes() == b"writer lifetime unknown"
    assert events.load_job(identity)["remote_stage_cleanup"]["status"] == "retained_unknown"


def test_box_launch_fences_before_starting_ssh(monkeypatch):
    calls = []
    async def stage_command(action, identity, **kwargs):
        calls.append((action, identity))
        return {"status": "launching"}
    async def create(*args, **kwargs):
        assert calls == [("launch", "job-id")]
        assert args[-2:] == ("--stage-id", "job-id")
        raise OSError("SSH launch outcome unknown")
    monkeypatch.setattr(box, "stage_command", stage_command)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    async def exercise():
        async for _ in box.stream_training("config", "test", "model", "qwen", "vae", 1, "loras", stage_id="job-id"):
            pass
    with pytest.raises(OSError, match="unknown"):
        asyncio.run(exercise())


@pytest.mark.parametrize("saves_lora", [False, True])
def test_training_entrypoint_checks_saved_output_and_reclaims_stage(stage, tmp_path, monkeypatch, saves_lora):
    identity, path = stage
    config = path / "dataset.toml"
    config.write_text("training fixture")
    staging.transition(identity, "prepared", "launching")
    spec = importlib.util.spec_from_file_location("spriteforge_train", Path(__file__).parents[1] / "box/train.py")
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)
    monkeypatch.setitem(sys.modules, "staging", staging)
    monkeypatch.setattr(sys, "argv", ["train.py", "--dataset-config", str(config), "--stage-id", identity,
                                      "--output-name", "test", "--output-dir", str(tmp_path)])
    script = "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'LoRA')" if saves_lora else "pass"
    monkeypatch.setattr(trainer, "training_command", lambda args: ([sys.executable, "-c", script, str(tmp_path / "test.safetensors")], tmp_path))
    if saves_lora:
        assert trainer.main() == 0
        assert (tmp_path / "test.safetensors").read_bytes() == b"LoRA"
    else:
        with pytest.raises(RuntimeError, match="without saving"):
            trainer.main()
    assert not path.exists()
