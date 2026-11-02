"""The vendored fixtures are unmodified, and every fixture file has a harness."""

from __future__ import annotations

import hashlib

import unicom360
from tests.harness import FIXTURES, load

# Every fixture file and the test module that runs all of its vectors.
HARNESSES = {
    "requests.json": "test_conformance_requests",
    "responses.json": "test_conformance_responses",
    "retries.json": "test_conformance_retries",
    "error-codes.json": "test_conformance_small",
    "callbacks.json": "test_conformance_small",
    "gsm7.json": "test_conformance_small",
    "webhooks/signatures.json": "test_conformance_webhooks",
    "webhooks/events.json": "test_conformance_webhooks",
}


def _version() -> dict[str, str]:
    lines = (FIXTURES / "VERSION").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def test_fixture_tree_hash_matches_version() -> None:
    """Recomputes the tree hash ``scripts/sync-conformance`` wrote (its ``--check``)."""
    files = sorted(
        (p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*") if p.is_file()),
        key=lambda name: name.encode("utf-8"),
    )
    listing = "".join(
        f"{hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()}  {name}\n"
        for name in files
        if name != "VERSION"
    )
    version = _version()
    assert version["source"] == "unicom360-openapi"
    assert hashlib.sha256(listing.encode("utf-8")).hexdigest() == version["sha256"]


def test_fixtures_target_this_contract_version() -> None:
    version = _version()
    assert version["version"] == unicom360.CONTRACT_VERSION
    assert version["tag"] == f"v{unicom360.CONTRACT_VERSION}"
    for name in HARNESSES:
        assert load(name)["version"] == unicom360.CONTRACT_VERSION


def test_every_fixture_file_has_a_harness() -> None:
    found = {
        p.relative_to(FIXTURES).as_posix()
        for p in FIXTURES.rglob("*.json")
        if p.relative_to(FIXTURES).parts[0] != "schema"
    }
    assert found == set(HARNESSES), "a fixture file without a harness would be skipped"


def test_vector_ids_are_unique_per_file() -> None:
    for name in HARNESSES:
        ids = [v["id"] for v in load(name)["vectors"]]
        assert ids, name
        assert len(ids) == len(set(ids)), name
