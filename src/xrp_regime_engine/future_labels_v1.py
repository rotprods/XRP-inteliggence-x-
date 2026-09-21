from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from xrp_regime_engine.research_horizon import ResearchHorizon, horizon_end_at

LABEL_STORE_ROLE = "LABELS"
LABEL_STORE_SCHEMA_VERSION = 1


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _finite_positive(value: float, field: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return numeric


@dataclass(frozen=True, slots=True)
class BarrierSet:
    barrier_set_id: str
    barrier_sha256: str
    version: str
    absolute_prices: tuple[float, ...]
    return_thresholds: tuple[float, ...]

    @classmethod
    def build(
        cls,
        *,
        version: str,
        absolute_prices: Sequence[float],
        return_thresholds: Sequence[float],
    ) -> BarrierSet:
        normalized_version = version.strip()
        if not normalized_version:
            raise ValueError("barrier version is required")
        absolute = tuple(
            sorted({_finite_positive(value, "absolute barrier") for value in absolute_prices})
        )
        thresholds = tuple(
            sorted({_finite_positive(value, "return threshold") for value in return_thresholds})
        )
        if not absolute and not thresholds:
            raise ValueError("barrier set cannot be empty")
        payload = {
            "version": normalized_version,
            "absolute_prices": list(absolute),
            "return_thresholds": list(thresholds),
        }
        digest = sha256(_canonical(payload).encode()).hexdigest()
        return cls(
            barrier_set_id=f"barriers:sha256:{digest}",
            barrier_sha256=digest,
            version=normalized_version,
            absolute_prices=absolute,
            return_thresholds=thresholds,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "barrier_set_id": self.barrier_set_id,
            "barrier_sha256": self.barrier_sha256,
            "version": self.version,
            "absolute_prices": list(self.absolute_prices),
            "return_thresholds": list(self.return_thresholds),
        }


def canonical_xrp_barrier_set() -> BarrierSet:
    return BarrierSet.build(
        version="xrp-barriers-v1",
        absolute_prices=(2.0, 3.0, 3.65, 5.0, 7.34, 10.0, 17.0, 26.6, 50.0),
        return_thresholds=(0.01, 0.02, 0.05, 0.10),
    )


@dataclass(frozen=True, slots=True)
class PricePoint:
    at: datetime
    price: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", _utc(self.at, "price point timestamp"))
        object.__setattr__(self, "price", _finite_positive(self.price, "price"))


@dataclass(frozen=True, slots=True)
class FutureOutcomeLabel:
    label_id: str
    label_sha256: str
    feature_row_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    label_end_at: datetime
    resolved_at: datetime
    barrier_set_id: str
    start_price: float
    end_price: float
    future_return: float
    maximum_favorable_excursion: float
    maximum_adverse_excursion: float
    realized_log_volatility: float
    maximum_drawdown: float
    positive_return_touches: Mapping[str, bool]
    negative_return_touches: Mapping[str, bool]
    absolute_price_touches: Mapping[str, bool]

    def to_payload(self) -> dict[str, object]:
        return {
            "label_id": self.label_id,
            "label_sha256": self.label_sha256,
            "feature_row_id": self.feature_row_id,
            "prediction_time": self.prediction_time.isoformat(),
            "horizon": self.horizon.value,
            "label_end_at": self.label_end_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat(),
            "barrier_set_id": self.barrier_set_id,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "future_return": self.future_return,
            "maximum_favorable_excursion": self.maximum_favorable_excursion,
            "maximum_adverse_excursion": self.maximum_adverse_excursion,
            "realized_log_volatility": self.realized_log_volatility,
            "maximum_drawdown": self.maximum_drawdown,
            "positive_return_touches": dict(self.positive_return_touches),
            "negative_return_touches": dict(self.negative_return_touches),
            "absolute_price_touches": dict(self.absolute_price_touches),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FutureOutcomeLabel:
        label = cls(
            label_id=str(payload["label_id"]),
            label_sha256=str(payload["label_sha256"]),
            feature_row_id=str(payload["feature_row_id"]),
            prediction_time=datetime.fromisoformat(str(payload["prediction_time"])),
            horizon=ResearchHorizon(str(payload["horizon"])),
            label_end_at=datetime.fromisoformat(str(payload["label_end_at"])),
            resolved_at=datetime.fromisoformat(str(payload["resolved_at"])),
            barrier_set_id=str(payload["barrier_set_id"]),
            start_price=float(cast(float | int | str, payload["start_price"])),
            end_price=float(cast(float | int | str, payload["end_price"])),
            future_return=float(cast(float | int | str, payload["future_return"])),
            maximum_favorable_excursion=float(
                cast(float | int | str, payload["maximum_favorable_excursion"])
            ),
            maximum_adverse_excursion=float(
                cast(float | int | str, payload["maximum_adverse_excursion"])
            ),
            realized_log_volatility=float(
                cast(float | int | str, payload["realized_log_volatility"])
            ),
            maximum_drawdown=float(cast(float | int | str, payload["maximum_drawdown"])),
            positive_return_touches=cast(Mapping[str, bool], payload["positive_return_touches"]),
            negative_return_touches=cast(Mapping[str, bool], payload["negative_return_touches"]),
            absolute_price_touches=cast(Mapping[str, bool], payload["absolute_price_touches"]),
        )
        unsigned = label._unsigned_payload()
        digest = sha256(_canonical(unsigned).encode()).hexdigest()
        if label.label_id != f"label:sha256:{digest}" or label.label_sha256 != digest:
            raise RuntimeError("stored label digest does not match payload")
        return label

    def _unsigned_payload(self) -> dict[str, object]:
        payload = self.to_payload()
        payload.pop("label_id")
        payload.pop("label_sha256")
        return payload


def _touch_key(value: float) -> str:
    return format(value, ".12g")


def build_future_outcome_label(
    *,
    feature_row_id: str,
    prediction_time: datetime,
    horizon: ResearchHorizon,
    start_price: float,
    price_path: Sequence[PricePoint],
    resolved_at: datetime,
    barrier_set: BarrierSet,
) -> FutureOutcomeLabel:
    feature_id = feature_row_id.strip()
    if not feature_id.startswith("feature:sha256:"):
        raise ValueError("feature_row_id must use feature:sha256:<digest>")
    digest = feature_id.removeprefix("feature:sha256:")
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("feature_row_id digest must be lowercase SHA-256")
    prediction = _utc(prediction_time, "prediction_time")
    end_at = horizon_end_at(prediction, horizon)
    resolved = _utc(resolved_at, "resolved_at")
    if resolved < end_at:
        raise ValueError("label cannot resolve before its horizon end")
    start = _finite_positive(start_price, "start_price")
    if not price_path:
        raise ValueError("price_path cannot be empty")
    ordered = tuple(sorted(price_path, key=lambda point: point.at))
    timestamps = [point.at for point in ordered]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("price_path timestamps must be unique")
    if any(point.at <= prediction for point in ordered):
        raise ValueError("future label price_path must be strictly after prediction_time")
    if any(point.at > end_at for point in ordered):
        raise ValueError("future label price_path cannot include points after horizon end")
    if ordered[-1].at != end_at:
        raise ValueError("price_path must contain an exact horizon-end price")

    prices = [start, *(point.price for point in ordered)]
    returns = [price / start - 1.0 for price in prices]
    future_return = prices[-1] / start - 1.0
    mfe = max(returns)
    mae = min(returns)

    log_returns = [math.log(prices[index] / prices[index - 1]) for index in range(1, len(prices))]
    realized_log_volatility = math.sqrt(sum(value * value for value in log_returns))

    running_peak = prices[0]
    maximum_drawdown = 0.0
    for price in prices[1:]:
        running_peak = max(running_peak, price)
        maximum_drawdown = min(maximum_drawdown, price / running_peak - 1.0)

    positive_touches = {
        _touch_key(threshold): mfe >= threshold for threshold in barrier_set.return_thresholds
    }
    negative_touches = {
        _touch_key(threshold): mae <= -threshold for threshold in barrier_set.return_thresholds
    }
    absolute_touches: dict[str, bool] = {}
    for barrier in barrier_set.absolute_prices:
        key = _touch_key(barrier)
        if start < barrier:
            absolute_touches[key] = max(prices) >= barrier
        elif start > barrier:
            absolute_touches[key] = min(prices) <= barrier
        else:
            absolute_touches[key] = True

    unsigned: dict[str, object] = {
        "feature_row_id": feature_id,
        "prediction_time": prediction.isoformat(),
        "horizon": horizon.value,
        "label_end_at": end_at.isoformat(),
        "resolved_at": resolved.isoformat(),
        "barrier_set_id": barrier_set.barrier_set_id,
        "start_price": start,
        "end_price": prices[-1],
        "future_return": future_return,
        "maximum_favorable_excursion": mfe,
        "maximum_adverse_excursion": mae,
        "realized_log_volatility": realized_log_volatility,
        "maximum_drawdown": maximum_drawdown,
        "positive_return_touches": positive_touches,
        "negative_return_touches": negative_touches,
        "absolute_price_touches": absolute_touches,
    }
    label_digest = sha256(_canonical(unsigned).encode()).hexdigest()
    return FutureOutcomeLabel(
        label_id=f"label:sha256:{label_digest}",
        label_sha256=label_digest,
        feature_row_id=feature_id,
        prediction_time=prediction,
        horizon=horizon,
        label_end_at=end_at,
        resolved_at=resolved,
        barrier_set_id=barrier_set.barrier_set_id,
        start_price=start,
        end_price=prices[-1],
        future_return=future_return,
        maximum_favorable_excursion=mfe,
        maximum_adverse_excursion=mae,
        realized_log_volatility=realized_log_volatility,
        maximum_drawdown=maximum_drawdown,
        positive_return_touches=positive_touches,
        negative_return_touches=negative_touches,
        absolute_price_touches=absolute_touches,
    )


class FutureLabelStoreV1:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.busy_timeout_ms = busy_timeout_ms
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level="DEFERRED",
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_store_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            role = connection.execute(
                "SELECT value FROM research_store_metadata WHERE key='store_role'"
            ).fetchone()
            if role is not None and str(role["value"]) != LABEL_STORE_ROLE:
                raise ValueError("database already belongs to a non-label research store")
            connection.execute(
                """
                INSERT INTO research_store_metadata(key, value) VALUES('store_role', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (LABEL_STORE_ROLE,),
            )
            connection.execute(
                """
                INSERT INTO research_store_metadata(key, value) VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(LABEL_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS future_outcome_labels(
                    label_id TEXT PRIMARY KEY,
                    label_sha256 TEXT NOT NULL UNIQUE,
                    feature_row_id TEXT NOT NULL,
                    prediction_time TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    label_end_at TEXT NOT NULL,
                    barrier_set_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_label_feature
                ON future_outcome_labels(feature_row_id, horizon)
                """
            )

    def save(self, label: FutureOutcomeLabel) -> None:
        payload = _canonical(label.to_payload())
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM future_outcome_labels WHERE label_id=?",
                (label.label_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_json"]) != payload:
                    raise ValueError("label_id collision with different payload")
                return
            connection.execute(
                """
                INSERT INTO future_outcome_labels(
                    label_id, label_sha256, feature_row_id, prediction_time,
                    horizon, label_end_at, barrier_set_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    label.label_id,
                    label.label_sha256,
                    label.feature_row_id,
                    label.prediction_time.isoformat(),
                    label.horizon.value,
                    label.label_end_at.isoformat(),
                    label.barrier_set_id,
                    payload,
                ),
            )

    def load(self, label_id: str) -> FutureOutcomeLabel | None:
        with self._connection() as connection:
            record = connection.execute(
                "SELECT payload_json FROM future_outcome_labels WHERE label_id=?",
                (label_id,),
            ).fetchone()
        if record is None:
            return None
        payload = json.loads(str(record["payload_json"]))
        if not isinstance(payload, dict):
            raise RuntimeError("stored label root must be an object")
        return FutureOutcomeLabel.from_payload(payload)

    def count(self) -> int:
        with self._connection() as connection:
            record = connection.execute(
                "SELECT COUNT(*) AS count FROM future_outcome_labels"
            ).fetchone()
        return int(record["count"])

    def table_names(self) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return tuple(str(row["name"]) for row in rows)
