"""The contract test: every operation against a Prism mock of ``openapi.yaml``.

Not part of the default run. Start Prism, then run ``pytest -m contract``::

    docker run --rm -p 4011:4010 -v "$OPENAPI_DIR":/spec:ro stoplight/prism:5 \\
        mock -h 0.0.0.0 --multiprocess=false --errors /spec/openapi.yaml
    UNICOM360_CONTRACT_BASE_URL=http://127.0.0.1:4011 pytest -m contract

Prism validates each request against the spec; with ``--errors`` it answers an invalid request
with an error status, and it reports every problem in an ``sl-violations`` header. Either one
fails the test. Every call in ``requests.json`` goes
through the default urllib transport, and the example Prism answers with must parse into the
operation's result.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests.harness import OPERATIONS, call, load, vectors
from unicom360 import Request, Response, Unicom360, UrllibTransport, models, session

pytestmark = pytest.mark.contract

PRISM_URL = os.environ.get("UNICOM360_CONTRACT_BASE_URL", "http://127.0.0.1:4011")

RESULT_TYPES = {
    "sms.send": models.SmsSendResult,
    "email.send": models.EmailSendResult,
    "whatsapp.send_template": models.TemplateSendResult,
    "whatsapp.send_session": models.SessionSendResult,
    "whatsapp.status": models.StatusResult,
    "whatsapp.templates": models.TemplateList,
    "balance.get": models.Balance,
    "balance.all": models.Balances,
    "health": models.Health,
}


class Recording(UrllibTransport):
    def __init__(self) -> None:
        super().__init__()
        self.exchanges: list[tuple[Request, Response]] = []

    def send(self, request: Request) -> Response:
        response = super().send(request)
        self.exchanges.append((request, response))
        return response


def client(transport: Recording, **options: Any) -> Unicom360:
    return Unicom360(
        "contract-test-key", base_url=PRISM_URL, transport=transport, max_retries=0, **options
    )


def assert_conforms(transport: Recording) -> None:
    assert transport.exchanges, "no request was sent"
    for request, response in transport.exchanges:
        violations = response.headers.get("sl-violations")
        assert violations is None, f"{request.method} {request.url}: {violations}"
        assert response.status == 200, f"{request.method} {request.url}: HTTP {response.status}"


def test_prism_is_reachable() -> None:
    transport = Recording()
    assert client(transport).health().status == "ok"
    assert_conforms(transport)


@pytest.mark.parametrize("vector", vectors("requests.json"))
def test_request_conforms_to_the_spec(vector: dict[str, Any]) -> None:
    transport = Recording()
    result = call(client(transport), vector["operation"], vector["params"])
    assert_conforms(transport)
    assert isinstance(result, RESULT_TYPES[vector["operation"]])


def test_every_operation_is_covered() -> None:
    covered = {v["operation"] for v in load("requests.json")["vectors"]}
    assert covered == set(OPERATIONS)


def test_generated_references_conform() -> None:
    transport = Recording()
    c = client(transport, auto_reference_ids=True)
    c.sms.send(from_="Unicom360", to="260971234567", message="Your order is ready.")
    c.email.send(
        from_="noreply@example.com", to="jane@example.com", subject="Hi", email_body="<p>Hi</p>"
    )
    c.whatsapp.send_session(session.text("260971234567", "Your order is ready."))
    assert_conforms(transport)
