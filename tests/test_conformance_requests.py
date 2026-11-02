"""requests.json: each call and the exact HTTP request it must make."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import pytest

from tests.harness import (
    API_KEY,
    OPERATIONS,
    FakeTransport,
    call,
    check_keys,
    http_response,
    json_pointer_exists,
    load,
    make_client,
    vectors,
)

FILE = "requests.json"
CANNED = load(FILE)["canned_responses"]


def test_canned_responses_cover_every_operation() -> None:
    assert set(CANNED) == set(OPERATIONS)


@pytest.mark.parametrize("vector", vectors(FILE))
def test_request(vector: dict[str, Any]) -> None:
    check_keys(vector, ("id", "operation", "params", "expect"), ("description",))
    expect = vector["expect"]
    check_keys(
        expect,
        (
            "method",
            "path",
            "headers",
            "absent_headers",
            "user_agent_prefix",
            "json",
            "absent_keys",
        ),
        (),
    )
    operation = vector["operation"]
    assert operation in OPERATIONS

    transport = FakeTransport([http_response(CANNED[operation])])
    client = make_client(transport, max_retries=0)
    call(client, operation, vector["params"])

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == expect["method"]

    url = urllib.parse.urlsplit(request.url)
    assert url.query == ""
    assert "?" not in request.url
    assert url.path == expect["path"]

    headers = {name.lower(): value for name, value in request.headers.items()}
    for name, value in expect["headers"].items():
        assert headers.get(name) == value.replace("<KEY>", API_KEY), name
    for name in expect["absent_headers"]:
        assert name not in headers, f"{name} must not be sent"
    assert headers["user-agent"].startswith(expect["user_agent_prefix"])

    if expect["json"] is None:
        assert request.body is None or request.body == b""
        return
    assert request.body is not None
    body = json.loads(request.body.decode("utf-8"))
    assert_deep_equal(expect["json"], body, "$")
    for pointer in expect["absent_keys"]:
        assert not json_pointer_exists(body, pointer), f"{pointer} must be absent"


def assert_deep_equal(expected: Any, actual: Any, path: str) -> None:
    """Exact JSON equality: no extra keys, no nulls for unset fields, numbers by value."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        assert type(expected) is type(actual), path
        assert expected == actual, path
    elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        assert expected == actual, path
    elif isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(expected) == set(actual), f"{path}: {sorted(expected)} != {sorted(actual)}"
        for key in expected:
            assert_deep_equal(expected[key], actual[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(expected) == len(actual), path
        for i, (e, a) in enumerate(zip(expected, actual)):
            assert_deep_equal(e, a, f"{path}[{i}]")
    else:
        assert type(expected) is type(actual), f"{path}: {actual!r}"
        assert expected == actual, f"{path}: {actual!r}"
