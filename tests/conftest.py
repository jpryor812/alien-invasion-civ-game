"""Shared fixtures. `cfg` is the real data, loaded once per test session."""

from __future__ import annotations

import pytest

from beacon import config


@pytest.fixture(scope="session")
def cfg() -> config.Config:
    return config.load()
