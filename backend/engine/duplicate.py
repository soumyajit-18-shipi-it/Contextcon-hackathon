"""Duplicate check: is this vendor already in the client's records (or a past run)?

FIRST VERSION: returns no matches. Phase 2 adds:
  same normalised domain                 -> exact duplicate (hard)
  same director + name score >= rule     -> likely duplicate (soft)
  name score in look-alike band + other domain -> look-alike name (soft)
Output shape (kept stable for the verdict and the UI):
  {"matches": [...], "duplicate_of": str|None, "evidence": [...]}
"""


async def step_duplicate(ctx):
    return {"matches": [], "duplicate_of": None, "evidence": []}
