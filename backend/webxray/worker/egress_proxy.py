"""Per-investigation egress proxy.

Chromium is launched with this proxy as its only route to the network. For
every request (plain HTTP or CONNECT tunnel) the proxy:

1. authenticates the browser with a per-instance random credential,
2. resolves the destination host and validates *every* answer against the
   :class:`EgressPolicy` (no loopback/private/link-local/metadata addresses
   unless explicitly allowlisted by the operator),
3. connects to the validated IP itself, pinning the connection so DNS
   rebinding cannot redirect it, and
4. enforces a byte budget for the whole investigation.

This runs regardless of what the crawler, journey engine or any AI component
decides — page content cannot talk its way past it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from webxray.security.target_policy import EgressPolicy, TargetRejected, resolve_and_check

log = logging.getLogger(__name__)

MAX_HEAD_BYTES = 64 * 1024
IDLE_TIMEOUT_S = 60.0
CONNECT_TIMEOUT_S = 10.0


@dataclass
class EgressDecision:
    host: str
    port: int
    allowed: bool
    reason: str
    method: str


@dataclass
class EgressStats:
    bytes_up: int = 0
    bytes_down: int = 0
    connections: int = 0
    denied: list[EgressDecision] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return self.bytes_up + self.bytes_down


class EgressProxy:
    def __init__(
        self,
        policy: EgressPolicy,
        *,
        byte_budget: int = 512 * 1024 * 1024,
        on_denied: Callable[[EgressDecision], None] | None = None,
    ) -> None:
        self.policy = policy
        self.byte_budget = byte_budget
        self.on_denied = on_denied
        self.stats = EgressStats()
        self.username = "wx"
        self.password = secrets.token_urlsafe(18)
        self._expected_auth = "Basic " + base64.b64encode(
            f"{self.username}:{self.password}".encode()
        ).decode()
        self._server: asyncio.base_events.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.port: int = 0

    @property
    def server_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> EgressProxy:
        self._server = await asyncio.start_server(self._handle, host="127.0.0.1", port=0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), 2)
        for task in list(self._tasks):
            task.cancel()
        self._server = None

    async def __aenter__(self) -> EgressProxy:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    # ------------------------------------------------------------------ internals

    def _deny(self, host: str, port: int, method: str, reason: str) -> None:
        decision = EgressDecision(host, port, False, reason, method)
        self.stats.denied.append(decision)
        log.info("egress denied %s %s:%s — %s", method, host, port, reason)
        if self.on_denied is not None:
            try:
                self.on_denied(decision)
            except Exception:  # pragma: no cover - callback must never break the proxy
                log.exception("egress on_denied callback failed")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await self._serve(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError, TimeoutError, asyncio.LimitOverrunError):
            pass
        except asyncio.CancelledError:
            pass
        except Exception:  # pragma: no cover
            log.exception("egress proxy connection failed")
        finally:
            with contextlib.suppress(Exception):
                writer.close()
            if task is not None:
                self._tasks.discard(task)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), IDLE_TIMEOUT_S)
        if len(head) > MAX_HEAD_BYTES:
            await _respond(writer, 431, "Request Header Fields Too Large")
            return
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            await _respond(writer, 400, "Bad Request")
            return
        headers = [line for line in lines[1:] if line]
        auth = next(
            (h.split(":", 1)[1].strip() for h in headers if h.lower().startswith("proxy-authorization:")),
            None,
        )
        if auth is None or not secrets.compare_digest(auth, self._expected_auth):
            await _respond(
                writer, 407, "Proxy Authentication Required", extra=['Proxy-Authenticate: Basic realm="webxray"']
            )
            return

        if self.stats.total_bytes >= self.byte_budget:
            self._deny("*", 0, method, "investigation bandwidth budget exhausted")
            await _respond(writer, 403, "Forbidden", body=b"WEB X-RAY: bandwidth budget exhausted")
            return

        if method.upper() == "CONNECT":
            host, _, port_s = target.rpartition(":")
            host = host.strip("[]")
            try:
                port = int(port_s)
            except ValueError:
                await _respond(writer, 400, "Bad Request")
                return
            upstream = await self._open_upstream(host, port, method, writer)
            if upstream is None:
                return
            up_reader, up_writer = upstream
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await self._pipe_both(reader, writer, up_reader, up_writer)
            return

        # Plain HTTP: absolute-form request line.
        parts = urlsplit(target)
        if parts.scheme.lower() != "http" or not parts.hostname:
            await _respond(writer, 400, "Bad Request")
            return
        port = parts.port or 80
        upstream = await self._open_upstream(parts.hostname, port, method, writer)
        if upstream is None:
            return
        up_reader, up_writer = upstream
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        forwarded = [f"{method} {path} {version}"]
        for h in headers:
            name = h.split(":", 1)[0].strip().lower()
            if name in {"proxy-authorization", "proxy-connection", "connection", "keep-alive"}:
                continue
            forwarded.append(h)
        forwarded.append("Connection: close")
        up_writer.write(("\r\n".join(forwarded) + "\r\n\r\n").encode("latin-1"))
        await up_writer.drain()
        await self._pipe_both(reader, writer, up_reader, up_writer)

    async def _open_upstream(
        self, host: str, port: int, method: str, writer: asyncio.StreamWriter
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter] | None:
        try:
            dest = await resolve_and_check(host, port, self.policy)
        except TargetRejected as exc:
            self._deny(host, port, method, exc.reason)
            await _respond(
                writer,
                403,
                "Forbidden",
                extra=["X-WebXray-Egress: denied"],
                body=f"WEB X-RAY egress policy blocked this request: {exc.reason}".encode(),
            )
            return None
        last_exc: Exception | None = None
        for addr in dest.addresses:
            try:
                up = await asyncio.wait_for(asyncio.open_connection(addr, port), CONNECT_TIMEOUT_S)
                self.stats.connections += 1
                return up
            except (OSError, TimeoutError) as exc:
                last_exc = exc
        log.info("egress upstream connect failed %s:%s — %s", host, port, last_exc)
        await _respond(writer, 502, "Bad Gateway")
        return None

    async def _pipe_both(
        self,
        c_reader: asyncio.StreamReader,
        c_writer: asyncio.StreamWriter,
        u_reader: asyncio.StreamReader,
        u_writer: asyncio.StreamWriter,
    ) -> None:
        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter, up: bool) -> None:
            try:
                while True:
                    chunk = await asyncio.wait_for(src.read(64 * 1024), IDLE_TIMEOUT_S)
                    if not chunk:
                        break
                    if up:
                        self.stats.bytes_up += len(chunk)
                    else:
                        self.stats.bytes_down += len(chunk)
                    if self.stats.total_bytes > self.byte_budget:
                        self._deny("*", 0, "STREAM", "investigation bandwidth budget exhausted")
                        break
                    dst.write(chunk)
                    await dst.drain()
            except (ConnectionError, TimeoutError, asyncio.CancelledError):
                pass
            finally:
                with contextlib.suppress(Exception):
                    if dst.can_write_eof():
                        dst.write_eof()

        up_task = asyncio.create_task(pipe(c_reader, u_writer, True))
        down_task = asyncio.create_task(pipe(u_reader, c_writer, False))
        try:
            # The response direction finishing ends the exchange.
            await down_task
        finally:
            up_task.cancel()
            with contextlib.suppress(Exception):
                u_writer.close()


async def _respond(
    writer: asyncio.StreamWriter,
    status: int,
    reason: str,
    *,
    extra: list[str] | None = None,
    body: bytes = b"",
) -> None:
    lines = [f"HTTP/1.1 {status} {reason}", "Connection: close", f"Content-Length: {len(body)}"]
    if body:
        lines.append("Content-Type: text/plain; charset=utf-8")
    lines.extend(extra or [])
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)
    with contextlib.suppress(Exception):
        await writer.drain()
