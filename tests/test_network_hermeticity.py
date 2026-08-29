from __future__ import annotations

import socket

import pytest

pytestmark = [pytest.mark.security, pytest.mark.unit]


def test_real_socket_access_is_denied_by_default() -> None:
    with pytest.raises(RuntimeError, match="unexpected network access"):
        socket.create_connection(("example.com", 443), timeout=0.01)


def test_real_dns_access_is_denied_by_default() -> None:
    with pytest.raises(RuntimeError, match="unexpected network access"):
        socket.getaddrinfo("example.com", 443)
