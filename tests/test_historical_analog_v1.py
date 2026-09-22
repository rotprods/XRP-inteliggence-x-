from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.historical_analog_v1 import (
    AnalogSearchConfig,
    AnalogSearchStatus,
    DistanceMetric,
    _distance,
    _jaccard,
    _normalizer,
    run_analog_sensitivity,
    search_historical_analogs,
)
from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.regime_state_v1 import (
    canonical_regime_policy,
    classify_regime,
)
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def feature(
    index: int,
    *,
    trend: float = 0.45,
    relative: float = 0.25,
    spot_flow: float = 0.55,
    leverage: float = 0.10,
    provider: str = "providers-v1",
    horizon: ResearchHorizon = ResearchHorizon.H1,
    omit: tuple[str, ...] = (),
) -> HistoricalFeatureRow:
    policy = canonical_regime_policy()
    desired = {spec.signal: 0.0 for spec in policy.specs}
    desired.update(
        {
            "trend": trend,
            "relative_strength": relative,
            "spot_flow": spot_flow,
            "leverage": leverage,
        }
    )
    families: dict[str, dict[str, float]] = {}
    for spec in policy.specs:
        if spec.signal in omit:
            continue
        family, name = spec.feature_key.split(".", 1)
        raw = spec.center + desired[spec.signal] * spec.scale / spec.direction
        families.setdefault(family, {})[name] = raw
    prediction = T0 + timedelta(days=index)
    snapshot = sha256(f"analog:{index}:{provider}:{horizon.value}".encode()).hexdigest()
    return HistoricalFeatureRow.build(
        feature_time=prediction,
        prediction_time=prediction,
        horizon=horizon,
        feature_schema_version="features-v1",
        provider_universe_version=provider,
        eligibility_class=EligibilityClass.STRICT_REPLAY,
        source_snapshot_ids=(f"snapshot:sha256:{snapshot}",),
        feature_families=families,
    )


def state(index: int, **kwargs: object):
    return classify_regime(feature(index, **kwargs))


def history(count: int = 30):
    return tuple(
        state(
            index,
            trend=0.35 + 0.01 * (index % 8),
            relative=0.10 + 0.02 * (index % 6),
            spot_flow=0.45 + 0.01 * (index % 5),
            provider="providers-v1" if index % 2 == 0 else "providers-v2",
        )
        for index in range(count)
    )


def test_search_uses_only_strictly_prior_states_and_is_future_invariant() -> None:
    query = state(
        40,
        trend=0.44,
        relative=0.18,
        spot_flow=0.50,
    )
    prior = history()
    config = AnalogSearchConfig(k=5, min_history=10)
    first = search_historical_analogs(query, prior, config=config)

    perfect_future = state(
        41,
        trend=0.44,
        relative=0.18,
        spot_flow=0.50,
    )
    second = search_historical_analogs(
        query,
        (*prior, perfect_future),
        config=config,
    )

    assert first == second
    assert first.status is AnalogSearchStatus.READY
    assert len(first.matches) == 5
    assert first.normalizer_digest is not None
    assert all(item.prediction_time < query.prediction_time for item in first.matches)
    assert all(0 < item.similarity <= 1 for item in first.matches)
    assert first.decision_authority is False
    assert first.execution_weight == 0


def test_other_horizons_and_missing_signal_candidates_are_not_eligible() -> None:
    query = state(40)
    valid = history(12)
    wrong_horizon = state(10, horizon=ResearchHorizon.H4)
    missing = classify_regime(
        feature(
            11,
            omit=("spot_flow",),
        )
    )
    report = search_historical_analogs(
        query,
        (*valid, wrong_horizon, missing),
        config=AnalogSearchConfig(
            k=3,
            min_history=10,
            signal_keys=("trend", "relative_strength", "spot_flow"),
        ),
    )
    assert report.status is AnalogSearchStatus.READY
    assert report.eligible_candidate_count == 12


