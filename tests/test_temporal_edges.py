from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest

from xrp_regime_engine.demo import generate_demo_frame
from xrp_regime_engine.features import _validate_frame
from xrp_regime_engine.models import Provenance

pytestmark = [pytest.mark.temporal, pytest.mark.contract]


def test_leap_day_and_timezone_offset_normalize_without_date_loss() -> None:
    local = timezone(timedelta(hours=2))
    observed = datetime(2024, 2, 29, 12, 30, tzinfo=local)
    item = Provenance(provider="p", observed_at=observed, available_at=observed, fetched_at=observed)
    assert item.observed_at == datetime(2024, 2, 29, 10, 30, tzinfo=UTC)


def test_frame_in_non_utc_timezone_is_normalized_to_utc() -> None:
    frame = generate_demo_frame(10)
    frame.index = frame.index.tz_convert("Europe/Madrid")
    result = _validate_frame(frame)
    assert str(result.index.tz) == "UTC"
    assert result.index.is_monotonic_increasing


def test_duplicate_instants_across_timezones_are_rejected() -> None:
    frame = generate_demo_frame(10)
    duplicate = pd.concat([frame.iloc[:2], frame.iloc[[1]], frame.iloc[2:]])
    with pytest.raises(ValueError, match="duplicates"):
        _validate_frame(duplicate)
