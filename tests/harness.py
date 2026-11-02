"""The conformance harness: fixture loading, fakes, the operation mapping and canonical form.

The fixtures under ``tests/conformance`` are vendored from ``unicom360-openapi`` (see
``conformance/README.md`` there). Every vector of every file runs through the public API; a
vector this harness does not understand fails rather than being skipped.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import unicom360
from unicom360 import (
    Request,
    Response,
    TemplateBody,
    TemplateButton,
    TemplateHeader,
    TemplateRecipient,
    TransportError,
    Unicom360,
    session,
)
from unicom360.session import ListRow, ListSection, ReplyButton, SessionMessage

FIXTURES = Path(__file__).parent / "conformance"
API_KEY = "test-api-key"

OPERATIONS = (
    "sms.send",
    "email.send",
    "whatsapp.send_template",
    "whatsapp.send_session",
    "whatsapp.status",
    "whatsapp.templates",
    "balance.get",
    "balance.all",
    "health",
)


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def vectors(name: str) -> list[Any]:
    """One ``pytest.param`` per vector, with the vector's id as the test id."""
    return [pytest.param(v, id=v["id"]) for v in load(name)["vectors"]]


def check_keys(vector: Mapping[str, Any], required: Iterable[str], optional: Iterable[str]) -> None:
    """Fail on a vector shape this harness does not understand."""
    keys = set(vector)
    missing = set(required) - keys
    unknown = keys - set(required) - set(optional)
    assert not missing, f"{vector.get('id')}: missing keys {sorted(missing)}"
    assert not unknown, (
        f"{vector.get('id')}: keys this harness does not understand {sorted(unknown)}"
    )


# ---------------------------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------------------------

_TRANSPORT_FAILURES = {
    "connect_refused": (False, False),
    "dns_failure": (False, False),
    "timeout_after_send": (True, True),
    "reset_after_send": (True, False),
}


def http_response(http: Mapping[str, Any]) -> Response:
    check_keys(http, ("status", "headers", "body_text"), ())
    return Response(status=http["status"], headers=dict(http["headers"]), body=http["body_text"])


def step(spec: Mapping[str, Any]) -> Response | TransportError:
    """A ``retries.json`` step: an HTTP response or a transport failure."""
    if "http" in spec:
        check_keys(spec, ("http",), ())
        return http_response(spec["http"])
    check_keys(spec, ("transport",), ())
    kind = spec["transport"]
    assert kind in _TRANSPORT_FAILURES, f"unknown transport failure {kind!r}"
    sent, timeout = _TRANSPORT_FAILURES[kind]
    return TransportError(kind, sent=sent, timeout=timeout)


class FakeTransport:
    """Answers attempt n with ``steps[n - 1]`` and records every request."""

    def __init__(self, steps: Sequence[Response | TransportError]) -> None:
        self.steps = list(steps)
        self.requests: list[Request] = []

    def send(self, request: Request) -> Response:
        self.requests.append(request)
        index = len(self.requests) - 1
        assert index < len(self.steps), f"unexpected attempt {index + 1}: no step for it"
        outcome = self.steps[index]
        if isinstance(outcome, TransportError):
            raise outcome
        return outcome


class FakeTime:
    """A clock that moves only when the sleeper sleeps, by exactly the seconds slept."""

    def __init__(self, now: float) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(
    transport: FakeTransport,
    *,
    now: float = 1767225630,
    max_retries: int = 0,
    max_retry_wait: float = 60,
    random: Any = None,
    fake_time: FakeTime | None = None,
    **options: Any,
) -> Unicom360:
    time = fake_time if fake_time is not None else FakeTime(now)
    return Unicom360(
        API_KEY,
        max_retries=max_retries,
        max_retry_wait=max_retry_wait,
        transport=transport,
        clock=time.clock,
        sleeper=time.sleep,
        random=random if random is not None else (lambda: 0.5),
        **options,
    )


# ---------------------------------------------------------------------------------------------
# Operations: canonical params (API names) to SDK calls
# ---------------------------------------------------------------------------------------------


class Params:
    """Reads a params object and fails if any key is left unread."""

    def __init__(self, what: str, params: Mapping[str, Any]) -> None:
        assert isinstance(params, Mapping), f"{what}: params must be an object"
        self.what = what
        self.params = dict(params)
        self.read: set[str] = set()

    def req(self, key: str) -> Any:
        assert key in self.params, f"{self.what}: missing {key!r}"
        self.read.add(key)
        return self.params[key]

    def opt(self, key: str) -> Any:
        self.read.add(key)
        return self.params.get(key)

    def done(self) -> None:
        unread = set(self.params) - self.read
        assert not unread, f"{self.what}: params this harness does not understand {sorted(unread)}"


