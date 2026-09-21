from __future__ import annotations

import asyncio

import pytest

from xrp_regime_engine.scheduler import run_forever


@pytest.mark.asyncio
async def test_scheduler_rejects_non_positive_interval() -> None:
    async def job() -> None:
        return None

    with pytest.raises(ValueError, match="positive"):
        await run_forever(job, 0)


@pytest.mark.asyncio
async def test_scheduler_runs_job_then_propagates_cancellation(monkeypatch) -> None:
    calls = 0

    async def job() -> None:
        nonlocal calls
        calls += 1

    async def stop_after_iteration(delay: float) -> None:
        assert delay == 1
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", stop_after_iteration)
    with pytest.raises(asyncio.CancelledError):
        await run_forever(job, 1)
    assert calls == 1


@pytest.mark.asyncio
async def test_scheduler_logs_job_failure_and_continues(monkeypatch, caplog) -> None:
    calls = 0

    async def job() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic failure")

    async def stop_after_iteration(delay: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", stop_after_iteration)
    with pytest.raises(asyncio.CancelledError):
        await run_forever(job, 2)
    assert calls == 1
    assert "scheduled job failed" in caplog.text
