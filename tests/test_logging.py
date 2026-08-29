import json
import logging

from xrp_regime_engine.logging import JsonFormatter, redact_secrets


def test_redact_secrets_covers_headers_query_and_key_values() -> None:
    text = (
        "Bearer abc.def token=TOKEN123 "
        "https://example.test/path?api_key=SECRET&x=1 password:pass"
    )
    redacted = redact_secrets(text)
    assert "abc.def" not in redacted
    assert "TOKEN123" not in redacted
    assert "SECRET" not in redacted
    assert "password=***" in redacted


def test_json_formatter_never_serializes_secret_message() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="authorization=super-secret",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "authorization=***"
