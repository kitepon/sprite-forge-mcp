"""Small SSH/SCP boundary for fox; it never generates shell scripts."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .config import BOX_SSH, BOX_TRAIN


async def run_training(dataset_toml: str, output_name: str, model: str, qwen3: str, vae: str,
                       steps: int, *, ssh: str = BOX_SSH, train: str = BOX_TRAIN) -> tuple[int, str, str]:
    command = ["ssh", "-o", "ConnectTimeout=20", ssh, "py", "-3.13", train,
               "--dataset-config", dataset_toml, "--output-name", output_name,
               "--pretrained-model-name-or-path", model, "--qwen3", qwen3, "--vae", vae,
               "--max-train-steps", str(steps), "--network-dim", "16", "--network-alpha", "16",
               "--learning-rate", "1e-4", "--mixed-precision", "bf16"]
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    return process.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def copy_to_box(local: Path, remote: str, *, ssh: str = BOX_SSH) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec("scp", str(local), f"{ssh}:{remote}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    output, _ = await process.communicate()
    return process.returncode or 0, output.decode(errors="replace")

