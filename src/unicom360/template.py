"""Builders for :meth:`unicom360.resources.WhatsApp.send_template`.

::

    from unicom360 import TemplateBody, TemplateButton, TemplateHeader, TemplateRecipient

    recipient = TemplateRecipient(
        to="260971234567",
        user_reference_id="inv-42",
        header=TemplateHeader.image("https://example.com/receipts/ZM-4821.png"),
        body=TemplateBody.of(["Ada", "ZM-4821"]),
        buttons=[TemplateButton.url(0, "ZM-4821")],
    )

A plain string is accepted wherever a text header is, a list or a dict wherever a body is, and
a dict in the API's shape wherever a recipient or button is.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Union

__all__ = [
    "TemplateBody",
    "TemplateButton",
    "TemplateHeader",
    "TemplateRecipient",
]


class TemplateHeader:
    """A template header parameter: text (sent as a JSON string) or media (sent as an object)."""

    __slots__ = ("_value",)

    def __init__(self, value: str | Mapping[str, str]) -> None:
        self._value: str | dict[str, str] = value if isinstance(value, str) else dict(value)

    @classmethod
    def text(cls, value: str) -> TemplateHeader:
        """A text header's value."""
        return cls(value)

    @classmethod
    def image(cls, url: str) -> TemplateHeader:
        """An image header, by public HTTPS URL."""
        return cls({"type": "image", "url": url})

    @classmethod
    def video(cls, url: str) -> TemplateHeader:
        """A video header, by public HTTPS URL."""
        return cls({"type": "video", "url": url})

    @classmethod
    def document(cls, url: str, filename: str | None = None) -> TemplateHeader:
        """A document header, by public HTTPS URL, with the file name the recipient sees."""
        value = {"type": "document", "url": url}
        if filename is not None:
            value["filename"] = filename
        return cls(value)

    def to_json(self) -> str | dict[str, str]:
        """The value in the API's shape."""
        return self._value if isinstance(self._value, str) else dict(self._value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TemplateHeader) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value if isinstance(self._value, str) else tuple(self._value.items()))

    def __repr__(self) -> str:
        return f"TemplateHeader({self._value!r})"


class TemplateBody:
    """Template body parameters: positional (a list) or named (a dict of variable to value)."""

    __slots__ = ("_value",)

    def __init__(self, value: Sequence[str] | Mapping[str, str]) -> None:
        self._value: list[str] | dict[str, str] = (
            dict(value) if isinstance(value, Mapping) else list(value)
        )

    @classmethod
    def of(cls, values: Sequence[str]) -> TemplateBody:
        """Positional parameters, for ``{{1}}``, ``{{2}}``, ... in order."""
        return cls(list(values))

    @classmethod
    def named(cls, values: Mapping[str, str]) -> TemplateBody:
        """Named parameters, keyed by the template's variable names."""
        return cls(dict(values))

    def to_json(self) -> list[str] | dict[str, str]:
        """The value in the API's shape."""
        return list(self._value) if isinstance(self._value, list) else dict(self._value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TemplateBody) and other._value == self._value

    def __hash__(self) -> int:
        value = self._value
        if isinstance(value, list):
            return hash(tuple(value))
        return hash(tuple(value.items()))

    def __repr__(self) -> str:
        return f"TemplateBody({self._value!r})"


@dataclass(frozen=True)
class TemplateButton:
    """A dynamic button parameter: the button's ``index`` in the template and its value."""

    index: int
    type: str
    value: str

    @classmethod
    def url(cls, index: int, value: str) -> TemplateButton:
        """The dynamic part of a URL button."""
        return cls(index=index, type="url", value=value)

    @classmethod
    def quick_reply(cls, index: int, value: str) -> TemplateButton:
        """The payload of a quick-reply button."""
        return cls(index=index, type="quick_reply", value=value)

    def to_json(self) -> dict[str, Any]:
        """The value in the API's shape."""
        return {"index": self.index, "type": self.type, "value": self.value}


HeaderLike = Union[TemplateHeader, str, Mapping[str, str]]
BodyLike = Union[TemplateBody, Sequence[str], Mapping[str, str]]
ButtonLike = Union[TemplateButton, Mapping[str, Any]]


@dataclass(frozen=True)
class TemplateRecipient:
    """One recipient of a template send, with its own parameters.

    ``user_reference_id`` lets the gateway refuse a repeat for this recipient; when every
    recipient has one, the send is safe to retry.
    """

    to: str
    user_reference_id: str | None = None
    header: HeaderLike | None = None
    body: BodyLike | None = None
    buttons: Sequence[ButtonLike] | None = None
    #: The one-time code, for an ``AUTHENTICATION`` template.
    otp: str | None = None

    def to_json(self) -> dict[str, Any]:
        """The recipient in the API's shape, without the fields that are not set."""
        out: dict[str, Any] = {"to": self.to}
        if self.user_reference_id is not None:
            out["user_reference_id"] = self.user_reference_id
        if self.header is not None:
            out["header"] = _header_json(self.header)
        if self.body is not None:
            out["body"] = _body_json(self.body)
        if self.buttons is not None:
            out["buttons"] = [_button_json(b) for b in self.buttons]
        if self.otp is not None:
            out["otp"] = self.otp
        return out


def _header_json(header: HeaderLike) -> Any:
    if isinstance(header, TemplateHeader):
        return header.to_json()
    if isinstance(header, str):
        return header
    return dict(header)


def _body_json(body: BodyLike) -> Any:
    if isinstance(body, TemplateBody):
        return body.to_json()
    if isinstance(body, Mapping):
        return dict(body)
    if isinstance(body, str):
        # A lone string is not a list of parameters; send it as the caller gave it.
        return body
    return list(body)


def _button_json(button: ButtonLike) -> Any:
    if isinstance(button, TemplateButton):
        return button.to_json()
    return dict(button)
