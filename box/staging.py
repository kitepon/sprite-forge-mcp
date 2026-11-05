"""Own disposable training transfers; source data and model weights live elsewhere."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent / "staging"


@contextmanager
def locked():
    if ROOT.is_symlink() or ROOT.is_junction():
        raise ValueError("staging root must not be a link")
    ROOT.mkdir(mode=0o700, exist_ok=True)
    path = ROOT / ".lock"
    if path.is_symlink():
        raise ValueError("staging lock must not be a link")
    with path.open("a+b") as handle:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def directory(stage_id: str) -> Path:
    if str(uuid.UUID(stage_id)) != stage_id:
        raise ValueError("a canonical job UUID is required")
    path = ROOT / stage_id
    if path.is_symlink() or path.is_junction():
        raise ValueError("stage must not be a link")
    return path


def state(stage_id: str) -> dict:
    path = directory(stage_id) / ".spriteforge-stage.json"
    if path.is_symlink():
        raise ValueError("stage marker must not be a link")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("job_id") != stage_id or value.get("schema") != 1:
        raise ValueError("stage ownership does not match")
    return value


def save(stage_id: str, status: str) -> None:
    path = directory(stage_id) / ".spriteforge-stage.json"
    temporary = path.with_suffix(".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError("stage state must not be a link")
    temporary.write_text(json.dumps({"schema": 1, "job_id": stage_id, "status": status}), encoding="utf-8")
    temporary.replace(path)


def prepare(stage_id: str) -> dict:
    with locked():
        path = directory(stage_id)
        path.mkdir(mode=0o700)
        save(stage_id, "prepared")
        return {"status": "prepared", "path": path.as_posix()}


def transition(stage_id: str, before: str, after: str) -> None:
    with locked():
        if state(stage_id)["status"] != before:
            raise ValueError(f"stage is not {before}")
        save(stage_id, after)


def clean(stage_id: str) -> dict:
    with locked():
        path = directory(stage_id)
        if not path.exists():
            return {"status": "absent"}
        current = state(stage_id)["status"]
        if current not in {"prepared", "finished"}:
            return {"status": "retained_unknown", "stage_state": current}
        # Never traverse links, even in a stage whose marker we own.
        if any(p.is_symlink() or p.is_junction() for p in path.rglob("*")):
            raise ValueError("stage contains a link")
        shutil.rmtree(path)
        return {"status": "removed"}


def validate_config(stage_id: str, config: Path) -> None:
    path = directory(stage_id)
    if not config.is_relative_to(path) or config.resolve() != config.absolute():
        raise ValueError("training config must be inside its owned stage")
    state(stage_id)


def run(stage_id: str, command: list[str], cwd: Path) -> int:
    transition(stage_id, "launching", "running")
    # A killed parent leaves running unknown: SSH exit is not worker exit.
    result = subprocess.run(command, cwd=cwd, check=False)
    transition(stage_id, "running", "finished")
    clean(stage_id)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch", "clean"))
    parser.add_argument("stage_id")
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.stage_id)
    elif args.action == "launch":
        transition(args.stage_id, "prepared", "launching")
        result = {"status": "launching"}
    else:
        result = clean(args.stage_id)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
