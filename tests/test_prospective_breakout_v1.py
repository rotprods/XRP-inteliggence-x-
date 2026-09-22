from datetime import UTC, datetime

import pytest

from xrp_regime_engine.prospective_breakout_v1 import (
    BreakoutEvidenceFrame,
    LiveBreakoutState,
    evaluate_breakout_frame,
)

T0 = datetime(2026, 9, 22, 14, 56, tzinfo=UTC)
SHOT1 = "bcc0f6a97065eb5f20dfc518165caab5bfe546ea2565f424241466eaa26afefa"
SHOT2 = "35ddc07af1e4721b3f585c80e89e8559b52c644ec4d8fd3cdb50ad0dddfce5a2"


def frame(**kwargs: object) -> BreakoutEvidenceFrame:
    values: dict[str, object] = {
        "observed_at": T0,
        "pair": "XRP/USDT",
        "reference_price": 1.56031,
        "breakout_level": 1.60,
        "target_barrier": 2.0,
        "independent_price_consensus_valid": True,
        "breakout_level_accepted": True,
        "spot_flow_confirmed": True,
        "relative_strength_confirmed": True,
        "leverage_expansion": False,
        "funding_dangerous": False,
        "failed_breakout": False,
        "screenshot_sha256": (SHOT1, SHOT2),
        "source_note": "prospective research fixture",
    }
    values.update(kwargs)
    return BreakoutEvidenceFrame(**values)  # type: ignore[arg-type]


def assess(**kwargs: object):
    return evaluate_breakout_frame(
        frame(**kwargs),
        experiment_id="H-XRP-BREAKOUT-150-20260922",
    )


def test_spot_confirmed_shadow_candidate_is_non_executing() -> None:
    item = assess()
    assert item.state is LiveBreakoutState.SPOT_CONFIRMED_BREAKOUT
    assert item.shadow_long_candidate is True
    assert item.research_signal_ready is True
    assert item.probability_calibrated is False
    assert item.production_ready is False
    assert item.decision_authority is False
    assert item.execution_weight == 0.0
    assert item.assessment_id == f"prospective-breakout:sha256:{item.assessment_sha256}"


def test_leverage_led_breakout_never_becomes_shadow_long_candidate() -> None:
    item = assess(
        leverage_expansion=True,
        funding_dangerous=True,
    )
    assert item.state is LiveBreakoutState.LEVERAGED_BREAKOUT
    assert item.shadow_long_candidate is False
    assert "FUNDING_DANGEROUS" in item.contradictions


def test_breakout_unconfirmed_for_price_acceptance_and_flow_gaps() -> None:
    not_accepted = assess(breakout_level_accepted=False)
    assert not_accepted.state is LiveBreakoutState.BREAKOUT_UNCONFIRMED
    assert "BREAKOUT_LEVEL_NOT_ACCEPTED" in not_accepted.contradictions

    unknown_acceptance = assess(breakout_level_accepted=None)
    assert unknown_acceptance.state is LiveBreakoutState.BREAKOUT_UNCONFIRMED
    assert "BREAKOUT_ACCEPTANCE_UNKNOWN" in unknown_acceptance.contradictions

    flow_missing = assess(spot_flow_confirmed=None)
    assert flow_missing.state is LiveBreakoutState.BREAKOUT_UNCONFIRMED
    assert "SPOT_FLOW_NOT_CONFIRMED" in flow_missing.contradictions

    relative_missing = assess(relative_strength_confirmed=None)
    assert relative_missing.state is LiveBreakoutState.BREAKOUT_UNCONFIRMED
    assert "RELATIVE_STRENGTH_NOT_CONFIRMED" in relative_missing.contradictions


def test_no_data_when_independent_consensus_is_missing_or_invalid() -> None:
    missing = assess(independent_price_consensus_valid=None)
    assert missing.state is LiveBreakoutState.NO_DATA
    assert "INDEPENDENT_PRICE_CONSENSUS_MISSING" in missing.contradictions

    invalid = assess(independent_price_consensus_valid=False)
    assert invalid.state is LiveBreakoutState.NO_DATA
    assert "INDEPENDENT_PRICE_CONSENSUS_INVALID" in invalid.contradictions


def test_failed_breakout_has_priority() -> None:
    item = assess(
        failed_breakout=True,
        independent_price_consensus_valid=False,
        breakout_level_accepted=False,
    )
    assert item.state is LiveBreakoutState.FAILED_BREAKOUT
    assert item.research_signal_ready is True
    assert item.shadow_long_candidate is False
    assert item.contradictions == ("FAILED_BREAKOUT_CONFIRMED",)


def test_unknown_leverage_blocks_confirmation() -> None:
    item = assess(leverage_expansion=None)
    assert item.state is LiveBreakoutState.BREAKOUT_UNCONFIRMED
    assert "LEVERAGE_STATE_UNKNOWN" in item.contradictions
    assert item.shadow_long_candidate is False


def test_frame_tracks_missing_signals_and_deduplicates_screenshot_hashes() -> None:
    item = frame(
        independent_price_consensus_valid=None,
        spot_flow_confirmed=None,
        screenshot_sha256=(SHOT1, SHOT1, SHOT2),
    )
    assert item.missing_signals == (
        "independent_price_consensus_valid",
        "spot_flow_confirmed",
    )
    assert item.screenshot_sha256 == tuple(sorted((SHOT1, SHOT2)))


def test_frame_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        frame(observed_at=datetime(2026, 9, 22, 14, 56))
    with pytest.raises(ValueError, match="pair"):
        frame(pair=" ")
    with pytest.raises(ValueError, match="reference_price"):
        frame(reference_price=0)
    with pytest.raises(ValueError, match="target_barrier"):
        frame(target_barrier=1.50)
    with pytest.raises(ValueError, match="screenshot_sha256"):
        frame(screenshot_sha256=("bad",))


def test_experiment_id_required() -> None:
    with pytest.raises(ValueError, match="experiment_id"):
        evaluate_breakout_frame(frame(), experiment_id=" ")
