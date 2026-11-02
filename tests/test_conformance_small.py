"""error-codes.json, callbacks.json and gsm7.json."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from tests.harness import assert_canonical_equal, canonical, check_keys, load, vectors
from unicom360 import Unicom360Error, gsm, normalize_code, webhooks

GSM = load("gsm7.json")


@pytest.mark.parametrize("vector", vectors("error-codes.json"))
def test_error_code(vector: dict[str, Any]) -> None:
    check_keys(vector, ("id", "message", "code", "source"), ("note",))
    assert normalize_code(vector["message"]) == vector["code"]


@pytest.mark.parametrize("vector", vectors("callbacks.json"))
def test_callback(vector: dict[str, Any]) -> None:
    check_keys(vector, ("id", "kind", "body_text", "expect"), ("description", "off_spec"))
    parse: dict[str, Callable[[Any], webhooks.SmsDeliveryReport | webhooks.EmailDeliveryReport]] = {
        "sms": webhooks.parse_sms_callback,
        "email": webhooks.parse_email_callback,
    }
    assert vector["kind"] in parse, f"unknown callback kind {vector['kind']!r}"
    parser = parse[vector["kind"]]
    expect = vector["expect"]
    if "error" in expect:
        check_keys(expect, ("error",), ())
        assert expect["error"] is True
        with pytest.raises(Unicom360Error):
            parser(vector["body_text"])
        # Bytes, as a web framework hands them over, behave the same.
        with pytest.raises(Unicom360Error):
            parser(vector["body_text"].encode("utf-8"))
        return
    check_keys(expect, ("result",), ())
    report = parser(vector["body_text"].encode("utf-8"))
    assert isinstance(report.message_id, str)
    assert_canonical_equal(expect["result"], canonical(report))
    assert_canonical_equal(expect["result"], canonical(parser(vector["body_text"])))


def test_gsm_constants_match_the_gateway() -> None:
    assert GSM["charset"] == gsm.CHARSET
    assert GSM["max_length"] == gsm.MAX_LENGTH
    assert GSM["unit_length"] == gsm.UNIT_LENGTH


@pytest.mark.parametrize("vector", vectors("gsm7.json"))
def test_gsm7(vector: dict[str, Any]) -> None:
    check_keys(
        vector,
        ("id", "text", "is_gsm7", "length", "units", "non_gsm", "validate"),
        ("description",),
    )
    text = vector["text"]
    assert gsm.is_gsm7(text) is vector["is_gsm7"]
    assert gsm.length(text) == vector["length"]
    assert gsm.units(text) == vector["units"]
    found = [{"char": c.char, "index": c.index} for c in gsm.non_gsm_characters(text)]
    assert found == vector["non_gsm"]
    issues = gsm.validate_sms(text)
    assert [issue.value for issue in issues] == vector["validate"]
    # Issues serialise to (and compare equal to) the contract's strings.
    assert [str(issue) for issue in issues] == vector["validate"]
    assert issues == vector["validate"]
