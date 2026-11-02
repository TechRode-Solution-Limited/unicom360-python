"""The webhook examples, driven with signed deliveries through each framework's test client."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

EXAMPLES = Path(__file__).parent.parent / "examples"
SECRET = "_p_1O9_F0Ntqznvs5yv1hE8-EVvIBFrIt10-7xoqVB8"
BODY = b'{"created_at":"2026-10-24T09:30:00Z","data":{"message":"hi"},"event":"webhook.test"}'


def load_example(name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("UNICOM360_WEBHOOK_SECRET", SECRET)
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signed_headers(body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    digest = hmac.new(SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return {
        "Content-Type": "application/json",
        "X-Unicom360-Event": "webhook.test",
        "X-Unicom360-Delivery": "3001",
        "X-Unicom360-Timestamp": timestamp,
        "X-Unicom360-Signature": f"sha256={digest.hexdigest()}",
    }


def test_flask_example(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("flask")
    app: Any = load_example("webhook_flask", monkeypatch).app
    client = app.test_client()
    url = "/webhooks/unicom360/whatsapp"
    assert client.post(url, data=BODY, headers=signed_headers(BODY)).status_code == 200
    # A repeat of the same delivery is acknowledged and dropped.
    assert client.post(url, data=BODY, headers=signed_headers(BODY)).status_code == 200
    tampered = client.post(url, data=BODY + b" ", headers=signed_headers(BODY))
    assert tampered.status_code == 401
    assert tampered.get_data(as_text=True) == "signature_mismatch"
    report = b'{"message_id":48213,"status":"DELIVERED","email_address":"j@e.com","message":"ok"}'
    assert client.post("/webhooks/unicom360/email", data=report).status_code == 200


def test_fastapi_example(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    client = TestClient(load_example("webhook_fastapi", monkeypatch).app)
    url = "/webhooks/unicom360/whatsapp"
    assert client.post(url, content=BODY, headers=signed_headers(BODY)).status_code == 200
    headers = signed_headers(BODY)
    del headers["X-Unicom360-Signature"]
    missing = client.post(url, content=BODY, headers=headers)
    assert missing.status_code == 401
    assert missing.text == "missing_signature"
