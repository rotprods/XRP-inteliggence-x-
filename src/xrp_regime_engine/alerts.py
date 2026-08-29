from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from xrp_regime_engine.models import AlertEvent, RegimeSnapshot


class AlertRegistry:
    def __init__(self, cooldown: timedelta = timedelta(hours=4)) -> None:
        self.cooldown = cooldown
        self._last_sent: dict[str, datetime] = {}

    def evaluate(self, snapshot: RegimeSnapshot) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        rules: list[tuple[str, bool, str, str]] = [
            (
                "regime_strong_bull",
                not snapshot.output_blocked
                and snapshot.bull_score >= 72
                and snapshot.directional_conviction >= 0.35,
                "high",
                "XRP entered strong-bull regime",
            ),
            (
                "distribution_risk",
                not snapshot.output_blocked and snapshot.distribution_risk >= 75,
                "high",
                "XRP distribution risk is elevated",
            ),
            (
                "data_degraded",
                snapshot.output_blocked,
                "critical",
                "XRP engine output is blocked by data-quality gates",
            ),
        ]
        now = datetime.now(UTC)
        for rule_id, condition, severity, summary in rules:
            if not condition:
                continue
            dedupe_key = f"{rule_id}:{snapshot.asset}:{snapshot.horizon.value}"
            last = self._last_sent.get(dedupe_key)
            if last and now - last < self.cooldown:
                continue
            self._last_sent[dedupe_key] = now
            alert_id = hashlib.sha256(f"{dedupe_key}:{now.isoformat()}".encode()).hexdigest()[:16]
            events.append(AlertEvent(
                alert_id=alert_id, created_at=now, severity=severity, rule_id=rule_id,
                asset=snapshot.asset, horizon=snapshot.horizon, summary=summary,
                dedupe_key=dedupe_key, payload=snapshot.model_dump(mode="json"),
            ))
        return events
