"""Target URL validation and destination-address policy (SSRF defence).

Two layers use this module:

* The API validates user-supplied origins up front so obviously prohibited
  targets are rejected with a clear error.
* The worker's egress proxy calls :func:`resolve_and_check` for *every*
  connection the browser makes, so DNS answers are validated at connection time
  and the connection is pinned to the validated address (DNS rebinding cannot
  swap in a private address between check and use).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import SplitResult, urlsplit

MAX_URL_LENGTH = 2048

# Ranges that are not covered (or not reliably covered) by ipaddress.is_global.
_EXTRA_BLOCKED_NETS = [
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64 (embeds IPv4)
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("2002::/16"),  # 6to4 (embeds IPv4)
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local
]


class TargetRejected(ValueError):
    """Raised when a URL or destination is not permitted."""

    def __init__(self, reason: str, code: str = "target_rejected") -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class Origin:
    scheme: str
    host: str  # lowercase, IDNA-encoded
    port: int

    @property
    def default_port(self) -> bool:
        return (self.scheme, self.port) in {("http", 80), ("https", 443)}

    def __str__(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}" if self.default_port else f"{self.scheme}://{host}:{self.port}"

    @property
    def hostport(self) -> str:
        return f"{self.host}:{self.port}"


def _parse(url: str) -> SplitResult:
    if not isinstance(url, str) or not url.strip():
        raise TargetRejected("A URL is required.", "invalid_url")
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise TargetRejected("URL is too long.", "invalid_url")
    if any(ord(c) < 0x21 for c in url):
        raise TargetRejected("URL contains whitespace or control characters.", "invalid_url")
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises on invalid port
    except ValueError as exc:
        raise TargetRejected(f"URL could not be parsed: {exc}", "invalid_url") from exc
    if parts.scheme.lower() not in {"http", "https"}:
        raise TargetRejected("Only http:// and https:// URLs can be investigated.", "invalid_scheme")
    if parts.username is not None or parts.password is not None:
        raise TargetRejected("URLs must not embed credentials. Use the secure credential form.", "invalid_url")
    if not parts.hostname:
        raise TargetRejected("URL has no host.", "invalid_url")
    return parts


def normalize_host(host: str) -> str:
    host = host.strip().rstrip(".").lower()
    if not host:
        raise TargetRejected("URL has no host.", "invalid_url")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        encoded = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise TargetRejected("Host name is not valid.", "invalid_url") from exc
    labels = encoded.split(".")
    if any(not label or len(label) > 63 for label in labels) or len(encoded) > 253:
        raise TargetRejected("Host name is not valid.", "invalid_url")
    if not all(all(ch.isalnum() or ch == "-" for ch in label) for label in labels):
        raise TargetRejected("Host name contains invalid characters.", "invalid_url")
    return encoded


def parse_origin(url: str) -> Origin:
    """Parse any http(s) URL and return its normalized origin."""
    parts = _parse(url)
    scheme = parts.scheme.lower()
    host = normalize_host(parts.hostname or "")
    port = parts.port or (443 if scheme == "https" else 80)
    if not 1 <= port <= 65535:
        raise TargetRejected("Port is out of range.", "invalid_url")
    return Origin(scheme, host, port)


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when ``ip`` is not a public, globally routable unicast address."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_blocked_ip(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            return True
        if ip.teredo is not None:
            return True
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return True
    return any(ip in net for net in _EXTRA_BLOCKED_NETS if net.version == ip.version)


@dataclass
class EgressPolicy:
    """Destination policy enforced independently of any AI or crawler logic."""

    allowed_ports: frozenset[int] = frozenset({80, 443, 8080, 8443})
    # host:port pairs an operator explicitly permits despite private addresses.
    private_allowlist: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_origins(cls, allowed_ports: list[int], private_origins: list[str]) -> EgressPolicy:
        allow: set[str] = set()
        for raw in private_origins:
            o = parse_origin(raw)
            allow.add(o.hostport)
        return cls(allowed_ports=frozenset(allowed_ports), private_allowlist=frozenset(allow))

    def is_private_allowlisted(self, host: str, port: int) -> bool:
        return f"{normalize_host(host)}:{port}" in self.private_allowlist

    def check_port(self, host: str, port: int) -> None:
        if port in self.allowed_ports or self.is_private_allowlisted(host, port):
            return
        raise TargetRejected(f"Port {port} is not permitted for outbound connections.", "port_blocked")


@dataclass(frozen=True)
class ResolvedDestination:
    host: str
    port: int
    addresses: tuple[str, ...]
    allowlisted_private: bool


async def resolve_and_check(host: str, port: int, policy: EgressPolicy) -> ResolvedDestination:
    """Resolve ``host`` and verify every answer is permitted.

    All returned addresses must pass (a hostname with one public and one private
    record is rejected) so the caller can safely connect to any of them.
    """
    host = normalize_host(host)
    policy.check_port(host, port)
    allowlisted = policy.is_private_allowlisted(host, port)

    try:
        literal = ipaddress.ip_address(host)
        addrs = [literal]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await asyncio.wait_for(
                loop.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP), 5
            )
        except (OSError, TimeoutError) as exc:
            raise TargetRejected(f"Could not resolve {host}.", "dns_failure") from exc
        addrs = []
        for info in infos:
            raw = info[4][0]
            # Strip IPv6 zone identifiers ("fe80::1%eth0").
            addr = ipaddress.ip_address(raw.split("%", 1)[0])
            if addr not in addrs:
                addrs.append(addr)
        if not addrs:
            raise TargetRejected(f"Could not resolve {host}.", "dns_failure")

    if not allowlisted:
        for addr in addrs:
            if is_blocked_ip(addr):
                raise TargetRejected(
                    f"{host} resolves to a non-public address ({addr}). Internal, loopback, "
                    "link-local and metadata addresses cannot be investigated.",
                    "private_address",
                )
    return ResolvedDestination(host, port, tuple(str(a) for a in addrs), allowlisted)


async def validate_target_origin(url: str, policy: EgressPolicy) -> tuple[Origin, ResolvedDestination]:
    """API-side validation of a target origin supplied by a user."""
    origin = parse_origin(url)
    dest = await resolve_and_check(origin.host, origin.port, policy)
    return origin, dest
