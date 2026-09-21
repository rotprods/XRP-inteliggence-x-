from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from xrp_regime_engine.depth_dynamics import DepthDynamics
from xrp_regime_engine.derivatives import FundingState, OpenInterestState
from xrp_regime_engine.order_flow import OrderFlowState


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True)
class CrossStreamFreshnessPolicy:
    depth_max_age_seconds: float = 5.0
    agg_trades_max_age_seconds: float = 5.0
    open_interest_max_age_seconds: float = 30.0
    funding_max_age_seconds: float = 120.0
    max_observed_skew_seconds: float = 30.0

    def __post_init__(self) -> None:
        for field, value in (
            ("depth_max_age_seconds", self.depth_max_age_seconds),
            ("agg_trades_max_age_seconds", self.agg_trades_max_age_seconds),
            ("open_interest_max_age_seconds", self.open_interest_max_age_seconds),
            ("funding_max_age_seconds", self.funding_max_age_seconds),
            ("max_observed_skew_seconds", self.max_observed_skew_seconds),
        ):
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field} must be finite and positive")


@dataclass(frozen=True)
class CrossStreamAlignment:
    symbol: str
    prediction_time: datetime
    depth_age_seconds: float | None
    agg_trades_age_seconds: float | None
    open_interest_age_seconds: float | None
    funding_age_seconds: float | None
    basis_age_seconds: float | None
    max_observed_skew_seconds: float | None
    point_in_time_eligible: bool
    evidence_eligible: bool
    regime_eligible: bool
    quality_flags: tuple[str, ...]
    execution_weight: float = 0.0


def _check_stream(
    *,
    name: str,
    observed_at: datetime | None,
    available_at: datetime | None,
    fetched_at: datetime | None,
    provenance_complete: bool,
    prediction_time: datetime,
    max_age_seconds: float,
    flags: list[str],
) -> tuple[float | None, bool]:
    if observed_at is None:
        flags.append(f"{name}_NO_DATA")
        return None, True

    _require_aware(observed_at, f"{name}.observed_at")
    age_seconds = (prediction_time - observed_at).total_seconds()
    blocked = False

    if not provenance_complete or available_at is None or fetched_at is None:
        flags.append(f"{name}_PROVENANCE_INCOMPLETE")
        blocked = True
    else:
        _require_aware(available_at, f"{name}.available_at")
        _require_aware(fetched_at, f"{name}.fetched_at")
        if not observed_at <= available_at <= fetched_at:
            flags.append(f"{name}_PROVENANCE_INVALID")
            blocked = True

    if observed_at > prediction_time:
        flags.append(f"{name}_FUTURE_KNOWLEDGE")
        blocked = True
    if available_at is not None and available_at > prediction_time:
        flags.append(f"{name}_FUTURE_KNOWLEDGE")
        blocked = True
    if fetched_at is not None and fetched_at > prediction_time:
        flags.append(f"{name}_FUTURE_KNOWLEDGE")
        blocked = True

    if age_seconds > max_age_seconds:
        flags.append(f"{name}_STALE")
        blocked = True

    return age_seconds, blocked


