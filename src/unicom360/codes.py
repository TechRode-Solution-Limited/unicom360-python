"""Normalised error codes and the function that derives them from a server message.

The gateway answers a refusal with a code (``TEMPLATE_NOT_APPROVED``), a code with detail
(``INSUFFICIENT_BUNDLE: no international SMS bundle``) or an English sentence
(``Invalid From Sender ID``). :func:`normalize_code` turns each into one stable code, which is
what :attr:`unicom360.APIError.code` holds.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = [
    "AUTHENTICATION_FAILED",
    "BODY_PARAMETERS_INVALID",
    "BUTTON_PARAMETERS_INVALID",
    "CLIENT_DISABLED",
    "CLIENT_NOT_FOUND",
    "CREDENTIAL_DISABLED",
    "CREDENTIAL_EXPIRED",
    "DUPLICATE_REFERENCE",
    "HEADER_PARAMETER_INVALID",
    "INSUFFICIENT_BUNDLE",
    "INVALID_AUTHORIZATION",
    "INVALID_NUMBER",
    "INVALID_PARAMETERS",
    "INVALID_RECIPIENT_LIMIT",
    "INVALID_SENDER_ID",
    "INVALID_USER_REFERENCE_ID",
    "IP_NOT_ALLOWED",
    "LANGUAGE_REQUIRED",
    "MEDIA_URL_INVALID",
    "MISSING_API_KEY",
    "NO_VALID_RECIPIENTS",
    "OTP_INVALID",
    "OTP_REQUIRED",
    "RATE_LIMIT_EXCEEDED",
    "REACTION_TARGET_NOT_FOUND",
    "REPLY_TO_NOT_FOUND",
    "SENDER_ID_NOT_ALLOWED",
    "SENDER_REQUIRED",
    "SEND_FAILED",
    "SESSION_WINDOW_CLOSED",
    "TEMPLATE_NOT_APPROVED",
    "TEMPLATE_NOT_FOUND",
    "TEMPLATE_SENDER_MISMATCH",
    "UNKNOWN",
    "normalize_code",
]

# Codes produced by the alias table.
INVALID_SENDER_ID: Final = "INVALID_SENDER_ID"
SENDER_ID_NOT_ALLOWED: Final = "SENDER_ID_NOT_ALLOWED"
INVALID_RECIPIENT_LIMIT: Final = "INVALID_RECIPIENT_LIMIT"
INSUFFICIENT_BUNDLE: Final = "INSUFFICIENT_BUNDLE"
DUPLICATE_REFERENCE: Final = "DUPLICATE_REFERENCE"
INVALID_PARAMETERS: Final = "INVALID_PARAMETERS"
MISSING_API_KEY: Final = "MISSING_API_KEY"
INVALID_AUTHORIZATION: Final = "INVALID_AUTHORIZATION"

# Codes the gateway sends as they are.
SENDER_REQUIRED: Final = "SENDER_REQUIRED"
TEMPLATE_NOT_FOUND: Final = "TEMPLATE_NOT_FOUND"
TEMPLATE_NOT_APPROVED: Final = "TEMPLATE_NOT_APPROVED"
LANGUAGE_REQUIRED: Final = "LANGUAGE_REQUIRED"
TEMPLATE_SENDER_MISMATCH: Final = "TEMPLATE_SENDER_MISMATCH"
NO_VALID_RECIPIENTS: Final = "NO_VALID_RECIPIENTS"
SEND_FAILED: Final = "SEND_FAILED"
SESSION_WINDOW_CLOSED: Final = "SESSION_WINDOW_CLOSED"
REPLY_TO_NOT_FOUND: Final = "REPLY_TO_NOT_FOUND"
REACTION_TARGET_NOT_FOUND: Final = "REACTION_TARGET_NOT_FOUND"
INVALID_NUMBER: Final = "INVALID_NUMBER"
INVALID_USER_REFERENCE_ID: Final = "INVALID_USER_REFERENCE_ID"
MEDIA_URL_INVALID: Final = "MEDIA_URL_INVALID"
BODY_PARAMETERS_INVALID: Final = "BODY_PARAMETERS_INVALID"
HEADER_PARAMETER_INVALID: Final = "HEADER_PARAMETER_INVALID"
BUTTON_PARAMETERS_INVALID: Final = "BUTTON_PARAMETERS_INVALID"
OTP_REQUIRED: Final = "OTP_REQUIRED"
OTP_INVALID: Final = "OTP_INVALID"
CLIENT_NOT_FOUND: Final = "CLIENT_NOT_FOUND"
AUTHENTICATION_FAILED: Final = "AUTHENTICATION_FAILED"
CREDENTIAL_DISABLED: Final = "CREDENTIAL_DISABLED"
CLIENT_DISABLED: Final = "CLIENT_DISABLED"
CREDENTIAL_EXPIRED: Final = "CREDENTIAL_EXPIRED"
IP_NOT_ALLOWED: Final = "IP_NOT_ALLOWED"
RATE_LIMIT_EXCEEDED: Final = "RATE_LIMIT_EXCEEDED"

#: Request-shape sentences, Phoenix error details, empty text and anything unrecognised.
UNKNOWN: Final = "UNKNOWN"

_ALIASES: Final[dict[str, str]] = {
    "Invalid From Sender ID": INVALID_SENDER_ID,
    "Invalid Sender": INVALID_SENDER_ID,
    "From Sender ID not allowed": SENDER_ID_NOT_ALLOWED,
    "Sender not allowed": SENDER_ID_NOT_ALLOWED,
    "Recipient list size is invalid": INVALID_RECIPIENT_LIMIT,
    "Invalid Recipient Limit": INVALID_RECIPIENT_LIMIT,
    "INSUFFICIENT_BUNDLE: no international SMS bundle": INSUFFICIENT_BUNDLE,
    "Insufficient bundle": INSUFFICIENT_BUNDLE,
    "INSUFFICIENT_BUNDLE_LIMIT": INSUFFICIENT_BUNDLE,
    "duplicate user reference id": DUPLICATE_REFERENCE,
    "DUPLICATE_MSG_REF": DUPLICATE_REFERENCE,
    "Invalid parameters provided": INVALID_PARAMETERS,
    "Missing API key. Provide X-API-Key header or Authorization: Bearer <api_key>": (
        MISSING_API_KEY
    ),
    "Invalid authorization format. Use 'Bearer <api_key>' or 'Basic <base64>'": (
        INVALID_AUTHORIZATION
    ),
    "Invalid Basic auth format. Use api_key as username": INVALID_AUTHORIZATION,
    "Invalid Base64 encoding in Basic auth": INVALID_AUTHORIZATION,
}

# [A-Z] and [0-9] are ASCII ranges. The whitespace class is spelled out to match the contract's
# (JavaScript's) \s exactly; Python's own \s differs on a few control and format characters.
_JS_WHITESPACE = "\t\n\v\f\r    -     　﻿"
_CODE = re.compile(r"[A-Z][A-Z0-9_]*")
_CODE_PREFIX = re.compile(r"([A-Z][A-Z0-9_]*):[" + _JS_WHITESPACE + "]")


def normalize_code(message: object) -> str:
    """Return the normalised code for a server message.

    The first matching rule wins: an exact alias; a whole message that is already a code
    (``^[A-Z][A-Z0-9_]*$``, aliased if the table knows it); a code followed by ``": "`` and
    detail (the code, aliased if known); otherwise ``"UNKNOWN"``. Matching is exact and
    case-sensitive, nothing is trimmed, and a non-string gives ``"UNKNOWN"``.
    """
    if not isinstance(message, str):
        return UNKNOWN
    alias = _ALIASES.get(message)
    if alias is not None:
        return alias
    if _CODE.fullmatch(message):
        return message
    prefix = _CODE_PREFIX.match(message)
    if prefix is not None:
        code = prefix.group(1)
        return _ALIASES.get(code, code)
    return UNKNOWN
