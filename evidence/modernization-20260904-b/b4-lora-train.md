# b4-lora-train acceptance evidence

`train_character_lora` uses the shared Services layer to caption and SCP bible
panels to fox, free ComfyUI, and stream `C:\sf\train.py` stdout into its UUID
job record. The launch is an argument vector (no PowerShell command string),
uses Anima Base, Qwen3, VAE, and bf16, and writes the result directly to fox
ComfyUI's LoRA directory.

Focused test: `tests/test_training.py tests/test_bible.py tests/test_services.py`
passed (`7 passed`).

## fox MCP acceptance

The accepted corrective run called `train_character_lora("Azure Mage",
trigger="azure_mage, silver-haired mage, teal navy robes", steps=12)`.
Job `1e84118a-b2c5-40c7-9967-8617c419cc29` completed bf16 training at `12/12`
and returned `Azure_Mage_80400235.safetensors`; `list_loras` included it.
MCP `generate_sprite` with that LoRA, the same trigger, and an explicit
silver-haired teal/navy-robed crystal-staff mage prompt completed job
`7560bc87-b72d-441c-9b7d-8180b9fedf41`, outputting
`.cache/generated/7560bc87-b72d-441c-9b7d-8180b9fedf41-0.png` (RGBA 1024x1024,
corner alpha `[0,0,0,0]`, prompt `fe159de4-ab94-4a41-bbf4-b85dd387e7c6`).
Visual inspection confirmed the Azure Mage's silver hair, teal/navy robes,
gold trim, and crystal staff.
