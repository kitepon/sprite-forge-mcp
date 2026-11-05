"""The SSH stage boundary used by CPU-only service fixtures."""


async def stage_command(action, stage_id, **kwargs):
    if action == "prepare":
        return {"status": "prepared", "path": f"C:/sf/staging/{stage_id}"}
    return {"status": "removed" if action == "clean" else "launching"}