def assess_cross_stream_alignment(
    *,
    depth: DepthDynamics | None,
    order_flow: OrderFlowState | None,
    funding: FundingState | None,
    open_interest: OpenInterestState | None,
    prediction_time: datetime,
    policy: CrossStreamFreshnessPolicy | None = None,
) -> CrossStreamAlignment:
    """Align depth, aggTrades, OI, funding and basis without inferring direction.

    The result is an observational eligibility gate only. Passing alignment does not
    authorize a regime label, probability, trading signal, position sizing or order.
    """
    _require_aware(prediction_time, "prediction_time")
    policy = policy or CrossStreamFreshnessPolicy()

    symbols = {
        item.symbol
        for item in (depth, order_flow, funding, open_interest)
        if item is not None
    }
    if len(symbols) > 1:
        raise ValueError("cross-stream alignment cannot mix symbols")
    symbol = next(iter(symbols), "UNKNOWN")

    flags: list[str] = []
    blocked = False

    depth_age, depth_blocked = _check_stream(
        name="DEPTH",
        observed_at=None if depth is None else depth.last_observed_at or depth.observed_at,
        available_at=None if depth is None else depth.last_available_at,
        fetched_at=None if depth is None else depth.last_fetched_at,
        provenance_complete=False if depth is None else depth.provenance_complete,
        prediction_time=prediction_time,
        max_age_seconds=policy.depth_max_age_seconds,
        flags=flags,
    )
    blocked = blocked or depth_blocked

    trade_age, trade_blocked = _check_stream(
        name="AGG_TRADES",
        observed_at=(
            None if order_flow is None else order_flow.last_observed_at or order_flow.observed_at
        ),
        available_at=None if order_flow is None else order_flow.last_available_at,
        fetched_at=None if order_flow is None else order_flow.last_fetched_at,
        provenance_complete=False if order_flow is None else order_flow.provenance_complete,
        prediction_time=prediction_time,
        max_age_seconds=policy.agg_trades_max_age_seconds,
        flags=flags,
    )
    blocked = blocked or trade_blocked

    oi_age, oi_blocked = _check_stream(
        name="OPEN_INTEREST",
        observed_at=None if open_interest is None else open_interest.observed_at,
        available_at=None if open_interest is None else open_interest.available_at,
        fetched_at=None if open_interest is None else open_interest.fetched_at,
        provenance_complete=(
            False if open_interest is None else open_interest.provenance_complete
        ),
        prediction_time=prediction_time,
        max_age_seconds=policy.open_interest_max_age_seconds,
        flags=flags,
    )
    blocked = blocked or oi_blocked

    funding_age, funding_blocked = _check_stream(
        name="FUNDING",
        observed_at=None if funding is None else funding.observed_at,
        available_at=None if funding is None else funding.available_at,
        fetched_at=None if funding is None else funding.fetched_at,
        provenance_complete=False if funding is None else funding.provenance_complete,
        prediction_time=prediction_time,
        max_age_seconds=policy.funding_max_age_seconds,
        flags=flags,
    )
    blocked = blocked or funding_blocked

    basis_age, basis_blocked = _check_stream(
        name="BASIS",
        observed_at=None if funding is None else funding.observed_at,
        available_at=None if funding is None else funding.available_at,
        fetched_at=None if funding is None else funding.fetched_at,
        provenance_complete=False if funding is None else funding.provenance_complete,
        prediction_time=prediction_time,
        max_age_seconds=policy.funding_max_age_seconds,
        flags=flags,
    )
    blocked = blocked or basis_blocked

    observed = [
        value
        for value in (
            None if depth is None else depth.last_observed_at or depth.observed_at,
            None
            if order_flow is None
            else order_flow.last_observed_at or order_flow.observed_at,
            None if open_interest is None else open_interest.observed_at,
            None if funding is None else funding.observed_at,
        )
        if value is not None
    ]
    max_skew: float | None = None
    if len(observed) >= 2:
        max_skew = (max(observed) - min(observed)).total_seconds()
        if max_skew > policy.max_observed_skew_seconds:
            flags.append("CROSS_STREAM_MISALIGNED")
            blocked = True

    point_in_time_eligible = not blocked
    return CrossStreamAlignment(
        symbol=symbol,
        prediction_time=prediction_time,
        depth_age_seconds=depth_age,
        agg_trades_age_seconds=trade_age,
        open_interest_age_seconds=oi_age,
        funding_age_seconds=funding_age,
        basis_age_seconds=basis_age,
        max_observed_skew_seconds=max_skew,
        point_in_time_eligible=point_in_time_eligible,
        evidence_eligible=point_in_time_eligible,
        regime_eligible=False,
        quality_flags=tuple(dict.fromkeys(flags)),
        execution_weight=0.0,
    )
