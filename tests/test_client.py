"""Client behaviour the fixtures do not pin down: configuration, redaction, logging, options."""

from __future__ import annotations

import json
import logging
import re
import socket
from decimal import Decimal
from typing import Any

import pytest

from tests.harness import API_KEY, FakeTime, FakeTransport, load, make_client
from unicom360 import (
    DEFAULT_BASE_URL,
    APIConnectionError,
    APIError,
    APIServerError,
    APIStatusError,
    APITimeoutError,
    AppInfo,
    ConfigurationError,
    DuplicateReferenceError,
    NoValidRecipientsError,
    Response,
    TemplateRecipient,
    TransportError,
    Unicom360,
    session,
)

CANNED = load("requests.json")["canned_responses"]
REFERENCE = re.compile(r"u360-[0-9a-f]{32}")


def ok(operation: str) -> Response:
    spec = CANNED[operation]
    return Response(status=spec["status"], headers=spec["headers"], body=spec["body_text"])


def json_response(body: Any, status: int = 200) -> Response:
    return Response(
        status=status, headers={"content-type": "application/json"}, body=json.dumps(body)
    )


def sent_json(transport: FakeTransport, index: int = 0) -> Any:
    body = transport.requests[index].body
    assert body is not None
    return json.loads(body)


# ---------------------------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------------------------


class TestApiKey:
    def test_missing_key_fails_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNICOM360_API_KEY", raising=False)
        with pytest.raises(ConfigurationError) as caught:
            Unicom360()
        assert caught.value.type == "configuration_error"

    def test_key_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNICOM360_API_KEY", "env-key")
        transport = FakeTransport([ok("balance.all")])
        Unicom360(transport=transport).balance.all()
        assert transport.requests[0].headers["X-API-Key"] == "env-key"

    def test_explicit_key_wins_over_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNICOM360_API_KEY", "env-key")
        transport = FakeTransport([ok("balance.all")])
        Unicom360("arg-key", transport=transport).balance.all()
        assert transport.requests[0].headers["X-API-Key"] == "arg-key"

    @pytest.mark.parametrize("key", ["", "   ", "\t\n"])
    def test_explicit_blank_key_never_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, key: str
    ) -> None:
        monkeypatch.setenv("UNICOM360_API_KEY", "env-key")
        with pytest.raises(ConfigurationError):
            Unicom360(key)

    def test_blank_environment_key_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNICOM360_API_KEY", " ")
        with pytest.raises(ConfigurationError):
            Unicom360()


class TestBaseUrl:
    @pytest.mark.parametrize(
        ("given", "kept"),
        [
            ("https://api.unicom360.com", "https://api.unicom360.com"),
            ("https://api.unicom360.com/", "https://api.unicom360.com"),
            ("https://proxy.example.com/unicom360//", "https://proxy.example.com/unicom360"),
            ("https://proxy.example.com:8443/u", "https://proxy.example.com:8443/u"),
            ("http://localhost:4010", "http://localhost:4010"),
            ("http://127.0.0.1:4010/", "http://127.0.0.1:4010"),
            ("http://127.9.8.7", "http://127.9.8.7"),
            ("http://[::1]:4010", "http://[::1]:4010"),
            ("HTTPS://API.UNICOM360.COM", "HTTPS://API.UNICOM360.COM"),
        ],
    )
    def test_accepted(self, given: str, kept: str) -> None:
        assert Unicom360(API_KEY, base_url=given).base_url == kept

    @pytest.mark.parametrize(
        "given",
        [
            "",
            "api.unicom360.com",
            "http://api.unicom360.com",
            "http://128.0.0.1",
            "http://localhost.example.com",
            "http://[::2]",
            "ftp://api.unicom360.com",
            "https://",
            "https:///path",
            "https://api.unicom360.com?x=1",
            "https://api.unicom360.com/#top",
            "https://api.unicom360.com:notaport",
            "https://api.unicom360 .com",
        ],
    )
    def test_refused(self, given: str) -> None:
        with pytest.raises(ConfigurationError):
            Unicom360(API_KEY, base_url=given)

    def test_default_and_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNICOM360_BASE_URL", raising=False)
        assert Unicom360(API_KEY).base_url == DEFAULT_BASE_URL
        monkeypatch.setenv("UNICOM360_BASE_URL", "http://localhost:4010/")
        assert Unicom360(API_KEY).base_url == "http://localhost:4010"
        assert Unicom360(API_KEY, base_url="https://x.example").base_url == "https://x.example"

    def test_path_prefix_is_kept_in_requests(self) -> None:
        transport = FakeTransport([ok("health")])
        client = Unicom360(API_KEY, base_url="https://proxy.example.com/u360/", transport=transport)
        client.health()
        assert transport.requests[0].url == "https://proxy.example.com/u360/health"


