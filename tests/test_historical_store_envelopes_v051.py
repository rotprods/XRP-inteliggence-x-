from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from xrp_regime_engine.historical_store import ContentAddressedRawStore


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def test_same_content_can_have_multiple_immutable_provenance_envelopes(tmp_path: Path) -> None:
    store = ContentAddressedRawStore(tmp_path)
    payload = b'{"same":"content"}'
    first = store.put(
        provider="coinbase",
        payload=payload,
        received_at=BASE,
        source_url="https://api.example.test/history?start=1",
        attributes={"cursor": 1},
    )
    second = store.put(
        provider="coinbase",
        payload=payload,
        received_at=BASE + timedelta(minutes=1),
        source_url="https://api.example.test/history?start=2",
        attributes={"cursor": 2},
    )
    assert first.payload_path == second.payload_path
    assert first.payload_sha256 == second.payload_sha256
    assert first.metadata_path != second.metadata_path
    store.verify(first)
    store.verify(second)


def test_source_query_secrets_are_redacted_but_safe_replay_parameters_remain(tmp_path: Path) -> None:
    store = ContentAddressedRawStore(tmp_path)
    envelope = store.put(
        provider="coinbase",
        payload=b'{"ok":true}',
        received_at=BASE,
        source_url=(
            "https://api.example.test/history?symbol=XRP-USD&start=1"
            "&api_key=super-secret&signature=also-secret"
        ),
    )
    assert "symbol=XRP-USD" in envelope.source_url
    assert "start=1" in envelope.source_url
    assert "super-secret" not in envelope.source_url
    assert "also-secret" not in envelope.source_url
    assert "%5BREDACTED%5D" in envelope.source_url
