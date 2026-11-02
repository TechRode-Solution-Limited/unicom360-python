"""Typed results of every operation.

Every model is an immutable dataclass with:

* the fields documented for it (``from`` is ``from_``), ``None`` when absent or null;
* ``extra``: every field the gateway sent that this version does not model, at the level it
  was found, so a field added tomorrow is readable today;
* ``raw``: the JSON object the model was parsed from, unmodified.

Statuses, categories, reasons and types are plain strings (open enums): a value this version
does not know passes through. ``message_id`` is always a string.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Final

__all__ = [
    "Balance",
    "Balances",
    "BundleType",
    "EmailResult",
    "EmailSendResult",
    "Health",
    "MessageError",
    "MessageStatus",
    "SessionSendResult",
    "SmsResult",
    "SmsSendResult",
    "StatusResult",
    "TemplateAuthentication",
    "TemplateBodyInfo",
    "TemplateButtonInfo",
    "TemplateHeaderInfo",
    "TemplateInfo",
    "TemplateList",
    "TemplateResult",
    "TemplateSendResult",
]

JsonObject = dict[str, Any]

#: ``status`` of an accepted SMS, email or template recipient.
ACKNOWLEDGED: Final = "ACKNOWLEDGED"
#: ``status`` of a refused template recipient.
REJECTED: Final = "REJECTED"


class BundleType:
    """Known ``bundle_type`` values for :meth:`unicom360.Unicom360.balance` ``.get``.

    Any other string is sent as given.
    """

    SMS: Final = "SMS"
    SMS_INTERNATIONAL: Final = "SMS_INTERNATIONAL"
    EMAIL: Final = "EMAIL"
    WHATSAPP: Final = "WHATSAPP"


# ---------------------------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------------------------


def _obj(value: object) -> JsonObject:
    return dict(value) if isinstance(value, Mapping) else {}


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _id_str(value: object) -> str | None:
    """A string, or a JSON number converted to its decimal text (ids the wire sends as numbers)."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return None


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


_DECIMAL_TEXT = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?")


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # repr gives the shortest text that round-trips, which is the text the gateway sent for
        # any balance it can produce. The client parses balances with Decimal directly anyway.
        return Decimal(repr(value))
    if isinstance(value, str) and _DECIMAL_TEXT.fullmatch(value):
        try:
            return Decimal(value)
        except InvalidOperation:  # pragma: no cover - the pattern only admits valid numbers
            return None
    return None


def _str_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [v for v in value if isinstance(v, str)]


def _extra(obj: Mapping[str, Any], known: frozenset[str]) -> JsonObject:
    return {k: v for k, v in obj.items() if k not in known}


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if "0" <= ch <= "9")


def _match_number(candidate: str | None, wanted: str) -> bool:
    wanted_digits = _digits(wanted)
    if wanted_digits == "":
        return candidate == wanted
    return _digits(candidate) == wanted_digits


# Envelope keys that are not data: ``success`` is consumed, the rest are modelled.
_ENVELOPE: Final = frozenset({"success", "api_reference", "message", "data"})


def _envelope_extra(envelope: Mapping[str, Any], data_known: frozenset[str]) -> JsonObject:
    """Unknown envelope fields plus unknown ``data`` fields when ``data`` is an object."""
    extra = _extra(envelope, _ENVELOPE)
    data = envelope.get("data")
    if isinstance(data, Mapping):
        extra.update(_extra(data, data_known))
    return extra


