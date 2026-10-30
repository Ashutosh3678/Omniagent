"""Local text similarity: 64-dimensional hashed embeddings and cosine similarity.

No model and no network. Used to check that what is on screen matches what a step
meant to do, and to pick the control whose label best matches a description.
"""

from __future__ import annotations

import hashlib
import math
import re

DIM = 64
VERIFY_THRESHOLD = 0.6

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    return _NON_ALNUM.sub(" ", text.lower()).strip()


def _slot(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % DIM, 1.0 if (value >> 32) & 1 else -1.0


def embed(text: str) -> list[float]:
    """Words plus character trigrams, hashed into 64 signed buckets and L2-normalised."""
    norm = normalize(text)
    vector = [0.0] * DIM
    if not norm:
        return vector
    for word in norm.split():
        index, sign = _slot("w:" + word)
        vector[index] += sign
    padded = f"  {norm}  "
    for i in range(len(padded) - 2):
        index, sign = _slot("c:" + padded[i : i + 3])
        vector[index] += 0.5 * sign
    length = math.sqrt(sum(v * v for v in vector))
    return [v / length for v in vector] if length else vector


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both are unit length (or zero)


def similarity(expected: str, observed: str) -> float:
    """How well `observed` contains something like `expected`, from 0 to 1.

    The screen holds more than the expected text, so the expected text is compared
    with every window of the observed text of about the same length and the best
    score wins. Text that appears verbatim scores 1.0.
    """
    want = normalize(expected)
    have = normalize(observed)
    if not want or not have:
        return 0.0
    if want in have:
        return 1.0
    target = embed(want)
    words = have.split()
    size = max(len(want.split()), 1)
    best = cosine(target, embed(have)) if len(words) <= size * 2 else 0.0
    for width in {size, size + 1, max(size - 1, 1), size * 2}:
        step = max(width // 2, 1)
        for start in range(0, max(len(words) - width, 0) + 1, step):
            best = max(best, cosine(target, embed(" ".join(words[start : start + width]))))
    return round(max(best, 0.0), 4)
