"""Look-alike / impersonation check: does the vendor's domain imitate an established company?

FIRST VERSION: returns no findings. Phase 2 compares resolve.by_name vs the vendor domain
(normalised, edit distance <= rules.lookalike_max_edit) -> hard "possible impersonation of X".
Output shape: {"findings": [...], "evidence": [...]}
"""


async def step_lookalike(ctx):
    return {"findings": [], "evidence": []}
