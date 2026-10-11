from __future__ import annotations

import asyncio
import base64
import ipaddress

import pytest

from webxray.security.crypto import (
    TestAccountSecret,
    decrypt_credential,
    encrypt_credential,
    sign_evidence_link,
    verify_evidence_link,
)
from webxray.security.redaction import Redactor, redact_text, redact_url
from webxray.security.target_policy import (
    EgressPolicy,
    TargetRejected,
    is_blocked_ip,
    parse_origin,
    resolve_and_check,
)
from webxray.worker.egress_proxy import EgressProxy

# ----------------------------------------------------------------- URL parsing


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://Example.COM/path?q=1", "https://example.com"),
        ("http://example.com:80/", "http://example.com"),
        ("https://example.com:8443", "https://example.com:8443"),
        ("https://bücher.example/", "https://xn--bcher-kva.example"),
        ("http://127.0.0.1:4100/x", "http://127.0.0.1:4100"),
    ],
)
def test_parse_origin_normalizes(url: str, expected: str) -> None:
    assert str(parse_origin(url)) == expected


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:pass@example.com",
        "https://",
        "https://exa mple.com",
        "https://example.com:99999",
        "",
        "https://ex_ample.com",
    ],
)
def test_parse_origin_rejects_invalid(url: str) -> None:
    with pytest.raises(TargetRejected):
        parse_origin(url)