def test_provider_filter_same_regime_and_lookback_are_explicit() -> None:
    query = state(40)
    prior = history()
    provider_report = search_historical_analogs(
        query,
        prior,
        config=AnalogSearchConfig(
            k=3,
            min_history=10,
            provider_universe_versions=("providers-v2",),
        ),
    )
    assert provider_report.status is AnalogSearchStatus.READY
    assert all(item.provider_universe_version == "providers-v2" for item in provider_report.matches)

    same_regime = search_historical_analogs(
        query,
        prior,
        config=AnalogSearchConfig(
            k=3,
            min_history=10,
            same_regime_only=True,
        ),
    )
    assert same_regime.status is AnalogSearchStatus.READY
    assert all(item.regime is query.regime for item in same_regime.matches)

    short = search_historical_analogs(
        query,
        prior,
        config=AnalogSearchConfig(
            k=3,
            min_history=10,
            max_lookback=timedelta(days=5),
        ),
    )
    assert short.status is AnalogSearchStatus.NO_DATA
    assert "INSUFFICIENT_STRICTLY_PRIOR_HISTORY" in short.reasons


def test_query_no_data_and_missing_requested_signal_fail_closed() -> None:
    no_data_query = classify_regime(
        feature(
            40,
            omit=("relative_strength",),
        )
    )
    report = search_historical_analogs(
        no_data_query,
        history(),
        config=AnalogSearchConfig(k=3, min_history=10),
    )
    assert report.status is AnalogSearchStatus.NO_DATA
    assert "QUERY_REGIME_NO_DATA" in report.reasons

    query = state(40)
    with pytest.raises(ValueError, match="missing requested"):
        search_historical_analogs(
            query,
            history(),
            config=AnalogSearchConfig(
                k=3,
                min_history=10,
                signal_keys=("not_present",),
            ),
        )


@pytest.mark.parametrize(
    "metric",
    tuple(DistanceMetric),
)
def test_all_distance_metrics_produce_ready_reports(metric: DistanceMetric) -> None:
    report = search_historical_analogs(
        state(40),
        history(),
        config=AnalogSearchConfig(
            k=4,
            min_history=10,
            metric=metric,
        ),
    )
    assert report.status is AnalogSearchStatus.READY
    assert len(report.matches) == 4
    assert all(item.distance >= 0 for item in report.matches)


def test_sensitivity_runs_metric_ablation_and_provider_scenarios() -> None:
    query = state(40)
    report = run_analog_sensitivity(
        query,
        history(),
        base_config=AnalogSearchConfig(
            k=3,
            min_history=10,
        ),
        metrics=tuple(DistanceMetric),
        ablation_sets=((), ("relative_strength",)),
        lookbacks=(None,),
        provider_universe_filters=((), ("providers-v1",)),
        min_ready_scenarios=3,
        min_top_k_overlap=0.0,
        min_top_regime_agreement=0.0,
    )
    assert report.ready_scenario_count >= 3
    assert len(report.scenarios) == 12
    assert report.minimum_top_k_overlap is not None
    assert report.top_regime_agreement_rate is not None
    assert report.stable is True
    assert report.decision_authority is False


def test_sensitivity_base_not_ready_fails_closed() -> None:
    query = state(40)
    report = run_analog_sensitivity(
        query,
        history(3),
        base_config=AnalogSearchConfig(k=2, min_history=5),
        min_ready_scenarios=1,
    )
    assert report.stable is False
    assert report.scenarios == ()
    assert report.reasons == ("BASE_ANALOG_SEARCH_NOT_READY",)


def test_duplicate_state_id_and_config_validation() -> None:
    query = state(40)
    duplicate = state(1)
    with pytest.raises(ValueError, match="state_id values must be unique"):
        search_historical_analogs(
            query,
            (duplicate, duplicate),
            config=AnalogSearchConfig(k=1, min_history=1),
        )
    with pytest.raises(ValueError, match="k must be positive"):
        AnalogSearchConfig(k=0)
    with pytest.raises(ValueError, match="min_history"):
        AnalogSearchConfig(k=5, min_history=4)
    with pytest.raises(ValueError, match="unique"):
        AnalogSearchConfig(signal_keys=("trend", "trend"))
    with pytest.raises(ValueError, match="cannot overlap"):
        AnalogSearchConfig(
            signal_keys=("trend",),
            excluded_signals=("trend",),
        )
    with pytest.raises(ValueError, match="max_lookback"):
        AnalogSearchConfig(max_lookback=timedelta(0))
    with pytest.raises(ValueError, match="provider_universe_versions"):
        AnalogSearchConfig(
            provider_universe_versions=("a", "a"),
        )