# ---------------------------------------------------------------------------------------------
# SMS and email
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SmsResult:
    """One recipient of an SMS send."""

    message_id: str | None = None
    #: ``ACKNOWLEDGED`` or ``Invalid mobile number`` (open).
    status: str | None = None
    #: The number as the gateway normalised it.
    mobile_number: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"message_id", "status", "mobile_number"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> SmsResult:
        return cls(
            message_id=_id_str(obj.get("message_id")),
            status=_str(obj.get("status")),
            mobile_number=_str(obj.get("mobile_number")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class SmsSendResult:
    """The result of :meth:`unicom360.resources.Sms.send`.

    ``results`` keep the response's order, which is **not** the request's order past the
    tenth recipient: find a recipient with :meth:`by_number`.
    """

    api_reference: str | None = None
    message: str | None = None
    results: list[SmsResult] = field(default_factory=list)
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, envelope: Mapping[str, Any]) -> SmsSendResult:
        data = envelope.get("data")
        items = data if isinstance(data, list) else []
        return cls(
            api_reference=_str(envelope.get("api_reference")),
            message=_str(envelope.get("message")),
            results=[SmsResult.from_json(_obj(item)) for item in items],
            extra=_envelope_extra(envelope, frozenset()),
            raw=dict(envelope),
        )

    def accepted(self) -> list[SmsResult]:
        """The results whose status is exactly ``ACKNOWLEDGED``, in response order."""
        return [r for r in self.results if r.status == ACKNOWLEDGED]

    def invalid(self) -> list[SmsResult]:
        """Every other result (for example ``Invalid mobile number``), in response order."""
        return [r for r in self.results if r.status != ACKNOWLEDGED]

    def by_number(self, number: str) -> SmsResult | None:
        """The first result whose ``mobile_number`` has the same digits as ``number``.

        Non-digits are ignored on both sides (``"+260 97 123 4567"`` finds
        ``"260971234567"``). Local formats are not expanded: pass the international form.
        """
        return next((r for r in self.results if _match_number(r.mobile_number, number)), None)


@dataclass(frozen=True)
class EmailResult:
    """One recipient of an email send."""

    message_id: str | None = None
    #: ``ACKNOWLEDGED`` or ``Invalid email address`` (open).
    status: str | None = None
    email_address: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"message_id", "status", "email_address"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> EmailResult:
        return cls(
            message_id=_id_str(obj.get("message_id")),
            status=_str(obj.get("status")),
            email_address=_str(obj.get("email_address")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class EmailSendResult:
    """The result of :meth:`unicom360.resources.Email.send`.

    ``results`` are not in request order past the tenth recipient: use :meth:`by_address`.
    """

    api_reference: str | None = None
    message: str | None = None
    results: list[EmailResult] = field(default_factory=list)
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_json(cls, envelope: Mapping[str, Any]) -> EmailSendResult:
        data = envelope.get("data")
        items = data if isinstance(data, list) else []
        return cls(
            api_reference=_str(envelope.get("api_reference")),
            message=_str(envelope.get("message")),
            results=[EmailResult.from_json(_obj(item)) for item in items],
            extra=_envelope_extra(envelope, frozenset()),
            raw=dict(envelope),
        )

    def accepted(self) -> list[EmailResult]:
        """The results whose status is exactly ``ACKNOWLEDGED``, in response order."""
        return [r for r in self.results if r.status == ACKNOWLEDGED]

    def invalid(self) -> list[EmailResult]:
        """Every other result (for example ``Invalid email address``), in response order."""
        return [r for r in self.results if r.status != ACKNOWLEDGED]

    def by_address(self, address: str) -> EmailResult | None:
        """The first result whose address equals ``address``, trimmed and lower-cased."""
        wanted = address.strip().lower()
        return next(
            (r for r in self.results if (r.email_address or "").strip().lower() == wanted),
            None,
        )


# ---------------------------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TemplateResult:
    """One recipient of a template send."""

    #: Null unless queued, or the original message after ``DUPLICATE_MSG_REF``.
    message_id: str | None = None
    #: As the request sent it (a string even when the request sent a number).
    to: str | None = None
    user_reference_id: str | None = None
    #: ``ACKNOWLEDGED`` or ``REJECTED`` (open).
    status: str | None = None
    #: Why a recipient was rejected (open); null when accepted.
    reason: str | None = None
    category: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {"message_id", "to", "user_reference_id", "status", "reason", "category"}
    )

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> TemplateResult:
        return cls(
            message_id=_id_str(obj.get("message_id")),
            to=_id_str(obj.get("to")),
            user_reference_id=_id_str(obj.get("user_reference_id")),
            status=_str(obj.get("status")),
            reason=_str(obj.get("reason")),
            category=_str(obj.get("category")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


def _template_results(value: object) -> list[TemplateResult]:
    items = value if isinstance(value, list) else []
    return [TemplateResult.from_json(_obj(item)) for item in items]


@dataclass(frozen=True)
class TemplateSendResult:
    """The result of :meth:`unicom360.resources.WhatsApp.send_template`.

    ``accepted_count`` and ``rejected_count`` are the API's ``data.accepted`` and
    ``data.rejected``; :meth:`accepted` and :meth:`rejected` return the results themselves.
    """

    api_reference: str | None = None
    message: str | None = None
    accepted_count: int | None = None
    rejected_count: int | None = None
    results: list[TemplateResult] = field(default_factory=list)
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _DATA_KNOWN: ClassVar[frozenset[str]] = frozenset({"accepted", "rejected", "results"})

    @classmethod
    def from_json(cls, envelope: Mapping[str, Any]) -> TemplateSendResult:
        data = _obj(envelope.get("data"))
        return cls(
            api_reference=_str(envelope.get("api_reference")),
            message=_str(envelope.get("message")),
            accepted_count=_int(data.get("accepted")),
            rejected_count=_int(data.get("rejected")),
            results=_template_results(data.get("results")),
            extra=_envelope_extra(envelope, cls._DATA_KNOWN),
            raw=dict(envelope),
        )

    def accepted(self) -> list[TemplateResult]:
        """The results whose status is exactly ``ACKNOWLEDGED``."""
        return [r for r in self.results if r.status == ACKNOWLEDGED]

    def rejected(self) -> list[TemplateResult]:
        """The results whose status is exactly ``REJECTED``."""
        return [r for r in self.results if r.status == REJECTED]

    def by_number(self, number: str) -> TemplateResult | None:
        """The first result whose ``to`` has the same digits as ``number`` (non-digits ignored)."""
        return next((r for r in self.results if _match_number(r.to, number)), None)


@dataclass(frozen=True)
class SessionSendResult:
    """The result of :meth:`unicom360.resources.WhatsApp.send_session`."""

    api_reference: str | None = None
    message: str | None = None
    message_id: str | None = None
    to: str | None = None
    user_reference_id: str | None = None
    status: str | None = None
    category: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _DATA_KNOWN: ClassVar[frozenset[str]] = frozenset(
        {"message_id", "to", "user_reference_id", "status", "category"}
    )

    @classmethod
    def from_json(cls, envelope: Mapping[str, Any]) -> SessionSendResult:
        data = _obj(envelope.get("data"))
        return cls(
            api_reference=_str(envelope.get("api_reference")),
            message=_str(envelope.get("message")),
            message_id=_id_str(data.get("message_id")),
            to=_id_str(data.get("to")),
            user_reference_id=_id_str(data.get("user_reference_id")),
            status=_str(data.get("status")),
            category=_str(data.get("category")),
            extra=_envelope_extra(envelope, cls._DATA_KNOWN),
            raw=dict(envelope),
        )


@dataclass(frozen=True)
class MessageError:
    """Why a WhatsApp message failed: Meta's error code (or null) and message."""

    code: int | None = None
    message: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"code", "message"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> MessageError:
        return cls(
            code=_int(obj.get("code")),
            message=_str(obj.get("message")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )

    @classmethod
    def parse(cls, value: object) -> MessageError | None:
        return cls.from_json(value) if isinstance(value, Mapping) else None


@dataclass(frozen=True)
class MessageStatus:
    """The status of one WhatsApp message.

    ``status`` is ``ACCEPTED``, ``SENT``, ``DELIVERED``, ``READ``, ``FAILED``, ``REJECTED`` or
    ``NOT_FOUND`` (open). A ``NOT_FOUND`` entry carries only ``message_id`` and ``status``.
    """

    message_id: str | None = None
    status: str | None = None
    user_reference_id: str | None = None
    to: str | None = None
    from_: str | None = None
    sent_at: str | None = None
    delivered_at: str | None = None
    read_at: str | None = None
    error: MessageError | None = None
    category: str | None = None
    billable: bool | None = None
    refunded: bool | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {
            "message_id",
            "status",
            "user_reference_id",
            "to",
            "from",
            "sent_at",
            "delivered_at",
            "read_at",
            "error",
            "category",
            "billable",
            "refunded",
        }
    )

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> MessageStatus:
        return cls(
            message_id=_id_str(obj.get("message_id")),
            status=_str(obj.get("status")),
            user_reference_id=_id_str(obj.get("user_reference_id")),
            to=_id_str(obj.get("to")),
            from_=_id_str(obj.get("from")),
            sent_at=_str(obj.get("sent_at")),
            delivered_at=_str(obj.get("delivered_at")),
            read_at=_str(obj.get("read_at")),
            error=MessageError.parse(obj.get("error")),
            category=_str(obj.get("category")),
            billable=_bool(obj.get("billable")),
            refunded=_bool(obj.get("refunded")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class StatusResult:
    """The result of :meth:`unicom360.resources.WhatsApp.status`."""

    api_reference: str | None = None
    message: str | None = None
    results: list[MessageStatus] = field(default_factory=list)
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _DATA_KNOWN: ClassVar[frozenset[str]] = frozenset({"results"})

    @classmethod
    def from_json(cls, envelope: Mapping[str, Any]) -> StatusResult:
        data = _obj(envelope.get("data"))
        items = data.get("results")
        return cls(
            api_reference=_str(envelope.get("api_reference")),
            message=_str(envelope.get("message")),
            results=[
                MessageStatus.from_json(_obj(item))
                for item in (items if isinstance(items, list) else [])
            ],
            extra=_envelope_extra(envelope, cls._DATA_KNOWN),
            raw=dict(envelope),
        )

    def by_id(self, message_id: str) -> MessageStatus | None:
        """The entry for ``message_id`` (exact match), or ``None``."""
        return next((r for r in self.results if r.message_id == message_id), None)


@dataclass(frozen=True)
class TemplateHeaderInfo:
    """A template's header: its ``type`` (``text``, ``image``, ...) and variable names."""

    type: str | None = None
    variables: list[str] | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"type", "variables"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> TemplateHeaderInfo:
        return cls(
            type=_str(obj.get("type")),
            variables=_str_list(obj.get("variables")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class TemplateBodyInfo:
    """A template's body text and its variable names."""

    text: str | None = None
    variables: list[str] | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"text", "variables"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> TemplateBodyInfo:
        return cls(
            text=_str(obj.get("text")),
            variables=_str_list(obj.get("variables")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class TemplateButtonInfo:
    """One button of a template (``url``, ``quick_reply``, ``otp``, ...)."""

    index: int | None = None
    type: str | None = None
    text: str | None = None
    url: str | None = None
    otp_type: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"index", "type", "text", "url", "otp_type"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> TemplateButtonInfo:
        return cls(
            index=_int(obj.get("index")),
            type=_str(obj.get("type")),
            text=_str(obj.get("text")),
            url=_str(obj.get("url")),
            otp_type=_str(obj.get("otp_type")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class TemplateAuthentication:
    """The one-time-password settings of an ``AUTHENTICATION`` template."""

    otp_type: str | None = None
    code_expiration_minutes: int | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"otp_type", "code_expiration_minutes"})

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> TemplateAuthentication:
        return cls(
            otp_type=_str(obj.get("otp_type")),
            code_expiration_minutes=_int(obj.get("code_expiration_minutes")),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class TemplateInfo:
    """One approved template available to the account."""

    name: str | None = None
    language: str | None = None
    category: str | None = None
    from_: str | None = None
    header: TemplateHeaderInfo | None = None
    body: TemplateBodyInfo | None = None
    footer: str | None = None
    buttons: list[TemplateButtonInfo] | None = None
    authentication: TemplateAuthentication | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {
            "name",
            "language",
            "category",
            "from",
            "header",
            "body",
            "footer",
            "buttons",
            "authentication",
        }
    )

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> TemplateInfo:
        header = obj.get("header")
        body = obj.get("body")
        buttons = obj.get("buttons")
        authentication = obj.get("authentication")
        return cls(
            name=_str(obj.get("name")),
            language=_str(obj.get("language")),
            category=_str(obj.get("category")),
            from_=_id_str(obj.get("from")),
            header=TemplateHeaderInfo.from_json(header) if isinstance(header, Mapping) else None,
            body=TemplateBodyInfo.from_json(body) if isinstance(body, Mapping) else None,
            footer=_str(obj.get("footer")),
            buttons=(
                [TemplateButtonInfo.from_json(_obj(b)) for b in buttons]
                if isinstance(buttons, list)
                else None
            ),
            authentication=(
                TemplateAuthentication.from_json(authentication)
                if isinstance(authentication, Mapping)
                else None
            ),
            extra=_extra(obj, cls._KNOWN),
            raw=dict(obj),
        )


@dataclass(frozen=True)
class TemplateList:
    """The result of :meth:`unicom360.resources.WhatsApp.templates`."""

    api_reference: str | None = None
    message: str | None = None
    templates: list[TemplateInfo] = field(default_factory=list)
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _DATA_KNOWN: ClassVar[frozenset[str]] = frozenset({"templates"})

    @classmethod
    def from_json(cls, envelope: Mapping[str, Any]) -> TemplateList:
        data = _obj(envelope.get("data"))
        items = data.get("templates")
        return cls(
            api_reference=_str(envelope.get("api_reference")),
            message=_str(envelope.get("message")),
            templates=[
                TemplateInfo.from_json(_obj(item))
                for item in (items if isinstance(items, list) else [])
            ],
            extra=_envelope_extra(envelope, cls._DATA_KNOWN),
            raw=dict(envelope),
        )

    def by_name(self, name: str, language: str | None = None) -> TemplateInfo | None:
        """The first template named ``name`` (and in ``language``, when given)."""
        return next(
            (
                t
                for t in self.templates
                if t.name == name and (language is None or t.language == language)
            ),
            None,
        )


# ---------------------------------------------------------------------------------------------
# Balance and health
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Balance:
    """The result of :meth:`unicom360.resources.BalanceResource.get`."""

    message: str | None = None
    #: Units remaining, exactly as the gateway sent them.
    balance: Decimal | None = None
    bundle_type: str | None = None
    client_id: str | None = None
    client_name: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {"status", "message", "balance", "bundle_type", "client_id", "client_name"}
    )

    @classmethod
    def from_json(cls, body: Mapping[str, Any], exact: Mapping[str, Any] | None = None) -> Balance:
        """Parse a balance envelope. ``exact`` is the same body parsed with ``Decimal`` floats."""
        numbers = exact if exact is not None else body
        return cls(
            message=_str(body.get("message")),
            balance=_decimal(numbers.get("balance")),
            bundle_type=_str(body.get("bundle_type")),
            client_id=_id_str(body.get("client_id")),
            client_name=_str(body.get("client_name")),
            extra=_extra(body, cls._KNOWN),
            raw=dict(body),
        )


@dataclass(frozen=True)
class Balances:
    """The result of :meth:`unicom360.resources.BalanceResource.all`."""

    message: str | None = None
    #: Units remaining per bundle type (``SMS``, ``EMAIL``, ``WHATSAPP``, ...).
    balances: dict[str, Decimal] = field(default_factory=dict)
    client_id: str | None = None
    client_name: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset(
        {"status", "message", "balances", "client_id", "client_name"}
    )

    @classmethod
    def from_json(cls, body: Mapping[str, Any], exact: Mapping[str, Any] | None = None) -> Balances:
        """Parse a balances envelope. ``exact`` is the same body parsed with ``Decimal`` floats."""
        numbers = _obj((exact if exact is not None else body).get("balances"))
        balances: dict[str, Decimal] = {}
        for key, value in numbers.items():
            amount = _decimal(value)
            if amount is not None:
                balances[key] = amount
        return cls(
            message=_str(body.get("message")),
            balances=balances,
            client_id=_id_str(body.get("client_id")),
            client_name=_str(body.get("client_name")),
            extra=_extra(body, cls._KNOWN),
            raw=dict(body),
        )


@dataclass(frozen=True)
class Health:
    """The result of :meth:`unicom360.Unicom360.health`."""

    status: str | None = None
    #: ISO 8601, as received (the gateway sends microseconds).
    timestamp: str | None = None
    version: str | None = None
    environment: str | None = None
    extra: JsonObject = field(default_factory=dict, repr=False)
    raw: JsonObject = field(default_factory=dict, repr=False, compare=False)

    _KNOWN: ClassVar[frozenset[str]] = frozenset({"status", "timestamp", "version", "environment"})

    @classmethod
    def from_json(cls, body: Mapping[str, Any]) -> Health:
        return cls(
            status=_str(body.get("status")),
            timestamp=_str(body.get("timestamp")),
            version=_str(body.get("version")),
            environment=_str(body.get("environment")),
            extra=_extra(body, cls._KNOWN),
            raw=dict(body),
        )
