# Modern stack decision record

Retrieved: 2026-09-04.  This is a project decision summary, not a replacement
for the upstream documentation.

- Anima Base v1.0 is the LoRA-learning model and Anima Turbo v1.1 is the
  production model. The accepted learner is sd-scripts `anima_train_network.py`.
- Anima-Control-Pose preview-2 supplies pose control; JoyAI-Image-Edit-Plus
  supplies editing and setting-sheet generation; ToonOut supplies final alpha;
  SAM 3.1 supplies masks.
- Mage-Flow and Mage-Flow-Edit won initial comparisons but were removed from the
  official Hugging Face distribution. They are historical benchmark data, not a
  deployable dependency.
- The code surface is FastMCP 4 + FastAPI over a shared service layer, with the
  GPU appliance isolated behind HTTP and SSH.

Evidence and measurement paths are in `docs/09_modernization_bench.md` and
`evidence/modernization-20260904/`.
