from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.regime_analog_v1 import (
    AnalogDistanceMetric,
    AnalogSearchPolicy,
    AnalogStabilityPolicy,
    HistoricalRegime,
    RegimeFeatureMap,
    RegimeThresholds,
    _distance,
    _mean_scale_matrix,
    _standardize,
    assess_analog_stability,
    classify_regime_candidate,
    search_historical_analogs,
)
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 1, tzinfo=UTC)
FEATURE_MAP = RegimeFeatureMap(
    short_return="market.short",
    medium_return="market.medium",
    relative_strength="market.relative",
    spot_flow="micro.flow",
    open_interest_change="derivatives.oi",
    funding="derivatives.funding",
    liquidation_stress="derivatives.liquidation",
    depth_imbalance="micro.depth",
)


def feature(
    index: int,
    *,
    horizon: ResearchHorizon = ResearchHorizon.H1,
    short: float | None = 0.0,
    medium: float | None = 0.0,
    relative: float | None = 0.0,
    flow: float | None = 0.0,
    oi: float | None = 0.0,
    funding: float | None = 0.0,
    liquidation: float | None = 0.0,
    depth: float | None = 0.0,
) -> HistoricalFeatureRow:
    prediction = T0 + timedelta(days=index)
    snapshot = sha256(f"analog:{horizon.value}:{index}".encode()).hexdigest()
    return HistoricalFeatureRow.build(
        feature_time=prediction,
        prediction_time=prediction,
        horizon=horizon,
        feature_schema_version="features-v1",
        provider_universe_version="providers-v1",
        eligibility_class=EligibilityClass.STRICT_REPLAY,
        source_snapshot_ids=(f"snapshot:sha256:{snapshot}",),
        feature_families={
            "market": {
                "short": short,
                "medium": medium,
                "relative": relative,
            },
            "micro": {
                "flow": flow,
                "depth": depth,
            },
            "derivatives": {
                "oi": oi,
                "funding": funding,
                "liquidation": liquidation,
            },
        },
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"medium": -0.10, "liquidation": 2.0}, HistoricalRegime.CAPITULATION),
        ({"medium": -0.03, "oi": -0.10, "liquidation": 2.0}, HistoricalRegime.DELEVERAGING),
        ({"oi": 0.10, "funding": 0.002}, HistoricalRegime.LONG_CROWDING),
        (
            {"medium": 0.06, "short": -0.03, "relative": -0.01},
            HistoricalRegime.FAILED_BREAKOUT,
        ),
        (
            {"short": 0.06, "medium": 0.03, "relative": 0.02, "flow": 0.20},
            HistoricalRegime.BREAKOUT,
        ),
        (
            {"short": 0.03, "oi": 0.10, "funding": 0.0005},
            HistoricalRegime.LEVERAGED_EXPANSION,
        ),
        (
            {"short": 0.03, "flow": 0.20, "oi": 0.01, "funding": 0.0001},
            HistoricalRegime.SPOT_LED_EXPANSION,
        ),
        (
            {"short": 0.03, "medium": -0.01, "relative": 0.02},
            HistoricalRegime.RECOVERY,
        ),
        (
            {"short": -0.01, "flow": -0.20, "depth": -0.30},
            HistoricalRegime.DISTRIBUTION,
        ),
        (
            {"short": 0.005, "flow": 0.05, "depth": 0.30, "funding": 0.0001},
            HistoricalRegime.ACCUMULATION,
        ),
        (
            {"short": 0.015, "medium": 0.02, "relative": 0.005},
            HistoricalRegime.RISK_ON,
        ),
    ],
)
def test_regime_candidate_rules(kwargs: dict[str, float], expected: HistoricalRegime) -> None:
    result = classify_regime_candidate(
        feature(1, **kwargs),
        feature_map=FEATURE_MAP,
    )
    assert result.regime is expected
    assert result.reasons
    assert not result.truth_claim
    assert not result.probability_calibrated
    assert not result.decision_authority
    assert result.execution_weight == 0
    assert result.assessment_id.startswith("regime-assessment:sha256:")


