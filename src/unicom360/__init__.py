"""The official Python SDK for the Unicom360 SMS, email and WhatsApp API.

::

    from unicom360 import Unicom360

    client = Unicom360()  # reads UNICOM360_API_KEY
    result = client.sms.send(from_="Unicom360", to="260971234567", message="Hello")

See https://unicom360.com/docs for the API reference.
"""

import logging

from . import codes, gsm, session, webhooks
from ._client import DEFAULT_BASE_URL, AppInfo, Unicom360
from ._version import CONTRACT_VERSION, __version__
from .codes import normalize_code
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
    SignatureVerificationError,
    Unicom360Error,
)
from .models import (
    Balance,
    Balances,
    BundleType,
    EmailResult,
    EmailSendResult,
    Health,
    MessageError,
    MessageStatus,
    SessionSendResult,
    SmsResult,
    SmsSendResult,
    StatusResult,
    TemplateAuthentication,
    TemplateBodyInfo,
    TemplateButtonInfo,
    TemplateHeaderInfo,
    TemplateInfo,
    TemplateList,
    TemplateResult,
    TemplateSendResult,
)
from .session import ListRow, ListSection, ReplyButton, SessionMessage
from .template import TemplateBody, TemplateButton, TemplateHeader, TemplateRecipient
from .transport import Request, Response, Transport, TransportError, UrllibTransport

__all__ = [
    "CONTRACT_VERSION",
    "DEFAULT_BASE_URL",
    "APIConnectionError",
    "APIError",
    "APIServerError",
    "APIStatusError",
    "APITimeoutError",
    "AppInfo",
    "AuthenticationError",
    "Balance",
    "Balances",
    "BundleType",
    "ConfigurationError",
    "DuplicateReferenceError",
    "EmailResult",
    "EmailSendResult",
    "Health",
    "InsufficientBundleError",
    "InvalidRequestError",
    "ListRow",
    "ListSection",
    "MessageError",
    "MessageStatus",
    "NoValidRecipientsError",
    "RateLimitError",
    "ReplyButton",
    "Request",
    "Response",
    "SessionMessage",
    "SessionSendResult",
    "SessionWindowClosedError",
    "SignatureVerificationError",
    "SmsResult",
    "SmsSendResult",
    "StatusResult",
    "TemplateAuthentication",
    "TemplateBody",
    "TemplateBodyInfo",
    "TemplateButton",
    "TemplateButtonInfo",
    "TemplateHeader",
    "TemplateHeaderInfo",
    "TemplateInfo",
    "TemplateList",
    "TemplateRecipient",
    "TemplateResult",
    "TemplateSendResult",
    "Transport",
    "TransportError",
    "Unicom360",
    "Unicom360Error",
    "UrllibTransport",
    "__version__",
    "codes",
    "gsm",
    "normalize_code",
    "session",
    "webhooks",
]

# A library logs through "unicom360" and leaves handlers to the application.
logging.getLogger("unicom360").addHandler(logging.NullHandler())