class TestOptions:
    @pytest.mark.parametrize(
        "options",
        [
            {"timeout": 0},
            {"timeout": -1},
            {"connect_timeout": 0},
            {"max_retries": -1},
            {"max_retries": 1.5},
            {"max_retries": True},
            {"max_retry_wait": -0.1},
            {"app_info": {"version": "1.0"}},
        ],
    )
    def test_invalid_options(self, options: dict[str, Any]) -> None:
        with pytest.raises(ConfigurationError):
            Unicom360(API_KEY, **options)

    def test_defaults(self) -> None:
        client = Unicom360(API_KEY)
        assert client.timeout == 60.0
        assert client.connect_timeout == 10.0
        assert client.max_retries == 2
        assert client.max_retry_wait == 60.0
        assert client.auto_reference_ids is False

    def test_user_agent(self) -> None:
        agent = Unicom360(API_KEY).user_agent
        assert re.fullmatch(r"unicom360-python/0\.1\.0 \(\w+ [\w.+]+; \w+; [\w-]+\)", agent)
        with_app = Unicom360(
            API_KEY, app_info=AppInfo("shopsync", "2.3.0", "https://shopsync.example")
        ).user_agent
        assert with_app.endswith(") shopsync/2.3.0 (+https://shopsync.example)")
        from_dict = Unicom360(API_KEY, app_info={"name": "shopsync"}).user_agent
        assert from_dict.endswith(") shopsync")

    def test_with_options_copies(self) -> None:
        transport = FakeTransport([ok("health")])
        client = Unicom360(API_KEY, max_retries=4, transport=transport)
        copy = client.with_options(timeout=5, base_url="http://localhost:4010")
        assert copy is not client
        assert (copy.timeout, copy.max_retries, copy.base_url) == (5.0, 4, "http://localhost:4010")
        assert (client.timeout, client.base_url) == (60.0, DEFAULT_BASE_URL)
        copy.health()
        assert transport.requests[0].url == "http://localhost:4010/health"
        with pytest.raises(ConfigurationError):
            client.with_options(api_key="")

    def test_per_request_options(self) -> None:
        transport = FakeTransport([Response(503), Response(503), ok("whatsapp.templates")])
        client = make_client(transport, max_retries=0)
        client.whatsapp.templates(timeout=2.5, max_retries=2)
        assert len(transport.requests) == 3
        assert {r.timeout for r in transport.requests} == {2.5}
        with pytest.raises(ConfigurationError):
            client.whatsapp.templates(max_retries=-1)
        with pytest.raises(ConfigurationError):
            client.whatsapp.templates(timeout=0)


# ---------------------------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------------------------


def test_api_key_never_printed() -> None:
    secret = "sk-very-secret-key"
    transport = FakeTransport(
        [json_response({"message": "AUTHENTICATION_FAILED", "success": False}, 401)]
    )
    client = Unicom360(secret, transport=transport)
    assert secret not in repr(client)
    assert "[REDACTED]" in repr(client)
    assert secret not in repr(client.sms)
    with pytest.raises(APIStatusError) as caught:
        client.balance.get()
    error = caught.value
    for text in (str(error), repr(error), error.message, repr(vars(error))):
        assert secret not in text
    assert secret not in repr(transport.requests[0])