def test_regime_no_data_for_missing_or_unresolved_evidence() -> None:
    missing = classify_regime_candidate(
        feature(1, funding=None),
        feature_map=FEATURE_MAP,
    )
    assert missing.regime is HistoricalRegime.NO_DATA
    assert "derivatives.funding" in missing.missing_features

    unresolved = classify_regime_candidate(
        feature(1, short=-0.01, medium=0.01, relative=-0.01),
        feature_map=FEATURE_MAP,
    )
    assert unresolved.regime is HistoricalRegime.NO_DATA
    assert unresolved.missing_features == ()
    assert unresolved.reasons == ("NO_REGIME_RULE_MATCHED",)


def test_regime_configuration_validation() -> None:
    with pytest.raises(ValueError, match="family.name"):
        RegimeFeatureMap(
            short_return="short",
            medium_return="market.medium",
            relative_strength="market.relative",
            spot_flow="micro.flow",
            open_interest_change="derivatives.oi",
            funding="derivatives.funding",
            liquidation_stress="derivatives.liquidation",
            depth_imbalance="micro.depth",
        )
    with pytest.raises(ValueError, match="capitulation"):
        RegimeThresholds(capitulation_return=0.1)
    with pytest.raises(ValueError, match="flow thresholds"):
        RegimeThresholds(positive_flow=-0.1)
    with pytest.raises(ValueError, match="funding thresholds"):
        RegimeThresholds(elevated_funding=0.01, crowded_funding=0.001)
    with pytest.raises(ValueError, match="rule_version"):
        classify_regime_candidate(
            feature(1),
            feature_map=FEATURE_MAP,
            rule_version=" ",
        )


def analog_history() -> tuple[HistoricalFeatureRow, ...]:
    rows = [
        feature(
            index,
            short=(index - 6) / 100,
            medium=(index - 5) / 80,
            relative=(index % 5 - 2) / 100,
            flow=(index % 4 - 1.5) / 10,
            oi=(index % 6 - 2.5) / 20,
            funding=(index % 3) * 0.0001,
            liquidation=float(index % 3) / 2,
            depth=(index % 5 - 2) / 5,
        )
        for index in range(1, 16)
    ]
    rows.append(feature(16, short=None))
    rows.append(feature(17, horizon=ResearchHorizon.H4))
    rows.append(feature(40))
    return tuple(rows)


def test_historical_analog_search_is_strictly_prior_and_order_independent() -> None:
    query = feature(
        30,
        short=0.04,
        medium=0.03,
        relative=0.01,
        flow=0.1,
        oi=0.02,
        funding=0.0001,
        liquidation=0.5,
        depth=0.2,
    )
    policy = AnalogSearchPolicy(
        feature_keys=(
            "market.short",
            "market.medium",
            "market.relative",
            "micro.flow",
        ),
        top_k=4,
        min_history=10,
    )
    history = analog_history()
    forward = search_historical_analogs(
        query,
        history,
        policy=policy,
        regime_feature_map=FEATURE_MAP,
    )
    reverse = search_historical_analogs(
        query,
        tuple(reversed(history)),
        policy=policy,
        regime_feature_map=FEATURE_MAP,
    )

    assert forward.search_id == reverse.search_id
    assert forward.candidate_count == 15
    assert forward.skipped_missing_count == 1
    assert len(forward.matches) == 4
    assert all(match.prediction_time < query.prediction_time.isoformat() for match in forward.matches)
    assert tuple(match.feature_row_id for match in forward.matches) == tuple(
        match.feature_row_id for match in reverse.matches
    )
    assert forward.regime_counts
    assert not forward.truth_claim
    assert forward.execution_weight == 0


def test_analog_search_excludes_future_wrong_horizon_and_missing_rows() -> None:
    query = feature(30, short=0.02, medium=0.01, relative=0.01)
    policy = AnalogSearchPolicy(
        feature_keys=("market.short", "market.medium", "market.relative"),
        top_k=3,
        min_history=10,
    )
    result = search_historical_analogs(query, analog_history(), policy=policy)
    selected = {match.feature_row_id for match in result.matches}
    assert feature(40).feature_row_id not in selected
    assert feature(17, horizon=ResearchHorizon.H4).feature_row_id not in selected
    assert feature(16, short=None).feature_row_id not in selected


