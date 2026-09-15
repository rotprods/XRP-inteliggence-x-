from __future__ import annotations

import os
import random
import socket
import time
from collections.abc import Iterator

import numpy as np
import pytest



try:
    from hypothesis import HealthCheck, settings as hypothesis_settings
except ImportError:  # local recovery runtimes may not have optional Q1 tooling installed
    hypothesis_settings = None
else:
    hypothesis_settings.register_profile(
        "fast",
        max_examples=100,
        derandomize=True,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    hypothesis_settings.register_profile(
        "deep",
        max_examples=500,
        derandomize=False,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    hypothesis_settings.register_profile(
        "release",
        max_examples=1000,
        derandomize=False,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )

SENSITIVE_ENV = {
    "FRED_API_KEY",
    "MARKET_DATA_VENDOR_API_KEY",
    "ALERT_WEBHOOK_URL",
    "BINANCE_API_KEY",
    "COINBASE_API_KEY",
    "KRAKEN_API_KEY",
    "KUCOIN_API_KEY",
    "XRPL_SEED",
    "XRP_PRIVATE_KEY",
}
PROXY_ENV = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--allow-network",
        action="store_true",
        default=False,
        help="allow real outbound network for explicitly marked live tests",
    )




def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deterministically permute test order when the flake gate supplies a seed."""

    seed_value = os.environ.get("Q1_TEST_ORDER_SEED")
    if seed_value is None:
        return
    try:
        seed = int(seed_value)
    except ValueError as exc:
        raise pytest.UsageError("Q1_TEST_ORDER_SEED must be an integer") from exc
    random.Random(seed).shuffle(items)

def pytest_configure(config: pytest.Config) -> None:
    for marker in (
        "unit: isolated deterministic behavior",
        "property: generated invariant/property test",
        "contract: data/provider/API contract test",
        "integration: multi-component test without external network",
        "temporal: timestamp/cadence/revision correctness",
        "storage: persistence/fault-injection test",
        "security: adversarial security boundary test",
        "api: HTTP/API contract test",
        "research: backtest/leakage/research-integrity test",
        "packaging: build/install/reproducibility test",
        "slow: deterministic but expensive suite",
        "live: real provider/network test; never automatic",
        "allow_network: explicitly opts a test into network when --allow-network is supplied",
    ):
        config.addinivalue_line("markers", marker)


@pytest.fixture(autouse=True)
def deterministic_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make tests deterministic and scrub inherited credentials/proxies."""

    for key in SENSITIVE_ENV | PROXY_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    if hasattr(time, "tzset"):
        time.tzset()

    py_state = random.getstate()
    np_state = np.random.get_state()
    random.seed(0)
    np.random.seed(0)
    try:
        yield
    finally:
        random.setstate(py_state)
        np.random.set_state(np_state)


@pytest.fixture(autouse=True)
def deny_unexpected_network(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Deny real network by default while leaving mock transports untouched."""

    wants_network = request.node.get_closest_marker("allow_network") is not None
    if wants_network and request.config.getoption("--allow-network"):
        yield
        return

    def blocked(*args: object, **kwargs: object) -> object:
        raise RuntimeError(
            "unexpected network access during hermetic tests; use fixtures/mock transports "
            "or mark live+allow_network and pass --allow-network explicitly"
        )

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    # DNS is network-adjacent and can leak outside hermetic CI. Provider tests using
    # MockTransport bypass provider DNS resolution; dedicated DNS tests monkeypatch
    # getaddrinfo to deterministic fixture values after this fixture runs.
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield
