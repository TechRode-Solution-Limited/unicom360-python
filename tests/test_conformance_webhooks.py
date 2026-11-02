"""webhooks/signatures.json and webhooks/events.json."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from tests.harness import assert_canonical_equal, canonical, check_keys, vectors
from unicom360 import SignatureVerificationError, webhooks

EVENT_MODELS = {
    "message_status": webhooks.MessageStatusEvent,
    "message_received": webhooks.MessageReceivedEvent,
    "test": webhooks.TestEvent,
    "unknown": webhooks.UnknownEvent,
}


def header_variants(headers: dict[str, str]) -> list[Any]:
    """The same headers as a dict and as a list of pairs (as ASGI and WSGI hand them over)."""
    return [dict(headers), list(headers.items())]


@pytest.mark.parametrize("vector", vectors("webhooks/signatures.json"))
def test_signature(vector: dict[str, Any]) -> None:
    check_keys(
        vector,
        (
            "id",
            "description",
            "secret",
            "headers",
            "body_base64",
            "body_text",
            "now_unix",
            "tolerance",
            "expect",
        ),
        (),
    )
    body = base64.b64decode(vector["body_base64"])
    assert body == vector["body_text"].encode("utf-8")
    expect = vector["expect"]
    for raw_body in (body, vector["body_text"]):
        for headers in header_variants(vector["headers"]):
            args = (raw_body, headers, vector["secret"], vector["tolerance"], vector["now_unix"])
            if expect["valid"]:
                check_keys(expect, ("valid",), ())
                webhooks.verify(*args)
            else:
                check_keys(expect, ("valid", "reason"), ())
                with pytest.raises(SignatureVerificationError) as caught:
                    webhooks.verify(*args)
                assert caught.value.reason == expect["reason"]
                assert caught.value.type == "signature_verification_error"
                assert vector["secret"] not in str(caught.value)


@pytest.mark.parametrize("vector", vectors("webhooks/events.json"))
def test_event(vector: dict[str, Any]) -> None:
    check_keys(
        vector,
        ("id", "secret", "headers", "body_text", "now_unix", "tolerance", "expect"),
        ("description",),
    )
    expect = vector["expect"]
    check_keys(expect, ("kind", "event", "delivery_id", "created_at", "data"), ())
    assert expect["kind"] in EVENT_MODELS, f"unknown event kind {expect['kind']!r}"

    for headers in header_variants(vector["headers"]):
        event = webhooks.construct_event(
            vector["body_text"].encode("utf-8"),
            headers,
            vector["secret"],
            vector["tolerance"],
            vector["now_unix"],
        )
        assert type(event) is EVENT_MODELS[expect["kind"]]
        assert event.kind == expect["kind"]
        assert event.event == expect["event"]
        assert event.delivery_id == expect["delivery_id"]
        assert event.created_at == expect["created_at"]
        assert_canonical_equal(expect["data"], canonical(event.data))
