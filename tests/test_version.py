from __future__ import annotations

from importlib import metadata

import unicom360


def test_version_matches_the_package_metadata() -> None:
    assert unicom360.__version__ == "0.1.0"
    assert metadata.version("unicom360") == unicom360.__version__


def test_package_has_no_runtime_dependencies() -> None:
    assert not metadata.requires("unicom360")


def test_public_names_resolve() -> None:
    for name in unicom360.__all__:
        assert hasattr(unicom360, name), name