def test_analog_search_fail_closed_guards() -> None:
    history = analog_history()
    query = feature(30)

    with pytest.raises(ValueError, match="query is missing"):
        search_historical_analogs(
            replace(
                query,
                feature_families={
                    **query.feature_families,
                    "market": {
                        **query.feature_families["market"],
                        "short": None,
                    },
                },
            ),
            history,
            policy=AnalogSearchPolicy(
                feature_keys=("market.short",),
                top_k=1,
                min_history=1,
            ),
        )

    with pytest.raises(ValueError, match="insufficient strictly-prior"):
        search_historical_analogs(
            query,
            history[:2],
            policy=AnalogSearchPolicy(
                feature_keys=("market.short",),
                top_k=2,
                min_history=3,
            ),
        )

    with pytest.raises(ValueError, match="duplicate feature_row_id"):
        search_historical_analogs(
            query,
            (history[0], history[0], *history[1:15]),
            policy=AnalogSearchPolicy(
                feature_keys=("market.short",),
                top_k=2,
                min_history=3,
            ),
        )

    with pytest.raises(ValueError, match="feature_keys cannot be empty"):
        AnalogSearchPolicy(feature_keys=())
    with pytest.raises(ValueError, match="unique"):
        AnalogSearchPolicy(feature_keys=("market.short", "market.short"))
    with pytest.raises(ValueError, match="min_history"):
        AnalogSearchPolicy(feature_keys=("market.short",), top_k=3, min_history=2)


def test_distance_scaling_guards_and_metrics() -> None:
    means, scales = _mean_scale_matrix(((1.0, 2.0), (3.0, 2.0)))
    assert means == (2.0, 2.0)
    assert scales[1] == 1.0
    standardized = _standardize((2.0, 2.0), means, scales)
    assert standardized == (0.0, 0.0)

    assert _distance((0.0, 0.0), (3.0, 4.0), AnalogDistanceMetric.EUCLIDEAN) == 5.0
    assert _distance((0.0, 0.0), (3.0, 4.0), AnalogDistanceMetric.MANHATTAN) == 7.0
    assert _distance((0.0, 0.0), (3.0, 4.0), AnalogDistanceMetric.COSINE) == 1.0

    with pytest.raises(ValueError, match="cannot be empty"):
        _mean_scale_matrix(())
    with pytest.raises(ValueError, match="rectangular"):
        _mean_scale_matrix(((1.0,), (1.0, 2.0)))
    with pytest.raises(ValueError, match="dimensions"):
        _standardize((1.0,), (0.0, 0.0), (1.0, 1.0))
    with pytest.raises(ValueError, match="aligned"):
        _distance((1.0,), (1.0, 2.0), AnalogDistanceMetric.EUCLIDEAN)
    with pytest.raises(ValueError, match="unsupported"):
        _distance((1.0,), (1.0,), cast(AnalogDistanceMetric, "BAD"))


def test_analog_stability_metrics_and_no_variant_guard() -> None:
    query = feature(
        30,
        short=0.04,
        medium=0.03,
        relative=0.01,
        flow=0.1,
    )
    base = AnalogSearchPolicy(
        feature_keys=(
            "market.short",
            "market.medium",
            "market.relative",
        ),
        top_k=4,
        min_history=10,
    )
    report = assess_analog_stability(
        query,
        analog_history(),
        base_policy=base,
        stability_policy=AnalogStabilityPolicy(min_overlap=0.0),
    )
    assert report.variants
    assert report.stable
    assert 0 <= report.minimum_overlap <= 1
    assert not report.truth_claim

    no_variants = assess_analog_stability(
        query,
        analog_history(),
        base_policy=base,
        stability_policy=AnalogStabilityPolicy(
            metrics=(AnalogDistanceMetric.EUCLIDEAN,),
            leave_one_feature_out=False,
        ),
    )
    assert not no_variants.stable
    assert "NO_STABILITY_VARIANTS" in no_variants.reasons

    with pytest.raises(ValueError, match="cannot be empty"):
        AnalogStabilityPolicy(metrics=())
    with pytest.raises(ValueError, match="unique"):
        AnalogStabilityPolicy(
            metrics=(
                AnalogDistanceMetric.EUCLIDEAN,
                AnalogDistanceMetric.EUCLIDEAN,
            )
        )
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        AnalogStabilityPolicy(min_overlap=2.0)