def _header(value: Any) -> TemplateHeader:
    if isinstance(value, str):
        return TemplateHeader.text(value)
    p = Params("template header", value)
    kind = p.req("type")
    url = p.req("url")
    if kind == "image":
        header = TemplateHeader.image(url)
    elif kind == "video":
        header = TemplateHeader.video(url)
    elif kind == "document":
        header = TemplateHeader.document(url, p.opt("filename"))
    else:
        raise AssertionError(f"unknown template header type {kind!r}")
    p.done()
    return header


def _body(value: Any) -> TemplateBody:
    if isinstance(value, list):
        return TemplateBody.of(value)
    assert isinstance(value, dict), "template body must be a list or an object"
    return TemplateBody.named(value)


def _button(value: Any) -> TemplateButton:
    p = Params("template button", value)
    kind = p.req("type")
    index = p.req("index")
    text = p.req("value")
    p.done()
    if kind == "url":
        return TemplateButton.url(index, text)
    if kind == "quick_reply":
        return TemplateButton.quick_reply(index, text)
    raise AssertionError(f"unknown template button type {kind!r}")


def recipient(value: Any) -> TemplateRecipient:
    p = Params("template recipient", value)
    header = p.opt("header")
    body = p.opt("body")
    buttons = p.opt("buttons")
    built = TemplateRecipient(
        to=p.req("to"),
        user_reference_id=p.opt("user_reference_id"),
        header=_header(header) if header is not None else None,
        body=_body(body) if body is not None else None,
        buttons=[_button(b) for b in buttons] if buttons is not None else None,
        otp=p.opt("otp"),
    )
    p.done()
    return built


def session_message(params: Mapping[str, Any]) -> SessionMessage:
    """Build a session message with the factory for ``params["type"]``."""
    p = Params("session message", params)
    to = p.req("to")
    kind = p.req("type")
    common: dict[str, Any] = {
        "from_": p.opt("from"),
        "user_reference_id": p.opt("user_reference_id"),
        "callback_url": p.opt("callback_url"),
    }
    reply_to = p.opt("reply_to")
    if kind != "reaction":
        common["reply_to"] = reply_to
    else:
        assert reply_to is None, "a reaction takes no reply_to"

    message: SessionMessage
    if kind == "text":
        message = session.text(to, p.req("text"), **common)
    elif kind in ("image", "video", "document", "audio", "sticker"):
        m = Params(f"{kind} media", p.req("media"))
        url = m.req("url")
        if kind == "image":
            message = session.image(to, url, m.opt("caption"), **common)
        elif kind == "video":
            message = session.video(to, url, m.opt("caption"), **common)
        elif kind == "document":
            message = session.document(to, url, m.opt("caption"), m.opt("filename"), **common)
        elif kind == "audio":
            message = session.audio(to, url, **common)
        else:
            message = session.sticker(to, url, **common)
        m.done()
    elif kind == "interactive":
        i = Params("interactive", p.req("interactive"))
        itype = i.req("type")
        if itype == "button":
            buttons: list[ReplyButton] = []
            for b in i.req("buttons"):
                bp = Params("reply button", b)
                buttons.append(ReplyButton(bp.req("id"), bp.req("title")))
                bp.done()
            message = session.buttons(
                to, i.req("body"), buttons, i.opt("header"), i.opt("footer"), **common
            )
        elif itype == "list":
            sections: list[ListSection] = []
            for s in i.req("sections"):
                sp = Params("list section", s)
                rows: list[ListRow] = []
                for r in sp.req("rows"):
                    rp = Params("list row", r)
                    rows.append(ListRow(rp.req("id"), rp.req("title"), rp.opt("description")))
                    rp.done()
                sections.append(ListSection(rows=rows, title=sp.opt("title")))
                sp.done()
            message = session.list(
                to,
                i.req("body"),
                i.req("button"),
                sections,
                i.opt("header"),
                i.opt("footer"),
                **common,
            )
        else:
            raise AssertionError(f"unknown interactive type {itype!r}")
        i.done()
    elif kind == "location":
        loc = Params("location", p.req("location"))
        message = session.location(
            to,
            loc.req("latitude"),
            loc.req("longitude"),
            loc.opt("name"),
            loc.opt("address"),
            **common,
        )
        loc.done()
    elif kind == "contacts":
        message = session.contacts(to, p.req("contacts"), **common)
    elif kind == "reaction":
        r = Params("reaction", p.req("reaction"))
        message = session.reaction(to, r.req("message_id"), r.req("emoji"), **common)
        r.done()
    else:
        raise AssertionError(f"unknown session message type {kind!r}")
    p.done()
    return message