# ----------------------------------------------------------------- IP policy


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "::1",
        "fd00:ec2::254",  # AWS IPv6 metadata (ULA)
        "fe80::1",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:169.254.169.254",
        "64:ff9b::a9fe:a9fe",  # NAT64 of 169.254.169.254
        "2002:7f00:1::",  # 6to4 of 127.0.0.1
        "224.0.0.1",
    ],
)
def test_blocked_ips(ip: str) -> None:
    assert is_blocked_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize("ip", ["93.184.215.14", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_ips_allowed(ip: str) -> None:
    assert not is_blocked_ip(ipaddress.ip_address(ip))


async def test_resolve_rejects_loopback_names_and_numeric_forms() -> None:
    policy = EgressPolicy()
    for host in ["localhost", "127.0.0.1", "2130706433", "0x7f000001", "[::1]"]:
        with pytest.raises(TargetRejected):
            await resolve_and_check(host.strip("[]"), 80, policy)


async def test_resolve_rejects_disallowed_port() -> None:
    with pytest.raises(TargetRejected) as exc:
        await resolve_and_check("1.1.1.1", 22, EgressPolicy())
    assert exc.value.code == "port_blocked"


async def test_operator_allowlist_is_exact_host_and_port() -> None:
    policy = EgressPolicy.from_origins([80, 443], ["http://127.0.0.1:4100"])
    dest = await resolve_and_check("127.0.0.1", 4100, policy)
    assert dest.allowlisted_private
    with pytest.raises(TargetRejected):
        await resolve_and_check("127.0.0.1", 4101, policy)
    with pytest.raises(TargetRejected):
        await resolve_and_check("127.0.0.2", 4100, policy)


# ----------------------------------------------------------------- redaction


def test_redaction_patterns() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    text = f"token={jwt} Authorization: Bearer abcdefghijklmnop password: hunter22 card 4242 4242 4242 4242"
    out, rules = redact_text(text)
    assert jwt not in out
    assert "abcdefghijklmnop" not in out
    assert "hunter22" not in out
    assert "4242 4242 4242 4242" not in out
    assert {"jwt", "bearer", "kv_secret", "card_number"} <= set(rules)


def test_redaction_keeps_non_card_numbers() -> None:
    # 13-digit millisecond timestamp — fails Luhn, must survive.
    out, _ = redact_text("ts=1760000000001")
    assert "1760000000001" in out


def test_known_secret_redaction_and_deep() -> None:
    r = Redactor(["S3cr3t-Value!"])
    assert "S3cr3t-Value!" not in r.text("typed S3cr3t-Value! into field")
    data = r.deep({"a": ["x S3cr3t-Value! y"], "password": "anything", "nested": {"cookie": "c"}})
    assert data == {"a": ["x [REDACTED] y"], "password": "[REDACTED]", "nested": {"cookie": "[REDACTED]"}}


def test_redact_url() -> None:
    out = redact_url("https://u:p@example.com/cb?code=abc&page=2&access_token=xyz#token=1")
    assert "abc" not in out and "xyz" not in out and "u:p" not in out
    assert "page=2" in out


# ----------------------------------------------------------------- crypto


def test_credential_round_trip_and_ciphertext_has_no_plaintext() -> None:
    secret = TestAccountSecret("qa@example.test", "pw-very-secret-123")
    blob = encrypt_credential(secret)
    assert b"pw-very-secret-123" not in blob and b"qa@example.test" not in blob
    assert decrypt_credential(blob) == secret


def test_evidence_link_signature() -> None:
    exp, sig = sign_evidence_link("abc")
    assert verify_evidence_link("abc", exp, sig)
    assert not verify_evidence_link("abd", exp, sig)
    assert not verify_evidence_link("abc", exp + 1, sig)
    assert not verify_evidence_link("abc", 1, sig)  # expired


# ----------------------------------------------------------------- egress proxy


async def _http_server() -> tuple[asyncio.base_events.Server, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        body = b"hello from upstream"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def _proxy_get(proxy: EgressProxy, url: str, *, auth: bool = True) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    lines = [f"GET {url} HTTP/1.1", "Host: x"]
    if auth:
        token = base64.b64encode(f"{proxy.username}:{proxy.password}".encode()).decode()
        lines.append(f"Proxy-Authorization: Basic {token}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(-1), 5)
    writer.close()
    return data


async def test_proxy_blocks_private_destination_and_records_it() -> None:
    server, port = await _http_server()
    denied = []
    async with EgressProxy(EgressPolicy(), on_denied=denied.append) as proxy:
        resp = await _proxy_get(proxy, f"http://127.0.0.1:{port}/")
    server.close()
    assert resp.startswith(b"HTTP/1.1 403")
    assert b"upstream" not in resp
    assert denied and denied[0].host == "127.0.0.1"


async def test_proxy_allows_allowlisted_origin() -> None:
    server, port = await _http_server()
    policy = EgressPolicy.from_origins([80, 443], [f"http://127.0.0.1:{port}"])
    async with EgressProxy(policy) as proxy:
        resp = await _proxy_get(proxy, f"http://127.0.0.1:{port}/")
        assert resp.startswith(b"HTTP/1.1 200")
        assert b"hello from upstream" in resp
        assert proxy.stats.bytes_down > 0
    server.close()


async def test_proxy_requires_its_credential() -> None:
    server, port = await _http_server()
    policy = EgressPolicy.from_origins([80, 443], [f"http://127.0.0.1:{port}"])
    async with EgressProxy(policy) as proxy:
        resp = await _proxy_get(proxy, f"http://127.0.0.1:{port}/", auth=False)
    server.close()
    assert resp.startswith(b"HTTP/1.1 407")


async def test_proxy_blocks_connect_to_metadata() -> None:
    async with EgressProxy(EgressPolicy()) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        token = base64.b64encode(f"{proxy.username}:{proxy.password}".encode()).decode()
        writer.write(
            f"CONNECT 169.254.169.254:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode()
        )
        await writer.drain()
        resp = await asyncio.wait_for(reader.read(-1), 5)
        writer.close()
    assert resp.startswith(b"HTTP/1.1 403")


async def test_proxy_enforces_byte_budget() -> None:
    server, port = await _http_server()
    policy = EgressPolicy.from_origins([80, 443], [f"http://127.0.0.1:{port}"])
    async with EgressProxy(policy, byte_budget=10) as proxy:
        await _proxy_get(proxy, f"http://127.0.0.1:{port}/")
        resp = await _proxy_get(proxy, f"http://127.0.0.1:{port}/")
    server.close()
    assert resp.startswith(b"HTTP/1.1 403")