# ---------------------------------------------------------------------------------------------
# Interpretation rules without a fixture
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", [1, "true", None, [True]])
def test_non_boolean_success_flag_is_a_status_error(flag: Any) -> None:
    body = {"success": flag, "message": "successful", "data": []}
    client = make_client(FakeTransport([json_response(body)]))
    with pytest.raises(APIStatusError) as caught:
        client.sms.send(from_="Unicom360", to="260971234567", message="Hi")
    assert type(caught.value) is APIStatusError
    assert caught.value.code == "UNKNOWN"


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (599, APIServerError),
        (500, APIServerError),
        (301, APIStatusError),
        (302, APIStatusError),
        (403, APIStatusError),
        (413, APIStatusError),
        (499, APIStatusError),
    ],
)
def test_status_classes(status: int, cls: type[APIStatusError]) -> None:
    client = make_client(FakeTransport([Response(status=status, body="")]))
    with pytest.raises(APIStatusError) as caught:
        client.balance.get()
    assert type(caught.value) is cls
    assert caught.value.http_status == status
    assert caught.value.message


def test_refusal_with_unusable_message() -> None:
    client = make_client(FakeTransport([json_response({"success": False, "message": [1, 2]})]))
    with pytest.raises(APIStatusError) as caught:
        client.balance.all()
    # A balance refusal reads `status`, so this body is not a usable balance envelope.
    assert type(caught.value) is APIStatusError

    client = make_client(FakeTransport([json_response({"success": False, "message": {"x": 1}})]))
    with pytest.raises(APIError) as caught_api:
        client.whatsapp.templates()
    assert caught_api.value.code == "UNKNOWN"
    assert caught_api.value.message


def test_duplicate_reference_original_message_id() -> None:
    body = {
        "message": "DUPLICATE_MSG_REF",
        "success": False,
        "api_reference": "1",
        "data": {"message_id": "7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f"},
    }
    client = make_client(FakeTransport([json_response(body)]))
    with pytest.raises(DuplicateReferenceError) as caught:
        client.whatsapp.send_session(session.text("260971234567", "Hi", user_reference_id="s-1"))
    assert caught.value.original_message_id == "7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f"


def test_no_valid_recipients_results() -> None:
    body = {
        "message": "NO_VALID_RECIPIENTS",
        "success": False,
        "api_reference": "1",
        "data": {
            "accepted": 0,
            "rejected": 1,
            "results": [{"to": 12, "status": "REJECTED", "reason": "INVALID_NUMBER"}],
        },
    }
    client = make_client(FakeTransport([json_response(body)]))
    with pytest.raises(NoValidRecipientsError) as caught:
        client.whatsapp.send_template(template="t", recipients=[TemplateRecipient(to="12")])
    [result] = caught.value.results
    assert (result.to, result.reason) == ("12", "INVALID_NUMBER")


def test_balances_are_exact_decimals() -> None:
    body = (
        '{"status":true,"message":"ok","balance":12345678901234567890.125,'
        '"bundle_type":"WHATSAPP","client_id":"UC-1","client_name":"Acme"}'
    )
    client = make_client(FakeTransport([Response(200, {}, body)]))
    balance = client.balance.get("WHATSAPP")
    assert balance.balance == Decimal("12345678901234567890.125")
    assert isinstance(balance.raw["balance"], float)

    body = (
        '{"status":true,"message":"ok","balances":{"SMS":1250,"WHATSAPP":37.50},"client_id":"UC-1"}'
    )
    balances = make_client(FakeTransport([Response(200, {}, body)])).balance.all()
    assert balances.balances == {"SMS": Decimal(1250), "WHATSAPP": Decimal("37.50")}


