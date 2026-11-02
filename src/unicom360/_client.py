from __future__ import annotations

import ipaddress
import json
import logging
import os
import platform
import random as _random
import socket
import sys
import time
import urllib.parse
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
from typing import Any, Callable, Final, NamedTuple, Union

from . import codes
from ._version import __version__
from .errors import (
    APIConnectionError,
    APIError,
    APIServerError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    ConfigurationError,
    DuplicateReferenceError,
    InsufficientBundleError,
    InvalidRequestError,
    NoValidRecipientsError,
    RateLimitError,
    SessionWindowClosedError,
    Unicom360Error,
)
from .models import Health
from .resources import BalanceResource, Email, Sms, WhatsApp
from .transport import Request, Response, Transport, TransportError, UrllibTransport

__all__ = ["DEFAULT_BASE_URL", "AppInfo", "Unicom360"]

DEFAULT_BASE_URL: Final = "https://api.unicom360.com"

_LOGGER_NAME: Final = "unicom360"
_REFERENCE_PREFIX: Final = "u360-"


@dataclass(frozen=True)
class AppInfo:
    """Your application, appended to the User-Agent so support can tell integrations apart."""

    name: str
    version: str | None = None
    url: str | None = None


AppInfoLike = Union[AppInfo, Mapping[str, str]]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]
RandomSource = Callable[[], float]
LoggerLike = Union[logging.Logger, "logging.LoggerAdapter[Any]"]


class _Operation(NamedTuple):
    name: str
    method: str
    path: str
    balance: bool = False
    auth: bool = True


OPERATIONS: Final[dict[str, _Operation]] = {
    op.name: op
    for op in (
        _Operation("sms.send", "POST", "/api/v1/json/bulk/sms"),
        _Operation("email.send", "POST", "/api/v1/json/bulk/email"),
        _Operation("whatsapp.send_template", "POST", "/api/v1/json/whatsapp/template"),
        _Operation("whatsapp.send_session", "POST", "/api/v1/json/whatsapp/session"),
        _Operation("whatsapp.status", "POST", "/api/v1/json/whatsapp/status"),
        _Operation("whatsapp.templates", "GET", "/api/v1/json/whatsapp/templates"),
        _Operation("balance.get", "POST", "/api/v1/json/balance", balance=True),
        _Operation("balance.all", "POST", "/api/v1/json/balance/all", balance=True),
        _Operation("health", "GET", "/health", auth=False),
    )
}

_API_ERROR_CLASSES: Final[dict[str, type[APIError]]] = {
    codes.INSUFFICIENT_BUNDLE: InsufficientBundleError,
    codes.DUPLICATE_REFERENCE: DuplicateReferenceError,
    codes.NO_VALID_RECIPIENTS: NoValidRecipientsError,
    codes.SESSION_WINDOW_CLOSED: SessionWindowClosedError,
}


class _NotGiven:
    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN: Final = _NotGiven()


class Parsed(NamedTuple):
    """A successful response body, and (balances only) the same body with exact decimals."""

    body: dict[str, Any]
    exact: dict[str, Any] | None


# ---------------------------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------------------------


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return address in ipaddress.IPv4Network("127.0.0.0/8")
    return address == ipaddress.IPv6Address("::1")


def _validate_base_url(value: object) -> str:
    if not isinstance(value, str):
        raise ConfigurationError("base_url must be a string")
    if value == "" or any(ch.isspace() for ch in value):
        raise ConfigurationError(f"base_url is not a valid URL: {value!r}")
    if "?" in value or "#" in value:
        raise ConfigurationError("base_url must not carry a query string or fragment")
    parts = urllib.parse.urlsplit(value)
    scheme = parts.scheme.lower()
    host = parts.hostname
    if scheme not in ("https", "http") or not host:
        raise ConfigurationError(
            f"base_url must be an absolute https URL such as {DEFAULT_BASE_URL}: {value!r}"
        )
    try:
        parts.port  # noqa: B018 - parsing the port is the check
    except ValueError as error:
        raise ConfigurationError(f"base_url has an invalid port: {value!r}") from error
    if scheme == "http" and not _is_loopback(host):
        raise ConfigurationError(
            "base_url must use https; plain http is allowed only for localhost, 127.0.0.0/8 "
            f"and ::1: {value!r}"
        )
    return value.rstrip("/")


