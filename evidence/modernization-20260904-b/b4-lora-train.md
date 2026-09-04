# b4-lora-train acceptance evidence

`train_character_lora` uses the shared Services layer to caption and SCP bible
panels to fox, free ComfyUI, and stream `C:\sf\train.py` stdout into its UUID
job record. The launch is an argument vector (no PowerShell command string),
uses Anima Base, Qwen3, VAE, and bf16, and writes the result directly to fox
ComfyUI's LoRA directory.

Focused test: `tests/test_training.py tests/test_bible.py tests/test_services.py`
passed (`7 passed`).

## fox MCP acceptance

Streamable HTTP MCP called `train_character_lora("Azure Mage", trigger="azure_mage", steps=3)`.
Job `77830def-1312-4b08-acf8-76b76c6bfd39` completed bf16 training at `3/3` and
returned `Azure_Mage_3f5fb2d7.safetensors`. A subsequent MCP `list_loras`
included that exact LoRA. MCP `generate_sprite` with this LoRA and trigger then
completed job `7a8579f9-1dd8-47db-a552-9fe5ccf5eda1`, outputting
`.cache/generated/7a8579f9-1dd8-47db-a552-9fe5ccf5eda1-0.png` (RGBA 1024x1024,
corner alpha `[0,0,0,0]`, prompt `d6ddcc84-0669-431d-bce5-bb1a01efb9d6`).
