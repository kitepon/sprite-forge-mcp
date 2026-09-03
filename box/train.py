#!/usr/bin/env python3
"""Windows-native Anima LoRA training entrypoint for the fox GPU machine.

This file is copied to ``C:\\sf\\train.py``.  It deliberately uses only Python:
it asks the already-running ComfyUI to release VRAM, then runs the checked-out
sd-scripts ``anima_train_network.py`` through the venv's ``accelerate`` command.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SDSCRIPTS = Path(r"C:\sd-scripts")
VENV = ROOT / "venv"


def _free_comfy(url: str) -> None:
    request = urllib.request.Request(
        f"{url.rstrip('/')}/free",
        data=b'{"unload_models":true,"free_memory":true}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except OSError as exc:
        print(f"warning: ComfyUI VRAM release skipped: {exc}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch Windows-native Anima LoRA training with kohya sd-scripts."
    )
    parser.add_argument("--dataset-config", required=True, type=Path,
                        help="kohya dataset TOML")
    parser.add_argument("--output-name", required=True,
                        help="output safetensors stem")
    parser.add_argument("--pretrained-model-name-or-path", required=True, type=Path,
                        help="Anima base-model directory or checkpoint")
    parser.add_argument("--qwen3", required=True, type=Path,
                        help="Qwen3-0.6B text-encoder model or directory")
    parser.add_argument("--vae", required=True, type=Path,
                        help="Qwen-Image VAE model")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--max-train-steps", type=int, default=1500)
    parser.add_argument("--network-dim", type=int, default=16)
    parser.add_argument("--network-alpha", type=int, default=8)
    parser.add_argument("--learning-rate", default="1e-4")
    parser.add_argument("--mixed-precision", choices=("bf16",), default="bf16")
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    return parser


def main() -> int:
    args = _parser().parse_args()
    accelerate = VENV / "Scripts" / "accelerate.exe"
    trainer = SDSCRIPTS / "anima_train_network.py"
    if not accelerate.is_file():
        raise SystemExit(f"accelerate is missing: {accelerate}")
    if not trainer.is_file():
        raise SystemExit(f"Anima trainer is missing: {trainer}")
    if not args.dataset_config.is_file():
        raise SystemExit(f"dataset TOML is missing: {args.dataset_config}")
    for label, path in (("base model", args.pretrained_model_name_or_path),
                        ("Qwen3 text encoder", args.qwen3), ("VAE", args.vae)):
        if not path.exists():
            raise SystemExit(f"{label} is missing: {path}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _free_comfy(args.comfy_url)
    command = [
        str(accelerate), "launch", "--num_processes", "1",
        "--mixed_precision", args.mixed_precision, str(trainer),
        "--pretrained_model_name_or_path", str(args.pretrained_model_name_or_path),
        "--qwen3", str(args.qwen3), "--vae", str(args.vae),
        "--dataset_config", str(args.dataset_config),
        "--output_dir", str(args.output_dir),
        "--output_name", args.output_name,
        "--network_module", "networks.lora_anima",
        "--network_dim", str(args.network_dim),
        "--network_alpha", str(args.network_alpha),
        "--learning_rate", args.learning_rate,
        "--max_train_steps", str(args.max_train_steps),
        "--mixed_precision", args.mixed_precision,
        "--save_precision", args.mixed_precision,
        "--save_model_as", "safetensors",
        "--gradient_checkpointing", "--sdpa",
    ]
    print("running:", subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(command, cwd=SDSCRIPTS, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
