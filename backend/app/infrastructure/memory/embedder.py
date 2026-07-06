"""Deterministic offline embedding fallback.

Not semantically meaningful like a learned model, but stable and cosine-comparable:
identical/similar token distributions land near each other, which is enough for tests
and keyless local demos. Production should set EMBEDDING_PROVIDER=openai.
"""
import hashlib
import math
import re

DIM = 1536


def hash_embedding(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec
