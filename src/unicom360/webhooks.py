"""Verify and parse what Unicom360 posts to you.

WhatsApp webhooks (``message.status``, ``message.received``, ``webhook.test``) are signed::

    from unicom360 import webhooks

    event = webhooks.construct_event(raw_body, request.headers, secret)

Pass the **raw** body bytes, exactly as received, before any JSON parsing. The secret is the
43-character string from the portal, used as it is (never base64-decoded). Deliveries are
retried on any non-2xx (after 30 s, 2 min, 10 min, 30 min, 1 h, 3 h, 6 h and 12 h), so answer
2xx quickly and drop repeats by ``event.delivery_id``.

SMS and email delivery reports are **unsigned and never retried**: anyone can post one to your
callback URL, so treat them as hints and confirm anything that matters another way.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final, Protocol, Union

from .errors import SignatureVerificationError, Unicom360Error
from .models import MessageError, _bool, _extra, _id_str, _str

__all__ = [
    "DEFAULT_TOLERANCE",
    "EmailDeliveryReport",
    "Event",
    "InboundMedia",
    "InboundMessage",
    "MessageReceivedEvent",
    "MessageStatusData",
    "MessageStatusEvent",
    "SmsDeliveryReport",
    "TestEvent",
    "TestEventData",
    "UnknownEvent",
    "construct_event",
    "parse_email_callback",
    "parse_sms_callback",
    "verify",
]

#: The default clock-skew tolerance, in seconds.
DEFAULT_TOLERANCE: Final = 300

SIGNATURE_HEADER: Final = "X-Unicom360-Signature"
TIMESTAMP_HEADER: Final = "X-Unicom360-Timestamp"
EVENT_HEADER: Final = "X-Unicom360-Event"
DELIVERY_HEADER: Final = "X-Unicom360-Delivery"

_MAX_INT64: Final = 2**63 - 1
_TIMESTAMP: Final = re.compile(r"[0-9]+")
_SIGNATURE: Final = re.compile(r"sha256=[0-9a-f]{64}")

JsonObject = dict[str, Any]
RawBody = Union[bytes, bytearray, memoryview, str]


class _SupportsItems(Protocol):
    def items(self) -> Iterable[tuple[Any, Any]]: ...


#: A header collection: a dict, Flask/Werkzeug, Django or Starlette headers, an
#: ``email.message.Message``, or a list of ``(name, value)`` pairs. Names are matched without
#: regard to case; when a header has several values the first is used.
Headers = Union[_SupportsItems, Iterable[tuple[Any, Any]]]


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("latin-1")
    return str(value)


def _header(headers: Headers, name: str) -> str | None:
    wanted = name.lower()
    pairs: Iterable[tuple[Any, Any]] = headers.items() if hasattr(headers, "items") else headers
    for key, value in pairs:
        if _text(key).lower() != wanted:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            value = value[0]
        return None if value is None else _text(value)
    return None


def _bytes(raw_body: RawBody) -> bytes:
    if isinstance(raw_body, str):
        return raw_body.encode("utf-8")
    return bytes(raw_body)


def verify(
    raw_body: RawBody,
    headers: Headers,
    secret: str | bytes,
    tolerance: float = DEFAULT_TOLERANCE,
    now: float | None = None,
) -> None:
    """Check a webhook delivery's signature and timestamp.

    Args:
        raw_body: The body exactly as received (a ``str`` is encoded as UTF-8).
        headers: The request headers; see :data:`Headers`.
        secret: Your webhook secret from the portal, used as it is.
        tolerance: The largest accepted difference, in seconds, between ``now`` and the
            delivery's timestamp, in either direction.
        now: The current Unix time; defaults to the system clock.

    Raises:
        SignatureVerificationError: with ``reason`` ``missing_signature``,
            ``missing_timestamp``, ``invalid_timestamp``, ``malformed_signature``,
            ``timestamp_out_of_tolerance`` or ``signature_mismatch`` (checked in that order).
    """
    signature = _header(headers, SIGNATURE_HEADER)
    if not signature:
        raise SignatureVerificationError("missing_signature")
    timestamp = _header(headers, TIMESTAMP_HEADER)
    if not timestamp:
        raise SignatureVerificationError("missing_timestamp")
    if not _TIMESTAMP.fullmatch(timestamp):
        raise SignatureVerificationError("invalid_timestamp")
    if not _SIGNATURE.fullmatch(signature):
        raise SignatureVerificationError("malformed_signature")
    sent_at = int(timestamp)
    current = time.time() if now is None else now
    if sent_at > _MAX_INT64 or abs(current - sent_at) > tolerance:
        raise SignatureVerificationError("timestamp_out_of_tolerance")
    key = secret if isinstance(secret, bytes) else secret.encode("utf-8")
    expected = hmac.new(
        key, timestamp.encode("ascii") + b"." + _bytes(raw_body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature[len("sha256=") :]):
        raise SignatureVerificationError("signature_mismatch")


# ---------------------------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------------------------


def _obj(value: object) -> JsonObject:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class MessageStatusData:
    """``message.status``: a WhatsApp message you sent changed status."""

    #: The ``message_id`` the send returned.
    message_id: str | None = None
    user_reference_id: str | None = None
    channel: str | None = None
    to: str | None = None
    from_: str | None = None
    #: ``sent``, ``delivered``, ``read`` or ``failed`` (open).
    status: str | None = None
    timestamp: str | None = None
    error: MessageError | None = None
    category: str | None = None
    billable: bool | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {
            "message_id",
            "user_reference_id",
            "channel",
            "to",
            "from",
            "status",
            "timestamp",
            "error",
            "category",
            "billable",
        }
    )

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> MessageStatusData:
        return cls(
            message_id=_id_str(obj.get("message_id")),
            user_reference_id=_id_str(obj.get("user_reference_id")),
            channel=_str(obj.get("channel")),
            to=_id_str(obj.get("to")),
            from_=_id_str(obj.get("from")),
            status=_str(obj.get("status")),
            timestamp=_str(obj.get("timestamp")),
            error=MessageError.parse(obj.get("error")),
            category=_str(obj.get("category")),
            billable=_bool(obj.get("billable")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class InboundMedia:
    """Media a customer sent. A caption arrives in :attr:`InboundMessage.text`, not here."""

    id: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"id", "mime_type", "filename"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> InboundMedia:
        return cls(
            id=_id_str(obj.get("id")),
            mime_type=_str(obj.get("mime_type")),
            filename=_str(obj.get("filename")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class InboundMessage:
    """``message.received``: a customer wrote to your WhatsApp number.

    * ``text`` holds the text, a media caption, or the chosen title of an interactive or
      button reply (whose button or row id is not passed on).
    * ``payload`` is Meta's object for location, contacts (``{"contacts": [...]}``), reaction,
      sticker and unsupported messages, and ``None`` otherwise.
    * ``reply_to`` is the ``wamid.`` id of the message replied to (for an interactive reply,
      your interactive message).
    """

    #: Meta's ``wamid.`` id; pass it as ``reply_to`` or a reaction's ``message_id``.
    message_id: str | None = None
    channel: str | None = None
    #: The customer.
    from_: str | None = None
    #: Your number.
    to: str | None = None
    type: str | None = None
    text: str | None = None
    media: InboundMedia | None = None
    payload: JsonObject | None = None
    reply_to: str | None = None
    timestamp: str | None = None
    #: When the 24-hour customer service window closes.
    window_expires_at: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {
            "message_id",
            "channel",
            "from",
            "to",
            "type",
            "text",
            "media",
            "payload",
            "reply_to",
            "timestamp",
            "window_expires_at",
        }
    )

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> InboundMessage:
        media = obj.get("media")
        payload = obj.get("payload")
        return cls(
            message_id=_id_str(obj.get("message_id")),
            channel=_str(obj.get("channel")),
            from_=_id_str(obj.get("from")),
            to=_id_str(obj.get("to")),
            type=_str(obj.get("type")),
            text=_str(obj.get("text")),
            media=InboundMedia.from_json(media) if isinstance(media, Mapping) else None,
            payload=dict(payload) if isinstance(payload, Mapping) else None,
            reply_to=_str(obj.get("reply_to")),
            timestamp=_str(obj.get("timestamp")),
            window_expires_at=_str(obj.get("window_expires_at")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class TestEventData:
    """``webhook.test``: sent from the portal's "Send test" button."""

    __test__: ClassVar[bool] = False  # not a pytest test class

    message: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"message"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> TestEventData:
        return cls(message=_str(obj.get("message")), extra=_extra(obj, cls._KNOWN), raw=dict(obj))


