"""Proof that the requester is authorized to investigate a target origin.

Supported methods:

* ``http_file`` — the origin serves ``/.well-known/webxray-verification.txt``
  containing the environment's verification token.
* ``dns_txt`` — a TXT record ``_webxray-verification.<host>`` contains
  ``webxray-verification=<token>``.
* ``operator_allowlist`` — the origin is listed in
  ``WEBXRAY_ALLOWED_PRIVATE_ORIGINS`` by the platform operator (used for the
  local benchmark app). This is a deployment-level decision, not a user one.

The HTTP fetch is SSRF-safe: the host is resolved and validated with the same
policy as the browser egress proxy, the socket is pinned to that address, and
redirects are not followed.
"""

from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass

import dns.asyncresolver
import dns.exception

from webxray.security.target_policy import EgressPolicy, Origin, TargetRejected, resolve_and_check

WELL_KNOWN_PATH = "/.well-known/webxray-verification.txt"
DNS_LABEL = "_webxray-verification"
MAX_BODY = 4096


@dataclass
class VerificationResult:
    verified: bool
    method: str | None
    detail: str


async def safe_get(origin: Origin, path: str, policy: EgressPolicy, timeout: float = 8.0) -> tuple[int, bytes]:
    dest = await resolve_and_check(origin.host, origin.port, policy)
    ssl_ctx = ssl.create_default_context() if origin.scheme == "https" else None
    last: Exception | None = None
    for addr in dest.addresses:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    addr,
                    origin.port,
                    ssl=ssl_ctx,
                    server_hostname=origin.host if ssl_ctx else None,
                ),
                timeout,
            )
            break
        except (OSError, TimeoutError, ssl.SSLError) as exc:
            last = exc
    else:
        raise TargetRejected(f"Could not connect to {origin}: {last}", "connect_failed")

    host_header = origin.host if origin.default_port else f"{origin.host}:{origin.port}"
    request = (
        f"GET {path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: WEB-X-RAY-Verifier/0.1\r\n"
        "Accept: text/plain\r\nConnection: close\r\n\r\n"
    )
    try:
        writer.write(request.encode("ascii"))
        await writer.drain()
        raw = b""
        while len(raw) < MAX_BODY + 8192:
            chunk = await asyncio.wait_for(reader.read(4096), timeout)
            if not chunk:
                break
            raw += chunk
    finally:
        writer.close()

    head, _, body = raw.partition(b"\r\n\r\n")
    try:
        status = int(head.split(b" ", 2)[1])
    except (IndexError, ValueError) as exc:
        raise TargetRejected("Verification endpoint returned an invalid response.", "bad_response") from exc
    if b"transfer-encoding: chunked" in head.lower():
        body = _dechunk(body)
    return status, body[:MAX_BODY]


def _dechunk(data: bytes) -> bytes:
    out = b""
    while data:
        size_line, _, rest = data.partition(b"\r\n")
        try:
            size = int(size_line.split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        out += rest[:size]
        data = rest[size + 2 :]
    return out


async def verify_http_file(origin: Origin, token: str, policy: EgressPolicy) -> VerificationResult:
    try:
        status, body = await safe_get(origin, WELL_KNOWN_PATH, policy)
    except TargetRejected as exc:
        return VerificationResult(False, None, exc.reason)
    if status != 200:
        return VerificationResult(False, None, f"{WELL_KNOWN_PATH} returned HTTP {status}.")
    if token in body.decode("utf-8", "replace").split():
        return VerificationResult(True, "http_file", f"Token found at {origin}{WELL_KNOWN_PATH}.")
    return VerificationResult(False, None, f"{WELL_KNOWN_PATH} does not contain this project's token.")


async def verify_dns_txt(origin: Origin, token: str) -> VerificationResult:
    name = f"{DNS_LABEL}.{origin.host}"
    try:
        answer = await dns.asyncresolver.resolve(name, "TXT", lifetime=5)
    except (dns.exception.DNSException, OSError) as exc:
        return VerificationResult(False, None, f"No TXT record at {name} ({exc.__class__.__name__}).")
    expected = f"webxray-verification={token}"
    for rdata in answer:
        txt = b"".join(rdata.strings).decode("utf-8", "replace")
        if txt.strip() == expected:
            return VerificationResult(True, "dns_txt", f"TXT record found at {name}.")
    return VerificationResult(False, None, f"TXT record at {name} does not contain the expected value.")


async def verify_environment(origin: Origin, token: str, policy: EgressPolicy) -> VerificationResult:
    if policy.is_private_allowlisted(origin.host, origin.port):
        return VerificationResult(
            True, "operator_allowlist", "Origin is allowlisted by the platform operator configuration."
        )
    http_result = await verify_http_file(origin, token, policy)
    if http_result.verified:
        return http_result
    dns_result = await verify_dns_txt(origin, token)
    if dns_result.verified:
        return dns_result
    return VerificationResult(False, None, f"{http_result.detail} {dns_result.detail}")
