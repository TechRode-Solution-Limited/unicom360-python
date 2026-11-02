"""The default urllib transport against a real local HTTP server."""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest

from unicom360 import (
    APIConnectionError,
    Request,
    TransportError,
    Unicom360,
    UrllibTransport,
)


class Handler(http.server.BaseHTTPRequestHandler):
    seen: ClassVar[list[dict[str, Any]]] = []

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _record(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        Handler.seen.append(
            {"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body}
        )
        return body

    def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for name, value in (headers or {"Content-Type": "application/json"}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._record()
        if self.path == "/health":
            self._send(200, b'{"status":"ok","timestamp":"t","version":"v","environment":"e"}')
        elif self.path == "/slow":
            time.sleep(1.5)
            self._send(200, b"{}")
        elif self.path == "/redirect":
            self._send(302, b"", {"Location": "/health"})
        elif self.path == "/reset":
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
        else:
            self._send(404, b'{"errors":{"detail":"Not Found"}}')

    def do_POST(self) -> None:
        body = self._record()
        payload = json.loads(body)
        reply = {
            "api_reference": "42",
            "message": "successful",
            "success": True,
            "data": [
                {"message_id": "m-1", "status": "ACKNOWLEDGED", "mobile_number": payload["to"]}
            ],
        }
        self._send(200, json.dumps(reply).encode())


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def request(url: str, method: str = "GET", timeout: float = 5.0) -> Request:
    return Request(
        method=method,
        url=url,
        headers={"Accept": "application/json", "X-API-Key": "k"},
        body=None,
        timeout=timeout,
        connect_timeout=2.0,
    )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def test_success_and_headers(server: str) -> None:
    response = UrllibTransport().send(request(f"{server}/health"))
    assert response.status == 200
    assert response.headers["content-type"] == "application/json"
    assert json.loads(response.body)["status"] == "ok"


def test_error_status_is_a_response(server: str) -> None:
    response = UrllibTransport().send(request(f"{server}/missing"))
    assert response.status == 404
    assert "Not Found" in response.body


def test_redirect_is_not_followed(server: str) -> None:
    Handler.seen.clear()
    response = UrllibTransport().send(request(f"{server}/redirect"))
    assert response.status == 302
    assert response.headers["location"] == "/health"
    assert [r["path"] for r in Handler.seen] == ["/redirect"]


def test_connection_refused_was_not_sent() -> None:
    with pytest.raises(TransportError) as caught:
        UrllibTransport().send(request(f"http://127.0.0.1:{free_port()}/health"))
    assert (caught.value.sent, caught.value.timeout) == (False, False)


def test_dns_failure_was_not_sent() -> None:
    with pytest.raises(TransportError) as caught:
        UrllibTransport().send(request("https://name-that-does-not-exist.invalid/health"))
    assert (caught.value.sent, caught.value.timeout) == (False, False)


def test_response_timeout_was_sent(server: str) -> None:
    with pytest.raises(TransportError) as caught:
        UrllibTransport().send(request(f"{server}/slow", timeout=0.3))
    assert (caught.value.sent, caught.value.timeout) == (True, True)


def test_reset_after_send_was_sent(server: str) -> None:
    with pytest.raises(TransportError) as caught:
        UrllibTransport().send(request(f"{server}/reset"))
    assert caught.value.sent is True
    assert caught.value.timeout is False


def test_client_end_to_end(server: str) -> None:
    Handler.seen.clear()
    client = Unicom360("secret-key", base_url=server)
    result = client.sms.send(from_="Unicom360", to="260971234567", message="Café €")
    assert result.api_reference == "42"
    assert result.results[0].mobile_number == "260971234567"
    [seen] = Handler.seen
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/json/bulk/sms"
    headers = {k.lower(): v for k, v in seen["headers"].items()}
    assert headers["x-api-key"] == "secret-key"
    assert headers["content-type"] == "application/json"
    assert headers["accept"] == "application/json"
    assert headers["user-agent"].startswith("unicom360-python/0.1.0 (")
    assert "authorization" not in headers
    assert json.loads(seen["body"]) == {
        "from": "Unicom360",
        "to": "260971234567",
        "message": "Café €",
    }
    assert client.health().status == "ok"


def test_client_connection_refused_is_retried_then_raised() -> None:
    sleeps: list[float] = []
    client = Unicom360(
        "k", base_url=f"http://127.0.0.1:{free_port()}", sleeper=sleeps.append, max_retries=2
    )
    with pytest.raises(APIConnectionError) as caught:
        client.sms.send(from_="U", to="260971234567", message="Hi")
    assert caught.value.sent is False
    assert caught.value.attempts == 3
    assert len(sleeps) == 2