def _positive(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ConfigurationError(f"{name} must be a number of seconds greater than 0")
    return float(value)


def _non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value >= 0:
        raise ConfigurationError(f"{name} must be a number of seconds, 0 or more")
    return float(value)


def _retries(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError("max_retries must be an integer, 0 or more")
    return value


def _app_info(value: AppInfoLike | None) -> AppInfo | None:
    if value is None or isinstance(value, AppInfo):
        return value
    if isinstance(value, Mapping) and isinstance(value.get("name"), str) and value["name"]:
        return AppInfo(name=value["name"], version=value.get("version"), url=value.get("url"))
    raise ConfigurationError("app_info needs a name: AppInfo(name, version=None, url=None)")


def _user_agent(app: AppInfo | None) -> str:
    runtime = f"{platform.python_implementation()} {platform.python_version()}"
    machine = platform.machine().lower() or "unknown"
    agent = f"unicom360-python/{__version__} ({runtime}; {sys.platform}; {machine})"
    if app is not None:
        agent += f" {app.name}"
        if app.version:
            agent += f"/{app.version}"
        if app.url:
            agent += f" (+{app.url})"
    return agent


# ---------------------------------------------------------------------------------------------
# Interpreting a response (docs/sdk-design.md section 7)
# ---------------------------------------------------------------------------------------------


def _reject_constant(name: str) -> Any:
    raise ValueError(f"not JSON: {name}")


def _parse_json(text: str, *, exact: bool = False) -> Any:
    """The parsed body, or ``None`` when it is empty or not strict JSON."""
    if text == "":
        return None
    try:
        if exact:
            return json.loads(text, parse_float=Decimal, parse_constant=_reject_constant)
        return json.loads(text, parse_constant=_reject_constant)
    except ValueError:
        return None


def message_text(value: object) -> str | None:
    """A string as is, a list of strings joined with ``"; "``, anything else ``None``."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "; ".join(value)
    return None


def _phrase(status: int) -> str:
    try:
        return f"HTTP {status} {HTTPStatus(status).phrase}"
    except ValueError:
        return f"HTTP {status}"


def _lower_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in headers.items()}


def interpret(operation: _Operation, response: Response, now: float) -> Parsed | Unicom360Error:
    """Turn one HTTP response into a result body or the error it stands for."""
    status = response.status
    text = response.body
    headers = _lower_headers(response.headers)
    body = _parse_json(text)

    if 200 <= status <= 299:
        if not isinstance(body, dict):
            return APIStatusError(
                f"{_phrase(status)}: the response is not a Unicom360 JSON object",
                code=codes.UNKNOWN,
                http_status=status,
                raw_body=text,
                headers=headers,
            )
        if operation.name == "health":
            return Parsed(body, None)
        flag = body.get("status") if operation.balance else body.get("success")
        if flag is True:
            exact = _parse_json(text, exact=True) if operation.balance else None
            return Parsed(body, exact if isinstance(exact, dict) else None)
        if flag is not False:
            name = "status" if operation.balance else "success"
            return APIStatusError(
                f"{_phrase(status)}: the response has no boolean {name!r} flag",
                code=codes.UNKNOWN,
                http_status=status,
                raw_body=text,
                headers=headers,
            )
        message = message_text(body.get("message"))
        code = codes.normalize_code(message)
        api_reference = body.get("api_reference")
        cls = _API_ERROR_CLASSES.get(code, APIError)
        return cls(
            message if message is not None else f"The request was refused ({_phrase(status)})",
            code=code,
            http_status=status,
            api_reference=api_reference if isinstance(api_reference, str) else None,
            raw_body=text,
            data=body.get("data"),
            headers=headers,
        )

    text_message: str | None = None
    code = codes.UNKNOWN
    api_reference = None
    data = None
    if isinstance(body, dict) and "message" in body:
        text_message = message_text(body["message"])
        code = codes.normalize_code(text_message)
        reference = body.get("api_reference")
        api_reference = reference if isinstance(reference, str) else None
        data = body.get("data")
    elif (
        isinstance(body, dict)
        and isinstance(body.get("errors"), dict)
        and isinstance(body["errors"].get("detail"), str)
    ):
        text_message = body["errors"]["detail"]
    fields: dict[str, Any] = {
        "code": code,
        "http_status": status,
        "api_reference": api_reference,
        "raw_body": text,
        "data": data,
        "headers": headers,
    }
    text_or_phrase = text_message if text_message is not None else _phrase(status)
    if status == 429:
        return RateLimitError(text_or_phrase, retry_after=60 - (now % 60), **fields)
    if status == 400:
        return InvalidRequestError(text_or_phrase, **fields)
    if status == 401:
        return AuthenticationError(text_or_phrase, **fields)
    if 500 <= status <= 599:
        return APIServerError(text_or_phrase, **fields)
    return APIStatusError(text_or_phrase, **fields)


# ---------------------------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------------------------


def new_reference() -> str:
    """A generated ``user_reference_id``: ``u360-`` and 32 lowercase hex characters."""
    return _REFERENCE_PREFIX + uuid.uuid4().hex


class Unicom360:
    """The Unicom360 API client.

    ::

        from unicom360 import Unicom360

        client = Unicom360()  # reads UNICOM360_API_KEY
        result = client.sms.send(from_="Unicom360", to="260971234567", message="Hello")

    Args:
        api_key: Your API key. Defaults to the ``UNICOM360_API_KEY`` environment variable.
        base_url: Defaults to ``UNICOM360_BASE_URL``, else ``https://api.unicom360.com``. Must be
            https (plain http only for localhost). A path prefix is kept.
        timeout: Seconds per attempt, from sending the request to receiving the whole body.
        connect_timeout: Seconds to establish the connection, TLS included.
        max_retries: Retries after the first attempt (so at most ``max_retries + 1`` attempts).
        max_retry_wait: Upper bound in seconds on one computed wait between attempts.
        auto_reference_ids: Give every send without a ``user_reference_id`` a generated one
            (``u360-`` and 32 hex characters), so SMS and WhatsApp sends become safe to retry.
        app_info: Your application's name, version and URL, appended to the User-Agent.
        transport: Sends the HTTP requests; see :mod:`unicom360.transport`.
        logger: Defaults to ``logging.getLogger("unicom360")``.
        clock: Returns the current Unix time in seconds (test seam).
        sleeper: Sleeps for the given seconds (test seam).
        random: Returns a float in ``[0, 1)`` for retry jitter (test seam).

    Raises:
        ConfigurationError: No API key, or an unusable option.

    The client is immutable and safe to share between threads. Use :meth:`with_options` for a
    copy with different options.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        connect_timeout: float = 10.0,
        max_retries: int = 2,
        max_retry_wait: float = 60.0,
        auto_reference_ids: bool = False,
        app_info: AppInfoLike | None = None,
        transport: Transport | None = None,
        logger: LoggerLike | None = None,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
        random: RandomSource | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("UNICOM360_API_KEY")
        if not isinstance(key, str) or key.strip() == "":
            raise ConfigurationError(
                "No API key: pass Unicom360(api_key=...) or set UNICOM360_API_KEY."
            )
        if base_url is None:
            base_url = os.environ.get("UNICOM360_BASE_URL") or DEFAULT_BASE_URL
        self._api_key = key
        self._base_url = _validate_base_url(base_url)
        self._timeout = _positive("timeout", timeout)
        self._connect_timeout = _positive("connect_timeout", connect_timeout)
        self._max_retries = _retries(max_retries)
        self._max_retry_wait = _non_negative("max_retry_wait", max_retry_wait)
        self._auto_reference_ids = bool(auto_reference_ids)
        self._app_info = _app_info(app_info)
        self._transport: Transport = transport if transport is not None else UrllibTransport()
        self._logger: LoggerLike = logger if logger is not None else logging.getLogger(_LOGGER_NAME)
        self._clock: Clock = clock if clock is not None else time.time
        self._sleeper: Sleeper = sleeper if sleeper is not None else time.sleep
        self._random: RandomSource = random if random is not None else _random.random
        self._user_agent = _user_agent(self._app_info)

        self.sms: Final = Sms(self)
        """SMS: :meth:`~unicom360.resources.Sms.send`."""
        self.email: Final = Email(self)
        """Email: :meth:`~unicom360.resources.Email.send`."""
        self.whatsapp: Final = WhatsApp(self)
        """WhatsApp: templates, session messages, status and the template list."""
        self.balance: Final = BalanceResource(self)
        """Balances: :meth:`~unicom360.resources.BalanceResource.get` and ``all``."""

    # -- read-only options ---------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def connect_timeout(self) -> float:
        return self._connect_timeout

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def max_retry_wait(self) -> float:
        return self._max_retry_wait

    @property
    def auto_reference_ids(self) -> bool:
        return self._auto_reference_ids

    @property
    def user_agent(self) -> str:
        return self._user_agent

    def __repr__(self) -> str:
        return (
            f"Unicom360(base_url={self._base_url!r}, api_key=[REDACTED], "
            f"timeout={self._timeout}, max_retries={self._max_retries})"
        )

    def with_options(
        self,
        *,
        api_key: str | _NotGiven = NOT_GIVEN,
        base_url: str | _NotGiven = NOT_GIVEN,
        timeout: float | _NotGiven = NOT_GIVEN,
        connect_timeout: float | _NotGiven = NOT_GIVEN,
        max_retries: int | _NotGiven = NOT_GIVEN,
        max_retry_wait: float | _NotGiven = NOT_GIVEN,
        auto_reference_ids: bool | _NotGiven = NOT_GIVEN,
        app_info: AppInfoLike | _NotGiven | None = NOT_GIVEN,
        transport: Transport | _NotGiven = NOT_GIVEN,
        logger: LoggerLike | _NotGiven = NOT_GIVEN,
        clock: Clock | _NotGiven = NOT_GIVEN,
        sleeper: Sleeper | _NotGiven = NOT_GIVEN,
        random: RandomSource | _NotGiven = NOT_GIVEN,
    ) -> Unicom360:
        """A copy of this client with the given options changed; the rest are kept."""
        return Unicom360(
            api_key=self._api_key if isinstance(api_key, _NotGiven) else api_key,
            base_url=self._base_url if isinstance(base_url, _NotGiven) else base_url,
            timeout=self._timeout if isinstance(timeout, _NotGiven) else timeout,
            connect_timeout=(
                self._connect_timeout if isinstance(connect_timeout, _NotGiven) else connect_timeout
            ),
            max_retries=self._max_retries if isinstance(max_retries, _NotGiven) else max_retries,
            max_retry_wait=(
                self._max_retry_wait if isinstance(max_retry_wait, _NotGiven) else max_retry_wait
            ),
            auto_reference_ids=(
                self._auto_reference_ids
                if isinstance(auto_reference_ids, _NotGiven)
                else auto_reference_ids
            ),
            app_info=self._app_info if isinstance(app_info, _NotGiven) else app_info,
            transport=self._transport if isinstance(transport, _NotGiven) else transport,
            logger=self._logger if isinstance(logger, _NotGiven) else logger,
            clock=self._clock if isinstance(clock, _NotGiven) else clock,
            sleeper=self._sleeper if isinstance(sleeper, _NotGiven) else sleeper,
            random=self._random if isinstance(random, _NotGiven) else random,
        )

    # -- operations ----------------------------------------------------------------------------

    def health(self, *, timeout: float | None = None, max_retries: int | None = None) -> Health:
        """Gateway liveness. Sends no API key."""
        parsed = self._request(
            "health", None, retry_safe=True, timeout=timeout, max_retries=max_retries
        )
        return Health.from_json(parsed.body)

    # -- internals used by the resources -------------------------------------------------------

    def _reference(self, value: object, generated: list[str]) -> object:
        """Fill in a generated reference when ``auto_reference_ids`` is on and none was given."""
        if self._auto_reference_ids and value is None:
            reference = new_reference()
            generated.append(reference)
            return reference
        return value

    def _request(
        self,
        operation_name: str,
        body: dict[str, Any] | None,
        *,
        retry_safe: bool,
        timeout: float | None,
        max_retries: int | None,
        generated: list[str] | None = None,
    ) -> Parsed:
        operation = OPERATIONS[operation_name]
        retries = self._max_retries if max_retries is None else _retries(max_retries)
        attempt_timeout = self._timeout if timeout is None else _positive("timeout", timeout)

        headers = {"Accept": "application/json", "User-Agent": self._user_agent}
        if operation.auth:
            headers["X-API-Key"] = self._api_key
        payload: bytes | None = None
        if operation.method == "POST":
            headers["Content-Type"] = "application/json"
            payload = json.dumps(
                body if body is not None else {}, ensure_ascii=True, separators=(",", ":")
            ).encode("ascii")
        request = Request(
            method=operation.method,
            url=self._base_url + operation.path,
            headers=headers,
            body=payload,
            timeout=attempt_timeout,
            connect_timeout=self._connect_timeout,
        )

        attempt = 1
        while True:
            started = time.perf_counter()
            now = 0.0
            rate_limited = False
            try:
                response = self._transport.send(request)
            except Exception as failure:
                # Every transport failure is classified, a custom transport's included.
                connection_error = _connection_error(failure)
                error: Unicom360Error = connection_error
                retryable = not connection_error.sent or retry_safe
                self._log_attempt(
                    operation, connection_error.type, None, attempt, started, generated
                )
            else:
                now = self._clock()
                outcome = interpret(operation, response, now)
                self._log_attempt(
                    operation,
                    str(response.status),
                    outcome.api_reference
                    if isinstance(outcome, Unicom360Error)
                    else _reference_of(outcome.body),
                    attempt,
                    started,
                    generated,
                )
                if isinstance(outcome, Parsed):
                    return outcome
                error = outcome
                status = response.status
                rate_limited = status == 429
                retryable = (
                    rate_limited
                    or (500 <= status <= 599 and retry_safe)
                    or (
                        isinstance(error, APIError)
                        and error.code == codes.SEND_FAILED
                        and retry_safe
                    )
                )

            if not retryable or attempt > retries:
                error.attempts = attempt
                raise error
            if rate_limited:
                base = 60 - (now % 60)
                if base > self._max_retry_wait:
                    error.attempts = attempt
                    raise error
                wait = max(1.0, base + self._random())
            else:
                wait = self._random() * min(8.0, 0.5 * 2**attempt, self._max_retry_wait)
            self._logger.info(
                "unicom360 retrying %s %s after attempt=%d wait_s=%.3f cause=%s",
                operation.method,
                operation.path,
                attempt,
                wait,
                _cause(error),
            )
            self._sleeper(wait)
            attempt += 1

    def _log_attempt(
        self,
        operation: _Operation,
        status: str,
        api_reference: str | None,
        attempt: int,
        started: float,
        generated: list[str] | None,
    ) -> None:
        if not self._logger.isEnabledFor(logging.DEBUG):
            return
        duration_ms = int((time.perf_counter() - started) * 1000)
        line = "unicom360 %s %s status=%s api_reference=%s attempt=%d duration_ms=%d"
        args: list[Any] = [
            operation.method,
            operation.path,
            status,
            api_reference or "-",
            attempt,
            duration_ms,
        ]
        if generated:
            line += " generated_user_reference_ids=%s"
            args.append(",".join(generated))
        self._logger.debug(line, *args)


def _reference_of(body: Mapping[str, Any]) -> str | None:
    value = body.get("api_reference")
    return value if isinstance(value, str) else None


def _cause(error: Unicom360Error) -> str:
    if isinstance(error, (APIStatusError, APIError)):
        return f"{error.type}(HTTP {error.http_status}, {error.code})"
    return error.type


_TIMEOUT_TYPES: Final = (TimeoutError, socket.timeout)


def _connection_error(failure: Exception) -> APIConnectionError:
    if isinstance(failure, TransportError):
        sent, timed_out = failure.sent, failure.timeout
        cause: BaseException = failure.cause if failure.cause is not None else failure
        message = str(failure) or "The request to the Unicom360 API failed"
    else:
        # Anything the SDK cannot classify may have reached the server.
        sent, timed_out = True, isinstance(failure, _TIMEOUT_TYPES)
        cause = failure
        message = f"The request to the Unicom360 API failed: {failure!r}"
    cls = APITimeoutError if timed_out else APIConnectionError
    error = cls(message, sent=sent, cause=cause)
    error.__cause__ = cause
    return error
