"""本人OKの生成だけを教材へ足す。NGは混ぜない。"""
import importlib.util
from pathlib import Path

_PROBE = Path(__file__).resolve().parents[1] / "evidence/ng-remake-20260907/ok_materials.py"
_spec = importlib.util.spec_from_file_location("ok_materials", _PROBE)
ok_materials = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ok_materials)


def test_add_ok_materials_copies_six_user_ok_images(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    for role, seed in ok_materials.USER_OK:
        (generated / f"compare-{role}-{seed}.png").write_bytes(b"ok")
    (generated / "compare-before-601.png").write_bytes(b"ng-like")
    record = {"key": "probe", "trigger": "probe"}
    panels = tmp_path / "dataset"
    materials = ok_materials.add_ok_materials(record, panels, tmp_path)
    assert len(materials) == 6
    assert {item["seed"] for item in materials} == {602, 604, 608}
    assert all(item["training_policy"]["priority"] == "primary" for item in materials)
    written = sorted(path.name for path in (panels / "primary").glob("ok-*.png"))
    assert written == ["ok-602-after.png", "ok-602-before.png", "ok-604-after.png",
                       "ok-604-before.png", "ok-608-after.png", "ok-608-before.png"]
    assert "probe, " in (panels / "primary" / "ok-602-before.txt").read_text()
    assert not (panels / "primary" / "ok-601-before.png").exists()


def test_ok_job_uses_primary_and_normal_subset_dirs():
    from backend.training_dataset import dataset_config
    job = {"images": 11, "training_selection": {"samples": []}, "materials": [
        {"training_policy": {"priority": "primary"}},
        {"training_policy": {"priority": "primary"}},
        {"training_policy": {"priority": "normal"}},
    ]}
    text = dataset_config(job, "C:/sf/dataset_probe")
    assert 'image_dir = "C:/sf/dataset_probe/primary"' in text
    assert 'image_dir = "C:/sf/dataset_probe/normal"' in text
    assert 'image_dir = "C:/sf/dataset_probe"\n' not in text
