from __future__ import annotations

import math

import httpx
import pytest

from xrp_regime_engine.semantic_brain.embeddings import HashDenseEmbedder, SparseLexicalEmbedder
from xrp_regime_engine.semantic_brain.qdrant import QdrantConfig, QdrantIndex


def test_hash_dense_embedder_is_deterministic_normalized_and_empty_safe() -> None:
    embedder = HashDenseEmbedder(dimensions=32)

    first = embedder.embed("XRP liquidity XRP")
    second = embedder.embed("xrp LIQUIDITY xrp")

    assert first == second
    assert len(first) == 32
    assert math.isclose(sum(value * value for value in first), 1.0)
    assert embedder.embed("") == [0.0] * 32


def test_sparse_lexical_embedder_counts_casefolded_tokens() -> None:
    embedded = SparseLexicalEmbedder().embed("XRP xrp RLUSD")

    assert len(embedded["indices"]) == 2
    assert sum(embedded["values"]) == 3.0
    assert embedded["indices"] == sorted(embedded["indices"])


def test_qdrant_existing_collection_is_not_recreated() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request, json={"result": {}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        QdrantIndex(QdrantConfig(), client=client).ensure_collection()

    assert [request.method for request in requests] == ["GET"]


def test_qdrant_missing_collection_is_created_with_expected_vector_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404, request=request)
        return httpx.Response(200, request=request, json={"result": True})

    config = QdrantConfig(base_url="http://qdrant.test", semantic_size=64)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        QdrantIndex(config, client=client).ensure_collection()

    assert [request.method for request in requests] == ["GET", "PUT"]
    assert b'"size":64' in requests[1].content
    assert b'"cos20"' in requests[1].content
    assert b'"lexical"' in requests[1].content


def test_qdrant_unexpected_collection_error_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        QdrantIndex(QdrantConfig(), client=client).ensure_collection()


def test_qdrant_upsert_and_query_are_hermetic_and_preserve_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                request=request,
                json={"result": {"points": [{"id": "claim:1", "score": 0.9}]}},
            )
        return httpx.Response(200, request=request, json={"result": {"status": "ok"}})

    filters = {"must": [{"key": "status", "match": {"value": "FACT"}}]}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        index = QdrantIndex(QdrantConfig(base_url="http://qdrant.test"), client=client)
        index.upsert([{"id": "claim:1", "vector": {"semantic": [1.0]}}])
        result = index.query([1.0], limit=3, filters=filters)
        result_without_filter = index.query([1.0], limit=1)

    assert result == [{"id": "claim:1", "score": 0.9}]
    assert result_without_filter == [{"id": "claim:1", "score": 0.9}]
    assert [request.method for request in requests] == ["PUT", "POST", "POST"]
    assert b'"filter"' in requests[1].content
    assert b'"filter"' not in requests[2].content
