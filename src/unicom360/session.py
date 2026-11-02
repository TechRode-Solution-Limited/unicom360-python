"""Builders for WhatsApp session messages (:meth:`unicom360.resources.WhatsApp.send_session`).

One function per content type. Each returns a :class:`SessionMessage` and takes the common
keyword arguments ``from_``, ``reply_to`` (all but :func:`reaction`), ``user_reference_id`` and
``callback_url``::

    from unicom360 import session

    message = session.text("260971234567", "Your order is ready.", user_reference_id="s-1")
    client.whatsapp.send_session(message)

``reply_to`` and a reaction's ``message_id`` take either a ``message_id`` a send returned or
the ``wamid.`` id of an inbound message, exactly as a ``message.received`` webhook delivers it.

Nothing is validated here: the gateway checks lengths and shapes and answers with an error.
"""

from __future__ import annotations

import builtins
import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple, Union

__all__ = [
    "ContactCard",
    "ListRow",
    "ListSection",
    "ReplyButton",
    "SessionMessage",
    "audio",
    "buttons",
    "contacts",
    "document",
    "image",
    "list",
    "location",
    "reaction",
    "sticker",
    "text",
    "video",
]

#: A contact card in Meta's shape (``name``, ``phones``, ``emails``, ``urls``, ``org``, ...).
ContactCard = Mapping[str, Any]


class SessionMessage:
    """A session message in the API's shape. Build one with this module's functions."""

    __slots__ = ("_payload",)

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload: dict[str, Any] = copy.deepcopy(dict(payload))

    @property
    def type(self) -> str | None:
        """The content type (``text``, ``image``, ``interactive``, ...)."""
        value = self._payload.get("type")
        return value if isinstance(value, str) else None

    @property
    def to(self) -> str | None:
        """The recipient."""
        value = self._payload.get("to")
        return value if isinstance(value, str) else None

    @property
    def user_reference_id(self) -> str | None:
        """The reference the gateway de-duplicates on, if set."""
        value = self._payload.get("user_reference_id")
        return value if isinstance(value, str) else None

    def to_json(self) -> dict[str, Any]:
        """A copy of the message in the API's shape."""
        return copy.deepcopy(self._payload)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SessionMessage) and other._payload == self._payload

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"SessionMessage(type={self.type!r}, to={self.to!r})"


class ReplyButton(NamedTuple):
    """A reply button of an interactive message: its ``id`` (returned to you) and ``title``."""

    id: str
    title: str


@dataclass(frozen=True)
class ListRow:
    """A row of an interactive list."""

    id: str
    title: str
    description: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "title": self.title}
        if self.description is not None:
            out["description"] = self.description
        return out


@dataclass(frozen=True)
class ListSection:
    """A section of an interactive list: its rows and an optional title."""

    rows: Sequence[ListRow | Mapping[str, Any]]
    title: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.title is not None:
            out["title"] = self.title
        out["rows"] = [r.to_json() if isinstance(r, ListRow) else dict(r) for r in self.rows]
        return out


ButtonLike = Union[ReplyButton, tuple[str, str], Mapping[str, Any]]
SectionLike = Union[ListSection, Mapping[str, Any]]


def _message(
    to: str,
    type_: str,
    content: Mapping[str, Any],
    *,
    from_: str | None,
    reply_to: str | None,
    user_reference_id: str | None,
    callback_url: str | None,
) -> SessionMessage:
    payload: dict[str, Any] = {"to": to, "type": type_}
    payload.update(content)
    if from_ is not None:
        payload["from"] = from_
    if reply_to is not None:
        payload["reply_to"] = reply_to
    if user_reference_id is not None:
        payload["user_reference_id"] = user_reference_id
    if callback_url is not None:
        payload["callback_url"] = callback_url
    return SessionMessage(payload)


def _media(url: str, caption: str | None = None, filename: str | None = None) -> dict[str, Any]:
    media: dict[str, Any] = {"url": url}
    if caption is not None:
        media["caption"] = caption
    if filename is not None:
        media["filename"] = filename
    return media


def _json_value(value: Any) -> Any:
    """A deep copy of ``value`` with every mapping a dict and every sequence a list."""
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (str, bytes)):
        return value
    if isinstance(value, Sequence):
        return [_json_value(v) for v in value]
    return value


def text(
    to: str,
    text: str,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """A text message."""
    return _message(
        to,
        "text",
        {"text": text},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def image(
    to: str,
    url: str,
    caption: str | None = None,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """An image, by public HTTPS URL, with an optional caption."""
    return _message(
        to,
        "image",
        {"media": _media(url, caption)},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def video(
    to: str,
    url: str,
    caption: str | None = None,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """A video, by public HTTPS URL, with an optional caption."""
    return _message(
        to,
        "video",
        {"media": _media(url, caption)},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def document(
    to: str,
    url: str,
    caption: str | None = None,
    filename: str | None = None,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """A document, by public HTTPS URL, with an optional caption and file name."""
    return _message(
        to,
        "document",
        {"media": _media(url, caption, filename)},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def audio(
    to: str,
    url: str,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """An audio file, by public HTTPS URL (no caption)."""
    return _message(
        to,
        "audio",
        {"media": _media(url)},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def sticker(
    to: str,
    url: str,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """A sticker, by public HTTPS URL (no caption)."""
    return _message(
        to,
        "sticker",
        {"media": _media(url)},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def _reply_button(button: ButtonLike) -> dict[str, Any]:
    if isinstance(button, Mapping):
        return dict(button)
    button_id, title = button
    return {"id": button_id, "title": title}


def buttons(
    to: str,
    body: str,
    buttons: Sequence[ButtonLike],
    header: str | None = None,
    footer: str | None = None,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """An interactive message with up to three reply buttons, each an ``(id, title)`` pair."""
    interactive: dict[str, Any] = {
        "type": "button",
        "body": body,
        "buttons": [_reply_button(b) for b in buttons],
    }
    if header is not None:
        interactive["header"] = header
    if footer is not None:
        interactive["footer"] = footer
    return _message(
        to,
        "interactive",
        {"interactive": interactive},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


# Named after the contract's canonical builder; this module uses builtins.list where it needs one.
def list(
    to: str,
    body: str,
    button: str,
    sections: Sequence[SectionLike],
    header: str | None = None,
    footer: str | None = None,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """An interactive list: ``button`` opens it, ``sections`` hold the rows."""
    interactive: dict[str, Any] = {
        "type": "list",
        "body": body,
        "button": button,
        "sections": [s.to_json() if isinstance(s, ListSection) else dict(s) for s in sections],
    }
    if header is not None:
        interactive["header"] = header
    if footer is not None:
        interactive["footer"] = footer
    return _message(
        to,
        "interactive",
        {"interactive": interactive},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def location(
    to: str,
    latitude: float,
    longitude: float,
    name: str | None = None,
    address: str | None = None,
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """A location pin."""
    pin: dict[str, Any] = {"latitude": latitude, "longitude": longitude}
    if name is not None:
        pin["name"] = name
    if address is not None:
        pin["address"] = address
    return _message(
        to,
        "location",
        {"location": pin},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def contacts(
    to: str,
    contacts: Sequence[ContactCard],
    *,
    from_: str | None = None,
    reply_to: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """One or more contact cards, in Meta's shape."""
    cards: builtins.list[Any] = [_json_value(card) for card in contacts]
    return _message(
        to,
        "contacts",
        {"contacts": cards},
        from_=from_,
        reply_to=reply_to,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )


def reaction(
    to: str,
    message_id: str,
    emoji: str,
    *,
    from_: str | None = None,
    user_reference_id: str | None = None,
    callback_url: str | None = None,
) -> SessionMessage:
    """A reaction to a message. An empty ``emoji`` removes your reaction (sent as ``""``)."""
    return _message(
        to,
        "reaction",
        {"reaction": {"message_id": message_id, "emoji": emoji}},
        from_=from_,
        reply_to=None,
        user_reference_id=user_reference_id,
        callback_url=callback_url,
    )
