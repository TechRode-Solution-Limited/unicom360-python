"""The operations, grouped as the client exposes them: ``client.sms``, ``client.email``,
``client.whatsapp`` and ``client.balance``.

Every operation takes the request options ``timeout=`` (seconds per attempt) and
``max_retries=``, which override the client's for that call.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Union

from .models import (
    Balance,
    Balances,
    EmailSendResult,
    SessionSendResult,
    SmsSendResult,
    StatusResult,
    TemplateList,
    TemplateSendResult,
)
from .session import SessionMessage
from .template import TemplateRecipient

if TYPE_CHECKING:
    from ._client import Unicom360

__all__ = ["BalanceResource", "Email", "Sms", "WhatsApp"]

Recipients = Union[str, Sequence[str]]


def _to(value: Recipients) -> str | list[str]:
    # A single string stays a string and a list stays a list: what the caller gave is sent.
    return value if isinstance(value, str) else list(value)


def _put(body: dict[str, Any], key: str, value: object) -> None:
    if value is not None:
        body[key] = value


def has_reference(value: object) -> bool:
    """Whether ``value`` is a reference the gateway de-duplicates on (a non-blank string)."""
    return isinstance(value, str) and value.strip() != ""


def _without_nulls(value: Mapping[str, Any]) -> dict[str, Any]:
    # An unset field is absent, never null.
    return {k: v for k, v in value.items() if v is not None}


class _Resource:
    def __init__(self, client: Unicom360) -> None:
        self._client = client

    def __repr__(self) -> str:
        return f"<{type(self).__name__} of {self._client!r}>"


class Sms(_Resource):
    """``client.sms``."""

    def send(
        self,
        *,
        from_: str,
        to: Recipients,
        message: str,
        user_reference_id: str | None = None,
        callback_url: str | None = None,
        source: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> SmsSendResult:
        """Send one GSM-7 text to one or more numbers.

        Args:
            from_: A registered sender ID.
            to: One number, or a list of numbers (international form, ``2609...``).
            message: GSM-7 text, at most 1,200 characters. See :mod:`unicom360.gsm`.
            user_reference_id: Your reference. The gateway refuses a repeat for the same
                recipient and sender, which makes the send safe to retry.
            callback_url: Where the gateway posts each delivery report (unsigned).
            source: A free-text label for your own reporting.

        Results are not in request order past the tenth recipient: use
        :meth:`~unicom360.models.SmsSendResult.by_number`.
        """
        generated: list[str] = []
        body: dict[str, Any] = {"from": from_, "to": _to(to), "message": message}
        _put(body, "user_reference_id", self._client._reference(user_reference_id, generated))
        _put(body, "callback_url", callback_url)
        _put(body, "source", source)
        parsed = self._client._request(
            "sms.send",
            body,
            retry_safe=has_reference(body.get("user_reference_id")),
            timeout=timeout,
            max_retries=max_retries,
            generated=generated,
        )
        return SmsSendResult.from_json(parsed.body)


class Email(_Resource):
    """``client.email``."""

    def send(
        self,
        *,
        from_: str,
        to: Recipients,
        subject: str,
        email_body: str,
        reply_to: str | None = None,
        user_reference_id: str | None = None,
        callback_url: str | None = None,
        source: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> EmailSendResult:
        """Send one email (HTML or text) to one or more addresses.

        Email is never retried after the request may have reached the gateway, even with a
        ``user_reference_id``: the gateway's duplicate check for email is not atomic. It is
        retried after a 429 and after a failure to connect.
        """
        generated: list[str] = []
        body: dict[str, Any] = {
            "from": from_,
            "to": _to(to),
            "subject": subject,
            "email_body": email_body,
        }
        _put(body, "reply_to", reply_to)
        _put(body, "user_reference_id", self._client._reference(user_reference_id, generated))
        _put(body, "callback_url", callback_url)
        _put(body, "source", source)
        parsed = self._client._request(
            "email.send",
            body,
            retry_safe=False,
            timeout=timeout,
            max_retries=max_retries,
            generated=generated,
        )
        return EmailSendResult.from_json(parsed.body)


RecipientLike = Union[TemplateRecipient, Mapping[str, Any]]
SessionLike = Union[SessionMessage, Mapping[str, Any]]


class WhatsApp(_Resource):
    """``client.whatsapp``."""

    def send_template(
        self,
        *,
        template: str,
        recipients: Sequence[RecipientLike],
        from_: str | None = None,
        language: str | None = None,
        callback_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> TemplateSendResult:
        """Send an approved template to up to 1,000 recipients, each with its own parameters.

        A rejected recipient is not an error: see
        :meth:`~unicom360.models.TemplateSendResult.rejected`. When every recipient is rejected
        the call raises :class:`~unicom360.NoValidRecipientsError`. The send is safe to retry
        when every recipient has a ``user_reference_id``.
        """
        generated: list[str] = []
        items: list[dict[str, Any]] = []
        for recipient in recipients:
            item = (
                recipient.to_json()
                if isinstance(recipient, TemplateRecipient)
                else _without_nulls(recipient)
            )
            reference = self._client._reference(item.get("user_reference_id"), generated)
            _put(item, "user_reference_id", reference)
            items.append(item)
        body: dict[str, Any] = {"template": template}
        _put(body, "from", from_)
        _put(body, "language", language)
        _put(body, "callback_url", callback_url)
        body["recipients"] = items
        retry_safe = bool(items) and all(
            has_reference(item.get("user_reference_id")) for item in items
        )
        parsed = self._client._request(
            "whatsapp.send_template",
            body,
            retry_safe=retry_safe,
            timeout=timeout,
            max_retries=max_retries,
            generated=generated,
        )
        return TemplateSendResult.from_json(parsed.body)

    def send_session(
        self,
        message: SessionLike,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> SessionSendResult:
        """Send a free-form message inside the 24-hour customer service window.

        Build ``message`` with :mod:`unicom360.session` (or pass a dict in the API's shape).
        Outside the window the call raises :class:`~unicom360.SessionWindowClosedError`.
        """
        generated: list[str] = []
        body = message.to_json() if isinstance(message, SessionMessage) else _without_nulls(message)
        _put(
            body,
            "user_reference_id",
            self._client._reference(body.get("user_reference_id"), generated),
        )
        parsed = self._client._request(
            "whatsapp.send_session",
            body,
            retry_safe=has_reference(body.get("user_reference_id")),
            timeout=timeout,
            max_retries=max_retries,
            generated=generated,
        )
        return SessionSendResult.from_json(parsed.body)

    def status(
        self,
        message_ids: str | Sequence[str],
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> StatusResult:
        """The current status of 1 to 100 WhatsApp messages, by the ``message_id`` a send gave.

        A single id may be passed as a string. Ids are sent as given (repeats included); an
        unknown id comes back with status ``NOT_FOUND``.
        """
        ids = [message_ids] if isinstance(message_ids, str) else list(message_ids)
        parsed = self._client._request(
            "whatsapp.status",
            {"message_ids": ids},
            retry_safe=True,
            timeout=timeout,
            max_retries=max_retries,
        )
        return StatusResult.from_json(parsed.body)

    def templates(
        self, *, timeout: float | None = None, max_retries: int | None = None
    ) -> TemplateList:
        """The approved templates available to your account."""
        parsed = self._client._request(
            "whatsapp.templates",
            None,
            retry_safe=True,
            timeout=timeout,
            max_retries=max_retries,
        )
        return TemplateList.from_json(parsed.body)


class BalanceResource(_Resource):
    """``client.balance``."""

    def get(
        self,
        bundle_type: str | None = None,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> Balance:
        """Units left on one bundle: ``SMS`` (the default), ``SMS_INTERNATIONAL``, ``EMAIL`` or
        ``WHATSAPP`` (see :class:`~unicom360.BundleType`)."""
        body: dict[str, Any] = {}
        _put(body, "bundle_type", bundle_type)
        parsed = self._client._request(
            "balance.get", body, retry_safe=True, timeout=timeout, max_retries=max_retries
        )
        return Balance.from_json(parsed.body, parsed.exact)

    def all(self, *, timeout: float | None = None, max_retries: int | None = None) -> Balances:
        """Units left on every bundle."""
        parsed = self._client._request(
            "balance.all", {}, retry_safe=True, timeout=timeout, max_retries=max_retries
        )
        return Balances.from_json(parsed.body, parsed.exact)