def test_float_ids_become_strings() -> None:
    body = {
        "success": True,
        "api_reference": "1",
        "message": "successful",
        "data": [{"message_id": 48213.0, "status": "ACKNOWLEDGED", "email_address": "a@b.c"}],
    }
    client = make_client(FakeTransport([json_response(body)]))
    result = client.email.send(from_="a@b.c", to="a@b.c", subject="s", email_body="b")
    assert result.results[0].message_id == "48213"


def test_helpers_by_id_and_by_name() -> None:
    client = make_client(FakeTransport([ok("whatsapp.status"), ok("whatsapp.templates")]))
    status = client.whatsapp.status("7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f")
    found = status.by_id("7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f")
    assert found is not None
    assert found.status == "READ"
    assert found.from_ == "260960123456"
    assert status.by_id("missing") is None
    templates = client.whatsapp.templates()
    assert templates.by_name("order_ready") is not None
    assert templates.by_name("order_ready", "fr") is None


# ---------------------------------------------------------------------------------------------
# Retry safety and auto_reference_ids
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("reference", ["", "   ", "\t"])
def test_blank_reference_is_not_retry_safe(reference: str) -> None:
    transport = FakeTransport([Response(500), ok("sms.send")])
    client = make_client(transport, max_retries=2)
    with pytest.raises(APIServerError):
        client.sms.send(from_="U", to="260971234567", message="Hi", user_reference_id=reference)
    assert len(transport.requests) == 1


def test_unclassified_transport_failure_counts_as_sent() -> None:
    class Broken:
        def send(self, request: Any) -> Response:
            raise ValueError("boom")

    client = Unicom360(API_KEY, transport=Broken(), sleeper=lambda s: None)
    with pytest.raises(APIConnectionError) as caught:
        client.sms.send(from_="U", to="260971234567", message="Hi")
    assert caught.value.sent is True
    assert caught.value.attempts == 1
    assert isinstance(caught.value.cause, ValueError)


def test_timeout_exception_from_a_custom_transport() -> None:
    class Slow:
        def send(self, request: Any) -> Response:
            raise socket.timeout("slow")

    client = Unicom360(API_KEY, transport=Slow(), sleeper=lambda s: None, max_retries=1)
    with pytest.raises(APITimeoutError) as caught:
        client.balance.get()
    assert caught.value.attempts == 2


def test_auto_reference_ids_fill_every_send() -> None:
    transport = FakeTransport(
        [
            ok("sms.send"),
            ok("email.send"),
            ok("whatsapp.send_session"),
            ok("whatsapp.send_template"),
        ]
    )
    client = make_client(transport, auto_reference_ids=True)
    client.sms.send(from_="U", to="260971234567", message="Hi")
    client.email.send(from_="a@b.c", to="a@b.c", subject="s", email_body="b")
    client.whatsapp.send_session(session.text("260971234567", "Hi"))
    client.whatsapp.send_template(
        template="t",
        recipients=[
            TemplateRecipient(to="260971234567"),
            TemplateRecipient(to="260961234567", user_reference_id="mine"),
            {"to": "260951234567", "user_reference_id": None},
        ],
    )
    for i in range(3):
        assert REFERENCE.fullmatch(sent_json(transport, i)["user_reference_id"])
    recipients = sent_json(transport, 3)["recipients"]
    assert REFERENCE.fullmatch(recipients[0]["user_reference_id"])
    assert recipients[1]["user_reference_id"] == "mine"
    assert REFERENCE.fullmatch(recipients[2]["user_reference_id"])
    assert recipients[0]["user_reference_id"] != recipients[2]["user_reference_id"]


def test_auto_reference_is_reused_and_makes_sms_retry_safe() -> None:
    transport = FakeTransport([TransportError("t", sent=True, timeout=True), ok("sms.send")])
    client = make_client(transport, max_retries=2, auto_reference_ids=True)
    client.sms.send(from_="U", to="260971234567", message="Hi")
    assert len(transport.requests) == 2
    assert transport.requests[0].body == transport.requests[1].body


