from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class QdrantConfig:
    base_url: str = "http://qdrant:6333"
    collection: str = "xrp_semantic_brain_v1"
    semantic_size: int = 1024
    timeout_seconds: float = 5.0


class QdrantIndex:
    """Minimal read/write client. No market execution capability exists here."""

    def __init__(self, config: QdrantConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client or httpx.Client(timeout=config.timeout_seconds)

    def ensure_collection(self) -> None:
        url = f"{self.config.base_url}/collections/{self.config.collection}"
        response = self.client.get(url)
        if response.status_code == 200:
            return
        if response.status_code != 404:
            response.raise_for_status()
        payload = {
            "vectors": {
                "semantic": {"size": self.config.semantic_size, "distance": "Cosine"},
                "cos20": {"size": 20, "distance": "Cosine"},
            },
            "sparse_vectors": {"lexical": {}},
        }
        self.client.put(url, json=payload).raise_for_status()

    def upsert(self, points: list[dict[str, Any]]) -> None:
        url = f"{self.config.base_url}/collections/{self.config.collection}/points?wait=true"
        self.client.put(url, json={"points": points}).raise_for_status()

    def query(self, vector: list[float], limit: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        url = f"{self.config.base_url}/collections/{self.config.collection}/points/query"
        body: dict[str, Any] = {
            "query": vector,
            "using": "semantic",
            "limit": limit,
            "with_payload": True,
        }
        if filters:
            body["filter"] = filters
        response = self.client.post(url, json=body)
        response.raise_for_status()
        return list(response.json().get("result", {}).get("points", []))
