# p1-matte evidence

Date: 2026-09-04 (JST)  
Target: fox / ComfyUI 0.34.0 / RTX 5090

## What was run

Used p1-base's fixed 1024px Anima, Mage-Flow, and Krea 2 outputs as a common
input set.  Ran `BiRefNet_toonout` through `BiRefNetRMBG` and native SAM 3.1
Multiplex through `SAM3_Detect` with the text prompt `character`.

The first SAM output exposed its mask polarity (background white).  The final
workflow therefore includes `InvertMask` before `JoinImageWithAlpha`; this
gives transparent corners and a correctly opaque subject.

## Results

- ToonOut prompts `8f7cfad7`, `e774de79`, and `3f089bad`: 3/3 success.
- Final SAM 3.1 prompts `dd2b1f8f`, `cf657a85`, and `0d014dc9`: 3/3 success.
- The four alpha corners of every final RGBA file were zero.
- ToonOut preserved partial-alpha edge pixels (8,750 / 13,025 / 16,014 for
  Anima / Krea / Mage); SAM 3.1 produced binary masks for these images.
- Visual inspection found that ToonOut retained hair tips, fingers, and the
  staff better.  Both methods avoided background color leakage.

`docs/09_modernization_bench.md` records the inputs, workflow settings,
output locations, and the adoption decision: ToonOut is the final RGBA path;
SAM 3.1 remains the promptable mask-extraction auxiliary.

