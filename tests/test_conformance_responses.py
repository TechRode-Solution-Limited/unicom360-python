"""responses.json: canned responses and the result or error each must produce."""

from __future__ import annotations

from typing import Any

import pytest

from tests.harness import (
    OPERATIONS,
    FakeTransport,
    assert_canonical_equal,
    call,
    canonical,
    check_keys,
    error_class,
    http_response,
    make_client,
    sample_params,
    vectors,
)
from unicom360 import Unicom360Error
from unicom360.models import EmailSendResult, SmsSendResult, TemplateSendResult

FILE = "responses.json"


@pytest.mark.parametrize("vector", vectors(FILE))
def test_response(vector: dict[str, Any]) -> None:
    check_keys(
        vector,
        ("id", "operation", "http", "expect"),
        ("description", "off_spec", "now_unix"),
    )
    operation = vector["operation"]
    assert operation in OPERATIONS
    expect = vector["expect"]

    transport = FakeTransport([http_response(vector["http"])])
    client = make_client(transport, max_retries=0, now=vector.get("now_unix", 1767225630))

    if "result" in expect:
        check_keys(expect, ("result",), ("helpers",))
        result = call(client, operation, sample_params(operation))
        assert_canonical_equal(expect["result"], canonical(result))
        if "helpers" in expect:
            check_helpers(result, expect["helpers"])
        return

    check_keys(expect, ("error",), ())
    want = expect["error"]
    check_keys(
        want,
        ("type", "class", "code", "message", "api_reference", "http_status", "data_present"),
        ("retry_after",),
    )
    with pytest.raises(Unicom360Error) as caught:
        call(client, operation, sample_params(operation))
    error: Any = caught.value
    assert error.type == want["type"]
    assert error_class(error) == want["class"]
    assert error.code == want["code"]
    assert error.api_reference == want["api_reference"]
    assert error.http_status == want["http_status"]
    if want["message"] is None:
        assert isinstance(error.message, str)
        assert error.message != ""
    else:
        assert error.message == want["message"]
    assert (error.data is not None) == want["data_present"]
    if "retry_after" in want:
        assert error.retry_after == want["retry_after"]
    assert error.attempts == 1
    assert error.raw_body == vector["http"]["body_text"]


def check_helpers(result: Any, helpers: dict[str, Any]) -> None:
    check_keys(helpers, (), ("accepted", "invalid", "rejected", "by_number", "by_address"))
    assert isinstance(result, (SmsSendResult, EmailSendResult, TemplateSendResult))
    results = result.results

    def positions(items: list[Any]) -> list[int]:
        return [next(i for i, r in enumerate(results) if r is item) for item in items]

    def position(item: Any) -> int | None:
        if item is None:
            return None
        return next(i for i, r in enumerate(results) if r is item)

    if "accepted" in helpers:
        assert positions(result.accepted()) == helpers["accepted"]
    if "invalid" in helpers:
        assert isinstance(result, (SmsSendResult, EmailSendResult))
        assert positions(result.invalid()) == helpers["invalid"]
    if "rejected" in helpers:
        assert isinstance(result, TemplateSendResult)
        assert positions(result.rejected()) == helpers["rejected"]
    for number, expected in helpers.get("by_number", {}).items():
        assert isinstance(result, (SmsSendResult, TemplateSendResult))
        assert position(result.by_number(number)) == expected, number
    for address, expected in helpers.get("by_address", {}).items():
        assert isinstance(result, EmailSendResult)
        assert position(result.by_address(address)) == expected, address