@dataclass(frozen=True)
class MessageStatusEvent:
    """A ``message.status`` delivery."""

    kind: ClassVar[str] = "message_status"
    event: str
    #: The ``X-Unicom360-Delivery`` header: drop a delivery you have already handled.
    delivery_id: str | None
    created_at: str | None
    data: MessageStatusData
    raw: JsonObject = field(repr=False, compare=False)


@dataclass(frozen=True)
class MessageReceivedEvent:
    """A ``message.received`` delivery."""

    kind: ClassVar[str] = "message_received"
    event: str
    delivery_id: str | None
    created_at: str | None
    data: InboundMessage
    raw: JsonObject = field(repr=False, compare=False)


@dataclass(frozen=True)
class TestEvent:
    """A ``webhook.test`` delivery."""

    __test__: ClassVar[bool] = False  # not a pytest test class
    kind: ClassVar[str] = "test"
    event: str
    delivery_id: str | None
    created_at: str | None
    data: TestEventData
    raw: JsonObject = field(repr=False, compare=False)


@dataclass(frozen=True)
class UnknownEvent:
    """An event this version of the SDK does not know. ``data`` is the raw JSON object."""

    kind: ClassVar[str] = "unknown"
    event: str
    delivery_id: str | None
    created_at: str | None
    data: JsonObject | None
    raw: JsonObject = field(repr=False, compare=False)


Event = Union[MessageStatusEvent, MessageReceivedEvent, TestEvent, UnknownEvent]


def _reject_constant(name: str) -> Any:
    raise ValueError(f"not JSON: {name}")


def _json_object(raw_body: RawBody, what: str) -> JsonObject:
    try:
        parsed = json.loads(_bytes(raw_body).decode("utf-8"), parse_constant=_reject_constant)
    except ValueError as error:
        raise Unicom360Error(f"The {what} is not JSON") from error
    if not isinstance(parsed, dict):
        raise Unicom360Error(f"The {what} is not a JSON object")
    return parsed


def construct_event(
    raw_body: RawBody,
    headers: Headers,
    secret: str | bytes,
    tolerance: float = DEFAULT_TOLERANCE,
    now: float | None = None,
) -> Event:
    """Verify a delivery (see :func:`verify`), then parse it into its event.

    The model is chosen by the body's ``event``: :class:`MessageStatusEvent`,
    :class:`MessageReceivedEvent`, :class:`TestEvent`, or :class:`UnknownEvent` for an event
    this version does not know (which never raises).

    Raises:
        SignatureVerificationError: The delivery failed verification.
        Unicom360Error: The body is not a JSON object with a string ``event``.
    """
    verify(raw_body, headers, secret, tolerance, now)
    body = _json_object(raw_body, "webhook body")
    event = body.get("event")
    if not isinstance(event, str):
        raise Unicom360Error("The webhook body has no string 'event'")
    delivery_id = _header(headers, DELIVERY_HEADER)
    created_at = _str(body.get("created_at"))
    data = body.get("data")
    if event == "message.status":
        return MessageStatusEvent(
            event, delivery_id, created_at, MessageStatusData.from_json(_obj(data)), body
        )
    if event == "message.received":
        return MessageReceivedEvent(
            event, delivery_id, created_at, InboundMessage.from_json(_obj(data)), body
        )
    if event == "webhook.test":
        return TestEvent(event, delivery_id, created_at, TestEventData.from_json(_obj(data)), body)
    return UnknownEvent(
        event, delivery_id, created_at, dict(data) if isinstance(data, Mapping) else None, body
    )


# ---------------------------------------------------------------------------------------------
# Unsigned SMS and email delivery reports
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SmsDeliveryReport:
    """An SMS delivery report posted to your ``callback_url``. Unsigned: treat it as a hint."""

    message_id: str | None = None
    #: ``SENT``, ``DELIVERED``, ``FAILED`` or ``UNKNOWN_ERROR`` (open).
    status: str | None = None
    mobile_number: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"message_id", "status", "mobile_number"})


@dataclass(frozen=True)
class EmailDeliveryReport:
    """An email delivery report posted to your ``callback_url``. Unsigned: treat it as a hint.

    ``message_id`` is the string the send returned (the report sends it as a number).
    """

    message_id: str | None = None
    #: ``SENT``, ``DELIVERED`` or ``FAILED`` (open).
    status: str | None = None
    email_address: str | None = None
    #: The mail server's answer, for example ``success`` or a bounce reason.
    message: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {"message_id", "status", "email_address", "message"}
    )


def parse_sms_callback(raw_body: RawBody) -> SmsDeliveryReport:
    """Parse an SMS delivery report.

    Raises:
        Unicom360Error: The body is not a JSON object.
    """
    body = _json_object(raw_body, "SMS delivery report")
    return SmsDeliveryReport(
        message_id=_id_str(body.get("message_id")),
        status=_str(body.get("status")),
        mobile_number=_id_str(body.get("mobile_number")),
        extra=_extra(body, SmsDeliveryReport._KNOWN),
        raw=body,
    )


def parse_email_callback(raw_body: RawBody) -> EmailDeliveryReport:
    """Parse an email delivery report.

    Raises:
        Unicom360Error: The body is not a JSON object.
    """
    body = _json_object(raw_body, "email delivery report")
    return EmailDeliveryReport(
        message_id=_id_str(body.get("message_id")),
        status=_str(body.get("status")),
        email_address=_str(body.get("email_address")),
        message=_str(body.get("message")),
        extra=_extra(body, EmailDeliveryReport._KNOWN),
        raw=body,
    )
