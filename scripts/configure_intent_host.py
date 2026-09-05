"""契約ログイン済みホストで、解釈CLI専用のSSH接続を設定する。"""
import argparse
from datetime import datetime, UTC
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile


MARKER = "sprite-forge-intent"


def authorized_text(previous: str, public_key: str, root: Path, uv: str) -> str:
    kind, key, *_ = public_key.strip().split()
    command = f"cd {shlex.quote(str(root))} && exec {shlex.quote(uv)} run --no-sync python -m backend.intent_cli"
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    entry = f'restrict,command="{escaped}" {kind} {key} {MARKER}'
    lines = previous.splitlines()
    for line in lines:
        if key in line.split() and not line.endswith(f" {MARKER}"):
            raise ValueError("この鍵には別用途の登録があります。既存の権限は変更していません。")
    return "\n".join([line for line in lines if not line.endswith(f" {MARKER}")] + [entry]) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--authorized-keys", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("ホストにuvが必要です。")
    if not (root / "backend/intent_cli.py").is_file():
        raise ValueError("解釈CLIのあるプロジェクトを指定してください。")
    authorized = args.authorized_keys
    previous = authorized.read_text() if authorized.exists() else ""
    updated = authorized_text(previous, args.public_key.read_text(), root, uv)
    subprocess.run(["codex", "login", "status"], check=True)
    subprocess.run([uv, "sync", "--frozen", "--no-dev"], cwd=root, check=True)
    if updated == previous:
        print("解釈CLI専用の接続設定は変更ありません。")
        return
    backup = root / ".intent-setup-backups"
    backup.mkdir(mode=0o700, exist_ok=True)
    archive = backup / f"ssh-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.tar.gz"
    with tarfile.open(archive, "w:gz") as target:
        if authorized.exists():
            target.add(authorized, arcname="authorized_keys")
    archive.chmod(0o600)
    authorized.write_text(updated)
    authorized.chmod(0o600)
    print(f"解釈CLI専用の接続を設定しました。変更前の保存先: {archive}")


if __name__ == "__main__":
    main()
