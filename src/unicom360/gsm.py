"""Opt-in GSM-7 helpers: check an SMS text the way the gateway will, before you send it.

The gateway accepts only GSM-7 text (the basic set plus ``^{}\\[~]|€``, no form feed), at most
1,200 characters, and bills ``max(1, ceil(length / 160))`` units per recipient, where a CR LF
pair counts as one character. These helpers give the same answers::

    from unicom360 import gsm

    gsm.validate_sms("It’s ready")   # [SmsIssue.NON_GSM]: the apostrophe is typographic
    gsm.units("a" * 161)             # 2

The client never calls them: an invalid text is refused by the gateway, not by the SDK.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Final

__all__ = [
    "CHARSET",
    "MAX_LENGTH",
    "UNIT_LENGTH",
    "NonGsmCharacter",
    "SmsIssue",
    "is_gsm7",
    "length",
    "non_gsm_characters",
    "units",
    "validate_sms",
]

#: Every character the gateway accepts (``sms_part_counter`` 0.1.7's set, in its order).
CHARSET: Final = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    "^{}\\[~]|€"
)
#: The longest text the gateway accepts, in characters (CR LF counting as one).
MAX_LENGTH: Final = 1200
#: Characters per billing unit.
UNIT_LENGTH: Final = 160

_CHARSET: Final = frozenset(CHARSET)
_BLANK: Final = frozenset(" \t\r\n")


class SmsIssue(str, enum.Enum):
    """A reason the gateway would refuse a text. Compares equal to its string value."""

    EMPTY = "empty"
    """The text is empty or only spaces, tabs, CR and LF."""
    TOO_LONG = "too_long"
    """More than 1,200 characters."""
    NON_GSM = "non_gsm"
    """At least one character outside the GSM-7 set."""

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class NonGsmCharacter:
    """A character outside the GSM-7 set and its 0-based code point index in the text."""

    char: str
    index: int


def is_gsm7(text: str) -> bool:
    """Whether every character is in the gateway's GSM-7 set (``""`` is)."""
    return all(ch in _CHARSET for ch in text)


def length(text: str) -> int:
    """Characters as the gateway counts them: code points, with each CR LF pair as one."""
    return len(text) - text.count("\r\n")


def units(text: str) -> int:
    """Billing units per recipient: ``max(1, ceil(length / 160))`` (not GSM segments)."""
    return max(1, math.ceil(length(text) / UNIT_LENGTH))


def non_gsm_characters(text: str) -> list[NonGsmCharacter]:
    """Every character outside the set, in order, with its code point index.

    Indexes count code points (an emoji is one; CR LF is two here).
    """
    return [NonGsmCharacter(ch, i) for i, ch in enumerate(text) if ch not in _CHARSET]


def validate_sms(text: str) -> list[SmsIssue]:
    """The reasons the gateway would refuse ``text``, in the order empty, too_long, non_gsm.

    An empty list means the gateway would accept the text.
    """
    issues: list[SmsIssue] = []
    if all(ch in _BLANK for ch in text):
        issues.append(SmsIssue.EMPTY)
    if length(text) > MAX_LENGTH:
        issues.append(SmsIssue.TOO_LONG)
    if not is_gsm7(text):
        issues.append(SmsIssue.NON_GSM)
    return issues
