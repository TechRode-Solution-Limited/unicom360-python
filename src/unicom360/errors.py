"""The exceptions this SDK raises.

::

    Unicom360Error
    +-- ConfigurationError
    +-- APIConnectionError
    |   +-- APITimeoutError
    +-- APIStatusError                 (any non-2xx, and a 2xx without a usable envelope)
    |   +-- AuthenticationError        (401)
    |   +-- RateLimitError             (429)
    |   +-- InvalidRequestError        (400)
    |   +-- APIServerError             (5xx)
    +-- APIError                       (2xx with success: false or status: false)
    |   +-- InsufficientBundleError
    |   +-- DuplicateReferenceError
    |   +-- NoValidRecipientsError
    |   +-- SessionWindowClosedError
    +-- SignatureVerificationError

A partial success (some recipients invalid or rejected) is a result, never an exception.
No exception carries the API key or a webhook secret.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from .models import TemplateResult

__all__ = [
    "APIConnectionError",
    "APIError",
    "APIServerError",
    "APIStatusError",
    "APITimeoutError",
    "AuthenticationError",
    "ConfigurationError",
    "DuplicateReferenceError",
    "InsufficientBundleError",
    "InvalidRequestError",
    "NoValidRecipientsError",
    "RateLimitError",
    "SessionWindowClosedError",
    "SignatureVerificationError",
    "Unicom360Error",
]


class Unicom360Error(Exception):
    """Base class of every exception this SDK raises.

    Attributes:
        message: Human-readable text.
        http_status: The response's status code, for API errors; otherwise ``None``.
        api_reference: The gateway's reference for the request, when the body had one. Quote it
            to support.
        raw_body: The response body text, for API errors.
        attempts: HTTP attempts made by the operation that raised, retries included.
    """

    #: The error's type string (the same in every Unicom360 SDK).
    type: ClassVar[str] = "unicom360_error"

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        api_reference: str | None = None,
        raw_body: str | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.api_reference = api_reference
        self.raw_body = raw_body
        self.attempts = attempts

    def __str__(self) -> str:
        details = []
        if self.http_status is not None:
            details.append(f"HTTP {self.http_status}")
        if self.api_reference is not None:
            details.append(f"api_reference {self.api_reference}")
        if self.attempts is not None and self.attempts > 1:
            details.append(f"after {self.attempts} attempts")
        return f"{self.message} ({', '.join(details)})" if details else self.message

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r})"


class ConfigurationError(Unicom360Error):
    """The configuration is unusable (no API key, a bad ``base_url``, a blank webhook secret)."""

    type = "configuration_error"


class APIConnectionError(Unicom360Error):
    """The request failed before a complete response arrived.

    ``sent`` says whether any byte of the request may have reached the gateway. ``cause`` is
    the underlying exception.
    """

    type = "connection_error"

    def __init__(
        self,
        message: str,
        *,
        sent: bool = True,
        cause: BaseException | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(message, attempts=attempts)
        self.sent = sent
        self.cause = cause


class APITimeoutError(APIConnectionError):
    """The connection or the response timed out."""

    type = "timeout_error"


class _ResponseError(Unicom360Error):
    """Shared fields of the errors built from an HTTP response."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        http_status: int,
        api_reference: str | None = None,
        raw_body: str | None = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(
            message,
            http_status=http_status,
            api_reference=api_reference,
            raw_body=raw_body,
            attempts=attempts,
        )
        #: The normalised code (see :mod:`unicom360.codes`).
        self.code = code
        #: The envelope's ``data`` as parsed JSON, or ``None``.
        self.data = data
        #: The response headers, names lower-cased.
        self.headers: dict[str, str] = dict(headers or {})

    def __str__(self) -> str:
        details = [f"code {self.code}", f"HTTP {self.http_status}"]
        if self.api_reference is not None:
            details.append(f"api_reference {self.api_reference}")
        if self.attempts is not None and self.attempts > 1:
            details.append(f"after {self.attempts} attempts")
        return f"{self.message} ({', '.join(details)})"


class APIStatusError(_ResponseError):
    """A non-2xx response (or a 2xx without a usable JSON envelope)."""

    type = "api_status_error"
    # Narrowed from the base class: always set on a response error.
    http_status: int


class AuthenticationError(APIStatusError):
    """HTTP 401: the API key is missing, wrong, disabled, expired or not allowed from this IP."""

    type = "authentication_error"


class RateLimitError(APIStatusError):
    """HTTP 429: the API key is over its requests-per-minute limit.

    The limit is a fixed UTC-minute window and the gateway sends no ``Retry-After``:
    ``retry_after`` is the seconds until the next UTC minute when the response arrived.
    """

    type = "rate_limit_error"

    def __init__(self, message: str, *, retry_after: float, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class InvalidRequestError(APIStatusError):
    """HTTP 400: the request's shape is wrong. Nothing was sent."""

    type = "invalid_request_error"


class APIServerError(APIStatusError):
    """HTTP 5xx."""

    type = "api_server_error"


class APIError(_ResponseError):
    """HTTP 2xx with ``success: false`` (``status: false`` on balances): a business refusal.

    ``code`` is the normalised code, for example ``INVALID_SENDER_ID`` or
    ``TEMPLATE_NOT_APPROVED``.
    """

    type = "api_error"
    http_status: int


class InsufficientBundleError(APIError):
    """Not enough units on the bundle for this send."""


class DuplicateReferenceError(APIError):
    """The ``user_reference_id`` was already used for this recipient and sender.

    When ``attempts`` is more than 1, an earlier attempt of this same call very probably
    succeeded: the retry was refused because that attempt had already used the reference.
    ``original_message_id`` is the original message's id when the gateway gives it (session
    sends).
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        data = self.data
        original = data.get("message_id") if isinstance(data, Mapping) else None
        self.original_message_id: str | None = original if isinstance(original, str) else None


class NoValidRecipientsError(APIError):
    """A template send where every recipient was rejected. ``results`` says why, per recipient."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        data = self.data
        items = data.get("results") if isinstance(data, Mapping) else None
        self.results: list[TemplateResult] = [
            TemplateResult.from_json(item)
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, Mapping)
        ]


class SessionWindowClosedError(APIError):
    """The 24-hour customer service window is closed: send a template instead."""


class SignatureVerificationError(Unicom360Error):
    """A webhook delivery failed verification. ``reason`` says which check failed.

    One of ``missing_signature``, ``missing_timestamp``, ``invalid_timestamp``,
    ``malformed_signature``, ``timestamp_out_of_tolerance`` or ``signature_mismatch``.
    """

    type = "signature_verification_error"

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or f"Webhook signature verification failed: {reason}")
        self.reason = reason