def test_low_level_distance_normalizer_and_jaccard_guards() -> None:
    assert _distance((0.0,), (1.0,), DistanceMetric.EUCLIDEAN) == 1.0
    assert _distance((0.0,), (1.0,), DistanceMetric.MANHATTAN) == 1.0
    assert _distance((0.0,), (0.0,), DistanceMetric.COSINE) == 0.0
    assert _distance((0.0,), (1.0,), DistanceMetric.COSINE) == 1.0
    assert _distance((1.0, 0.0), (1.0, 0.0), DistanceMetric.COSINE) == pytest.approx(0)
    with pytest.raises(ValueError, match="equal length"):
        _distance((1.0,), (), DistanceMetric.EUCLIDEAN)
    with pytest.raises(ValueError, match="unsupported"):
        _distance((1.0,), (1.0,), "bad")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="requires candidates"):
        _normalizer((), ("trend",))

    assert _jaccard((), ()) == 1.0
    assert _jaccard(("a",), ("a", "b")) == pytest.approx(0.5)


def test_sensitivity_threshold_validation() -> None:
    query = state(40)
    prior = history()
    base = AnalogSearchConfig(k=3, min_history=10)
    with pytest.raises(ValueError, match="positive"):
        run_analog_sensitivity(
            query,
            prior,
            base_config=base,
            min_ready_scenarios=0,
        )
    with pytest.raises(ValueError, match="min_top_k_overlap"):
        run_analog_sensitivity(
            query,
            prior,
            base_config=base,
            min_top_k_overlap=2,
        )
    with pytest.raises(ValueError, match="min_top_regime_agreement"):
        run_analog_sensitivity(
            query,
            prior,
            base_config=base,
            min_top_regime_agreement=-1,
        )


def test_self_state_same_regime_filter_and_no_signal_branches() -> None:
    query = state(40)
    different = replace(
        state(20),
        state_id="regime-state:sha256:" + "e" * 64,
        state_sha256="e" * 64,
        regime=CanonicalRegime.DISTRIBUTION,
    )
    report = search_historical_analogs(
        query,
        (*history(), query, different),
        config=AnalogSearchConfig(
            k=3,
            min_history=10,
            same_regime_only=True,
        ),
    )
    assert report.status is AnalogSearchStatus.READY
    assert all(item.state_id != query.state_id for item in report.matches)
    assert all(item.regime is query.regime for item in report.matches)

    no_signals = replace(
        query,
        state_id="regime-state:sha256:" + "f" * 64,
        state_sha256="f" * 64,
        regime=CanonicalRegime.NO_DATA,
        signals=(),
    )
    no_signal_report = search_historical_analogs(
        no_signals,
        history(),
        config=AnalogSearchConfig(k=3, min_history=10),
    )
    assert no_signal_report.status is AnalogSearchStatus.NO_DATA
    assert "NO_ANALOG_SIGNALS" in no_signal_report.reasons


def test_analog_finite_and_duplicate_exclusion_validation() -> None:
    from xrp_regime_engine.historical_analog_v1 import _finite

    with pytest.raises(ValueError, match="finite"):
        _finite(float("nan"), "x")
    with pytest.raises(ValueError, match="excluded_signals"):
        AnalogSearchConfig(excluded_signals=("trend", "trend"))


def test_sensitivity_can_surface_all_instability_reasons() -> None:
    query = state(
        40,
        trend=0.45,
        relative=0.25,
        spot_flow=0.55,
    )
    material = []
    for index in range(20):
        if index < 10:
            item = state(
                index,
                trend=0.44 + 0.001 * index,
                relative=0.24,
                spot_flow=0.54,
                provider="providers-v1",
            )
        else:
            base_item = state(
                index,
                trend=-0.1,
                relative=-0.2,
                spot_flow=0.0,
                provider="providers-v2",
            )
            item = replace(
                base_item,
                state_id="regime-state:sha256:" + f"{index + 100:064x}",
                state_sha256=f"{index + 100:064x}",
                regime=CanonicalRegime.DISTRIBUTION,
            )
        material.append(item)

    report = run_analog_sensitivity(
        query,
        tuple(material),
        base_config=AnalogSearchConfig(k=3, min_history=5),
        metrics=(DistanceMetric.EUCLIDEAN,),
        ablation_sets=((),),
        lookbacks=(None,),
        provider_universe_filters=(
            ("providers-v1",),
            ("providers-v2",),
        ),
        min_ready_scenarios=3,
        min_top_k_overlap=1.0,
        min_top_regime_agreement=1.0,
    )
    assert report.stable is False
    assert {
        "INSUFFICIENT_READY_SENSITIVITY_SCENARIOS",
        "ANALOG_TOP_K_UNSTABLE",
        "ANALOG_REGIME_UNSTABLE",
    } <= set(report.reasons)
