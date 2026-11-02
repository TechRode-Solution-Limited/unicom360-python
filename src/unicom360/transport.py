"""The HTTP transport seam.

A transport sends one request and returns the response, or raises :class:`TransportError`
saying whether any byte may have reached the server (``sent``) and whether it timed out
(``timeout``). The client decides about retries from those two facts.

The default, :class:`UrllibTransport`, uses only the standard library. Pass your own object
with a ``send(request) -> Response`` method to use another HTTP library, a proxy or a fake in
tests::

    class MyTransport:
        def send(self, request: Request) -> Response: ...

    client = Unicom360(transport=MyTransport())
"""

from __future__ import annotations

import http.client
import socket
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["Request", "Response", "Transport", "TransportError", "UrllibTransport"]


@dataclass(frozen=True)
class Request:
    """One HTTP request, as the client built it.

    ``headers`` include ``X-API-Key``: never log them.
    """

    method: str
    url: str
    headers: Mapping[str, str]
    #: UTF-8 JSON, or ``None`` for a request without a body.
    body: bytes | None
    #: Seconds from sending the request to receiving the whole body.
    timeout: float
    #: Seconds to establish the connection, TLS included.
    connect_timeout: float

    def __repr__(self) -> str:
        # The headers carry the API key; keep them out of every repr.
        return f"Request(method={self.method!r}, url={self.url!r}, headers=[REDACTED])"


@dataclass(frozen=True)
class Response:
    """One HTTP response: the status, the headers (names lower-cased) and the body text."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: str = ""


class TransportError(Exception):
    """A request that produced no complete response.

    Args:
        message: What happened.
        sent: Whether any byte of the request may have reached the server. When the
            underlying library cannot tell, say ``True``.
        timeout: Whether the failure was a timeout.
        cause: The underlying exception, if any.
    """

    def __init__(
        self,
        message: str,
        *,
        sent: bool,
        timeout: bool,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.sent = sent
        self.timeout = timeout
        self.cause = cause


@runtime_checkable
class Transport(Protocol):
    """Anything that can send a :class:`Request` and return a :class:`Response`."""

    def send(self, request: Request) -> Response:
        """Send ``request``. Raise :class:`TransportError` when no complete response arrives."""
        ...


# ---------------------------------------------------------------------------------------------
# The default transport on urllib.request
# ---------------------------------------------------------------------------------------------


class _Attempt:
    """What one request got to: whether it connected, and the socket it used.

    urllib drops the connection's own reference to the socket once the response headers are
    in, so the socket is kept here to bound the time spent reading the body.
    """

    def __init__(self) -> None:
        self.connected = False
        self.sock: socket.socket | None = None


def _timed_connect(
    connection: http.client.HTTPConnection,
    connect: Any,
    attempt: _Attempt | None,
    connect_timeout: float | None,
) -> None:
    """Connect within ``connect_timeout``, then give reads the connection's own timeout."""
    read_timeout = connection.timeout
    if connect_timeout is not None:
        connection.timeout = connect_timeout
    connect()
    connection.timeout = read_timeout
    if connection.sock is not None:
        connection.sock.settimeout(read_timeout)
    if attempt is not None:
        attempt.sock = connection.sock
        attempt.connected = True


class _HTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        *args: Any,
        attempt: _Attempt | None = None,
        connect_timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._attempt = attempt
        self._connect_timeout = connect_timeout

    def connect(self) -> None:
        _timed_connect(self, super().connect, self._attempt, self._connect_timeout)


class _HTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        *args: Any,
        attempt: _Attempt | None = None,
        connect_timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._attempt = attempt
        self._connect_timeout = connect_timeout

    def connect(self) -> None:
        _timed_connect(self, super().connect, self._attempt, self._connect_timeout)


class _HTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, attempt: _Attempt, connect_timeout: float) -> None:
        super().__init__()
        self._attempt = attempt
        self._connect_timeout = connect_timeout

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(
            _HTTPConnection, req, attempt=self._attempt, connect_timeout=self._connect_timeout
        )


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, attempt: _Attempt, connect_timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(context=context)
        self._attempt = attempt
        self._connect_timeout = connect_timeout
        self._ssl_context = context

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(
            _HTTPSConnection,
            req,
            context=self._ssl_context,
            attempt=self._attempt,
            connect_timeout=self._connect_timeout,
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: a 3xx comes back as a response, so the key never leaves."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _is_timeout(error: BaseException) -> bool:
    return isinstance(error, (socket.timeout, TimeoutError))


class UrllibTransport:
    """The default transport, on :mod:`urllib.request`.

    * The connection (TLS included) must be established within ``connect_timeout``, and the
      whole response must arrive within ``timeout`` of that.
    * Redirects are never followed.
    * Proxies from the usual environment variables (``HTTPS_PROXY``, ``NO_PROXY``) apply.

    Args:
        ssl_context: The TLS settings; by default :func:`ssl.create_default_context`.
    """

    def __init__(self, ssl_context: ssl.SSLContext | None = None) -> None:
        self._ssl_context = ssl_context or ssl.create_default_context()

    def __repr__(self) -> str:
        return "UrllibTransport()"

    def send(self, request: Request) -> Response:
        attempt = _Attempt()
        opener = urllib.request.build_opener(
            _NoRedirect(),
            _HTTPHandler(attempt, request.connect_timeout),
            _HTTPSHandler(attempt, request.connect_timeout, self._ssl_context),
        )
        native = urllib.request.Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method,
        )
        deadline = time.monotonic() + request.connect_timeout + request.timeout
        try:
            try:
                raw = opener.open(native, timeout=request.timeout)
            except urllib.error.HTTPError as error:
                # A non-2xx (or a 3xx we refused to follow) is still a response.
                raw = error
            with raw:
                status = int(raw.getcode())
                headers = _headers(raw.headers)
                body = _read(raw, attempt, deadline)
        except urllib.error.URLError as error:
            reason = error.reason
            cause = reason if isinstance(reason, BaseException) else error
            raise TransportError(
                f"Could not reach the Unicom360 API: {reason}",
                sent=attempt.connected,
                timeout=_is_timeout(cause),
                cause=cause,
            ) from error
        except (OSError, http.client.HTTPException) as error:
            raise TransportError(
                f"The connection to the Unicom360 API failed: {error!r}",
                sent=attempt.connected,
                timeout=_is_timeout(error),
                cause=error,
            ) from error
        return Response(status=status, headers=headers, body=body)


def _headers(message: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    if message is None:
        return headers
    for name, value in message.items():
        key = str(name).lower()
        headers[key] = f"{headers[key]}, {value}" if key in headers else str(value)
    return headers


def _read(raw: Any, attempt: _Attempt, deadline: float) -> str:
    """Read the whole body before ``deadline``, whatever pace the server sends it at."""
    chunks: list[bytes] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("timed out reading the response body")
        sock = attempt.sock
        if sock is not None and sock.fileno() != -1:
            # The response closes the socket once it has read a body of known length.
            sock.settimeout(remaining)
        chunk = raw.read(65536)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")
