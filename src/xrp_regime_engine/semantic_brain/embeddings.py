from __future__ import annotations

import math
import re
from collections import Counter
from hashlib import sha256

TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


class HashDenseEmbedder:
    """Offline deterministic baseline. Replace with a pinned semantic model in runtime."""

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_RE.findall(text.casefold()):
            digest = sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SparseLexicalEmbedder:
    def embed(self, text: str) -> dict[str, list[int] | list[float]]:
        counts = Counter(TOKEN_RE.findall(text.casefold()))
        pairs = sorted(
            (int.from_bytes(sha256(token.encode()).digest()[:4], "big"), count)
            for token, count in counts.items()
        )
        return {
            "indices": [index for index, _ in pairs],
            "values": [float(value) for _, value in pairs],
        }
