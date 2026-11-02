"""retries.json: sequences of responses and transport failures, and the attempts and sleeps."""

from __future__ import annotations

import random
from typing import Any, Callable

import pytest

from tests.harness import (
    OPERATIONS,
    FakeTime,
    FakeTransport,
    call,
    check_keys,
    error_class,
    make_client,
    step,
    vectors,
)
from unicom360 import Unicom360Error

FILE = "retries.json"

# Each vector runs with the jitter at both ends of [0, 1) and with a seeded generator.
RANDOM_SOURCES: dict[str, Callable[[str], Callable[[], float]]] = {
    "zero": lambda _id: lambda: 0.0,
    "almost-one": lambda _id: lambda: 0.999999,
    "seeded": lambda vector_id: random.Random(vector_id).random,
}


@pytest.mark.parametrize("vector", vectors(FILE))
def test_retries(vector: dict[str, Any]) -> None:
    check_keys(
        vector,
        ("id", "description", "operation", "params", "now_unix", "config", "steps", "expect"),
        (),
    )
    assert vector["operation"] in OPERATIONS
    config = vector["config"]
    check_keys(config, ("max_retries", "max_retry_wait"), ())
    expect = vector["expect"]
    check_keys(expect, ("attempts", "sleeps", "outcome"), ())

    for source_name, source in RANDOM_SOURCES.items():
        steps = [step(s) for s in vector["steps"]]
        transport = FakeTransport(steps)
        fake_time = FakeTime(vector["now_unix"])
        client = make_client(
            transport,
            max_retries=config["max_retries"],
            max_retry_wait=config["max_retry_wait"],
            fake_time=fake_time,
            random=source(vector["id"]),
        )
        label = f"{vector['id']} ({source_name} jitter)"

        outcome = expect["outcome"]
        if outcome["kind"] == "result":
            check_keys(outcome, ("kind",), ())
            call(client, vector["operation"], vector["params"])
        else:
            check_keys(outcome, ("kind", "type", "class", "code", "http_status"), ())
            assert outcome["kind"] == "error"
            with pytest.raises(Unicom360Error) as caught:
                call(client, vector["operation"], vector["params"])
            error: Any = caught.value
            assert error.type == outcome["type"], label
            assert error_class(error) == outcome["class"], label
            assert getattr(error, "code", None) == outcome["code"], label
            assert error.http_status == outcome["http_status"], label
            assert error.attempts == expect["attempts"], label

        assert len(transport.requests) == expect["attempts"], label
        assert len(fake_time.sleeps) == len(expect["sleeps"]), label
        for slept, bounds in zip(fake_time.sleeps, expect["sleeps"]):
            check_keys(bounds, ("min", "max"), ())
            assert bounds["min"] - 1e-6 <= slept <= bounds["max"] + 1e-6, f"{label}: {slept}"
        # Every attempt sends the same request (a generated reference included).
        assert len({(r.method, r.url, r.body) for r in transport.requests}) == 1, label
