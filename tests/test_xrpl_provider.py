from __future__ import annotations

import httpx
import pytest

from xrp_regime_engine.providers.base import ProviderError
from xrp_regime_engine.providers.xrpl import XRPLProvider


@pytest.mark.asyncio
async def test_xrpl_rpc_is_strictly_read_only() -> None:
    provider = XRPLProvider(
        "https://s1.ripple.com:51234",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    try:
        with pytest.raises(ProviderError, match="not allowlisted"):
            await provider.rpc("submit", [{"tx_blob": "00"}])
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_xrpl_server_metrics_parse_read_only_payload() -> None:
    payload = {
        "result": {
            "status": "success",
            "info": {
                "validated_ledger": {"age": 2},
                "load_factor": 1.25,
                "peers": 42,
            },
        }
    }
    provider = XRPLProvider(
        "https://s1.ripple.com:51234",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    try:
        metrics = await provider.server_metrics()
    finally:
        await provider.aclose()
    assert {item.metric for item in metrics} == {
        "validated_ledger_age",
        "load_factor",
        "peers",
    }