def test_auto_reference_does_not_make_email_retry_safe() -> None:
    transport = FakeTransport([Response(502), ok("email.send")])
    client = make_client(transport, max_retries=2, auto_reference_ids=True)
    with pytest.raises(APIServerError):
        client.email.send(from_="a@b.c", to="a@b.c", subject="s", email_body="b")
    assert len(transport.requests) == 1
    assert REFERENCE.fullmatch(sent_json(transport)["user_reference_id"])


def test_auto_reference_ids_off_by_default() -> None:
    transport = FakeTransport([ok("sms.send")])
    make_client(transport).sms.send(from_="U", to="260971234567", message="Hi")
    assert "user_reference_id" not in sent_json(transport)


# ---------------------------------------------------------------------------------------------
# Request shapes beyond the fixtures
# ---------------------------------------------------------------------------------------------


def test_dict_inputs_drop_nulls() -> None:
    transport = FakeTransport([ok("whatsapp.send_session"), ok("whatsapp.send_template")])
    client = make_client(transport)
    client.whatsapp.send_session(
        {"to": "260971234567", "type": "text", "text": "Hi", "reply_to": None}
    )
    assert sent_json(transport, 0) == {"to": "260971234567", "type": "text", "text": "Hi"}
    client.whatsapp.send_template(
        template="t", recipients=[{"to": "260971234567", "body": ["Ada"], "otp": None}]
    )
    assert sent_json(transport, 1) == {
        "template": "t",
        "recipients": [{"to": "260971234567", "body": ["Ada"]}],
    }


def test_status_accepts_one_id_as_a_string() -> None:
    transport = FakeTransport([ok("whatsapp.status")])
    make_client(transport).whatsapp.status("7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f")
    assert sent_json(transport) == {"message_ids": ["7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f"]}


def test_non_ascii_text_round_trips() -> None:
    transport = FakeTransport([ok("whatsapp.send_session")])
    text = "Café \U0001f44d €\r\n"
    make_client(transport).whatsapp.send_session(session.text("260971234567", text))
    assert sent_json(transport)["text"] == text


# ---------------------------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------------------------


def test_logging(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="unicom360")
    rate_limited = json_response(
        {"message": "RATE_LIMIT_EXCEEDED", "success": False, "api_reference": "999"}, 429
    )
    transport = FakeTransport([rate_limited, ok("sms.send")])
    fake_time = FakeTime(1767225630)
    client = make_client(
        transport, max_retries=1, fake_time=fake_time, auto_reference_ids=True, random=lambda: 0.25
    )
    client.sms.send(from_="Unicom360", to="260971234567", message="Your secret code 482193")

    records = [r for r in caplog.records if r.name == "unicom360"]
    debug = [r.getMessage() for r in records if r.levelno == logging.DEBUG]
    info = [r.getMessage() for r in records if r.levelno == logging.INFO]
    assert len(debug) == 2
    assert len(info) == 1
    assert "POST /api/v1/json/bulk/sms status=429 api_reference=999 attempt=1" in debug[0]
    assert "status=200 api_reference=1764184470578998353 attempt=2" in debug[1]
    assert "duration_ms=" in debug[0]
    assert REFERENCE.search(debug[0])
    assert "attempt=1 wait_s=30.250 cause=rate_limit_error" in info[0]
    everything = "\n".join(r.getMessage() for r in records)
    for secret in (API_KEY, "260971234567", "482193", 'Unicom360"'):
        assert secret not in everything


def test_custom_logger() -> None:
    logger = logging.getLogger("my.app.unicom360")
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Collect()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        make_client(FakeTransport([ok("health")]), logger=logger).health()
    finally:
        logger.removeHandler(handler)
    assert len(records) == 1
    assert "GET /health status=200" in records[0].getMessage()
