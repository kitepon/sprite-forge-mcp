# p0-models evidence

Date: 2026-09-04 (JST)  
Target: `fox` (`192.168.1.11`), Windows-native ComfyUI Portable

## Implementation

Placed the Phase 0 candidate manifest under
`C:\Users\kite_\ComfyUI\ComfyUI\models` and updated `docs/models.md` with
the exact filename, model family, and loader directory.  The inventory covers:

- Anima Base v1.0 and Turbo v1.1, `qwen_3_06b_base`, `qwen_image_vae`, and
  Anima Control-Pose preview-2;
- Mage-Flow and Mage-Flow-Edit in bf16 and int8_convrot variants, their
  Qwen3-VL encoder, and Mage VAE;
- JoyAI-Image-Edit-Plus int8, its Qwen3-VL encoder, and Wan VAE;
- Krea 2 raw int8_convrot, ToonOut / BiRefNet, and SAM 3.1 Multiplex.

`opencv-python 5.0.0.93` was added to ComfyUI Portable's embedded Python.
This is the missing runtime dependency that had prevented ComfyUI-RMBG's
BiRefNet loader from importing.  After the service restart the node package
reported 37 loaded nodes (including the BiRefNet/ToonOut loader).

## Verification

1. On fox, `Get-Item` returned nonzero files for all 17 listed model weights.
   Representative sizes: Anima Base 4,182,218,328 bytes, Mage-Flow bf16
   8,231,536,784 bytes, JoyAI int8 16,433,221,224 bytes, Krea 2
   13,492,686,496 bytes, ToonOut 884,878,824 bytes, and SAM 3.1
   1,745,546,848 bytes.
2. Restarted the `ComfyUI` NSSM service. It is `Running` with `Automatic`
   startup; `/system_stats` reports ComfyUI 0.34.0, PyTorch 2.13.0+cu130,
   and `cuda:0 NVIDIA GeForce RTX 5090`.
3. Fox `/object_info` contains every Phase 0 candidate selector, including
   all Anima, Mage, JoyAI, and Krea filenames plus `BiRefNet_toonout` and
   `sam3.1_multiplex_fp16.safetensors`.
4. From `main-server`, `curl http://192.168.1.11:8188/object_info` returned
   the same representative selectors: Anima Base, Mage-Flow-Edit, JoyAI,
   Krea 2, BiRefNet ToonOut, and SAM 3.1.