def call(client: Unicom360, operation: str, params: Mapping[str, Any]) -> Any:
    """Call ``operation`` with ``params`` (API field names) through the public API."""
    if operation == "whatsapp.send_session":
        return client.whatsapp.send_session(session_message(params))
    p = Params(operation, params)
    result: Any
    if operation == "sms.send":
        result = client.sms.send(
            from_=p.req("from"),
            to=p.req("to"),
            message=p.req("message"),
            user_reference_id=p.opt("user_reference_id"),
            callback_url=p.opt("callback_url"),
            source=p.opt("source"),
        )
    elif operation == "email.send":
        result = client.email.send(
            from_=p.req("from"),
            to=p.req("to"),
            subject=p.req("subject"),
            email_body=p.req("email_body"),
            reply_to=p.opt("reply_to"),
            user_reference_id=p.opt("user_reference_id"),
            callback_url=p.opt("callback_url"),
            source=p.opt("source"),
        )
    elif operation == "whatsapp.send_template":
        result = client.whatsapp.send_template(
            template=p.req("template"),
            recipients=[recipient(r) for r in p.req("recipients")],
            from_=p.opt("from"),
            language=p.opt("language"),
            callback_url=p.opt("callback_url"),
        )
    elif operation == "whatsapp.status":
        result = client.whatsapp.status(p.req("message_ids"))
    elif operation == "whatsapp.templates":
        result = client.whatsapp.templates()
    elif operation == "balance.get":
        result = client.balance.get(p.opt("bundle_type"))
    elif operation == "balance.all":
        result = client.balance.all()
    elif operation == "health":
        result = client.health()
    else:
        raise AssertionError(f"unknown operation {operation!r}")
    p.done()
    return result


def sample_params(operation: str) -> dict[str, Any]:
    """Valid params for ``operation``: those of its first ``requests.json`` vector."""
    for vector in load("requests.json")["vectors"]:
        if vector["operation"] == operation:
            params: dict[str, Any] = vector["params"]
            return params
    raise AssertionError(f"requests.json has no vector for {operation!r}")


# ---------------------------------------------------------------------------------------------
# Canonical form and comparison (conformance/README.md)
# ---------------------------------------------------------------------------------------------

# Model fields whose API name differs from the Python attribute.
_RENAMED = {"from_": "from", "accepted_count": "accepted", "rejected_count": "rejected"}


def canonical(value: Any) -> Any:
    """The canonical JSON of a model: its typed fields under API names, plus its ``extra``.

    Built from the typed model, never from ``raw``.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {}
        for f in dataclasses.fields(value):
            if f.name in ("raw", "extra"):
                continue
            out[_RENAMED.get(f.name, f.name)] = canonical(getattr(value, f.name))
        extra = getattr(value, "extra", {})
        for key, item in extra.items():
            assert key not in out, f"extra field {key!r} shadows a modelled field"
            out[key] = canonical(item)
        return out
    if isinstance(value, Mapping):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return value


def drop_nulls(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_nulls(v) for v in value]
    return value


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    return None


def _equal(a: Any, b: Any, path: str) -> str | None:
    na, nb = _number(a), _number(b)
    if na is not None or nb is not None:
        if na is None or nb is None or na != nb:
            return f"{path}: {a!r} != {b!r}"
        return None
    if isinstance(a, list) or isinstance(b, list):
        if not (isinstance(a, list) and isinstance(b, list)) or len(a) != len(b):
            return f"{path}: {a!r} != {b!r}"
        for i, (x, y) in enumerate(zip(a, b)):
            problem = _equal(x, y, f"{path}[{i}]")
            if problem:
                return problem
        return None
    if isinstance(a, dict) or isinstance(b, dict):
        if not (isinstance(a, dict) and isinstance(b, dict)):
            return f"{path}: {a!r} != {b!r}"
        if set(a) != set(b):
            return f"{path}: keys {sorted(a)} != {sorted(b)}"
        for key in a:
            problem = _equal(a[key], b[key], f"{path}.{key}")
            if problem:
                return problem
        return None
    if type(a) is not type(b) or a != b:
        return f"{path}: {a!r} != {b!r}"
    return None


def assert_canonical_equal(expected: Any, actual: Any) -> None:
    """Nulls dropped, key order ignored, numbers by value, strings and booleans exact."""
    problem = _equal(drop_nulls(expected), drop_nulls(actual), "$")
    assert problem is None, problem


def json_pointer_exists(document: Any, pointer: str) -> bool:
    """Whether the RFC 6901 ``pointer`` resolves in ``document``."""
    current = document
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return False
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return False
            current = current[int(token)]
        else:
            return False
    return True


def error_class(error: BaseException) -> str:
    """The canonical class name: the most specific class this SDK raised."""
    name = type(error).__name__
    assert hasattr(unicom360, name), f"{name} is not a public unicom360 class"
    return name
