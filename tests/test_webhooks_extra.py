"""Webhook and builder behaviour beyond the fixtures."""

from __future__ import annotations

import email.message
import hashlib
import hmac
import time
from typing import Any

import pytest

from unicom360 import (
    SignatureVerificationError,
    TemplateBody,
    TemplateButton,
    TemplateHeader,
    TemplateRecipient,
    Unicom360Error,
    gsm,
    session,
    webhooks,
)

SECRET = "krISEvfh1iUWHg5sdWQd0ZnOvE6D6mrCsuFLNEuhGfI"


def signed(body: bytes, timestamp: int) -> dict[str, str]:
    digest = hmac.new(SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return {
        "X-Unicom360-Timestamp": str(timestamp),
        "X-Unicom360-Signature": f"sha256={digest}",
        "X-Unicom360-Delivery": "77",
    }


def test_now_defaults_to_the_system_clock() -> None:
    body = b'{"event":"webhook.test","created_at":"x","data":{"message":"hi"}}'
    event = webhooks.construct_event(body, signed(body, int(time.time())), SECRET)
    assert isinstance(event, webhooks.TestEvent)
    assert event.data.message == "hi"
    with pytest.raises(SignatureVerificationError) as caught:
        webhooks.verify(body, signed(body, int(time.time()) - 3600), SECRET)
    assert caught.value.reason == "timestamp_out_of_tolerance"


def test_header_collections() -> None:
    body = b'{"event":"x.y","data":{"a":1}}'
    headers = signed(body, 1000)
    message = email.message.Message()
    for name, value in headers.items():
        message[name.lower()] = value
    as_bytes = [(k.encode(), v.encode()) for k, v in headers.items()]
    as_lists = {k: [v, "ignored"] for k, v in headers.items()}
    for collection in (message, as_bytes, as_lists):
        event: Any = webhooks.construct_event(body, collection, SECRET, now=1000)
        assert isinstance(event, webhooks.UnknownEvent)
        assert event.delivery_id == "77"
        assert event.data == {"a": 1}


def test_missing_delivery_header_is_none() -> None:
    body = b'{"event":"webhook.test","data":{}}'
    headers = signed(body, 1000)
    del headers["X-Unicom360-Delivery"]
    event = webhooks.construct_event(body, headers, SECRET, now=1000)
    assert event.delivery_id is None
    assert event.created_at is None


@pytest.mark.parametrize("body", [b"not json", b"[1]", b'{"event": 5}', b'{"data": {}}', b"\xff"])
def test_bad_payload_after_a_valid_signature(body: bytes) -> None:
    with pytest.raises(Unicom360Error) as caught:
        webhooks.construct_event(body, signed(body, 1000), SECRET, now=1000)
    assert not isinstance(caught.value, SignatureVerificationError)


def test_timestamp_beyond_int64_is_out_of_tolerance() -> None:
    headers = signed(b"{}", 1000)
    headers["X-Unicom360-Timestamp"] = "99999999999999999999"
    with pytest.raises(SignatureVerificationError) as caught:
        webhooks.verify(b"{}", headers, SECRET, now=1000)
    assert caught.value.reason == "timestamp_out_of_tolerance"


def test_secret_as_bytes() -> None:
    body = b"{}"
    webhooks.verify(body, signed(body, 1000), SECRET.encode(), now=1000)


def test_template_builders() -> None:
    recipient = TemplateRecipient(
        to="260971234567",
        header=TemplateHeader.document("https://e.x/a.pdf"),
        body=TemplateBody.named({"name": "Ada"}),
        buttons=[TemplateButton.quick_reply(1, "yes"), {"index": 2, "type": "url", "value": "v"}],
    )
    assert recipient.to_json() == {
        "to": "260971234567",
        "header": {"type": "document", "url": "https://e.x/a.pdf"},
        "body": {"name": "Ada"},
        "buttons": [
            {"index": 1, "type": "quick_reply", "value": "yes"},
            {"index": 2, "type": "url", "value": "v"},
        ],
    }
    plain = TemplateRecipient(to="1", header="Ada", body=["a", "b"])
    assert plain.to_json() == {"to": "1", "header": "Ada", "body": ["a", "b"]}
    assert TemplateHeader.text("x") == TemplateHeader("x")
    assert len({TemplateBody.of(["a"]), TemplateBody(["a"])}) == 1


def test_session_builders_and_message() -> None:
    message = session.buttons(
        "260971234567",
        "Pick one",
        [session.ReplyButton("a", "A"), ("b", "B"), {"id": "c", "title": "C"}],
        from_="260960123456",
    )
    assert message.type == "interactive"
    assert message.to == "260971234567"
    assert message.user_reference_id is None
    payload = message.to_json()
    assert payload["interactive"]["buttons"] == [
        {"id": "a", "title": "A"},
        {"id": "b", "title": "B"},
        {"id": "c", "title": "C"},
    ]
    payload["to"] = "changed"
    assert message.to == "260971234567", "to_json returns a copy"
    assert session.reaction("1", "m", "").to_json()["reaction"] == {"message_id": "m", "emoji": ""}


def test_gsm_issue_values() -> None:
    assert gsm.validate_sms("") == ["empty"]
    issue: str = gsm.SmsIssue.NON_GSM
    assert issue == "non_gsm"
    assert gsm.units("€" * 161) == 2
    assert gsm.non_gsm_characters("a\U0001f600") == [gsm.NonGsmCharacter("\U0001f600", 1)]
