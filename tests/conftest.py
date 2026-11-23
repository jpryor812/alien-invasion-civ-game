"""Shared fixtures. `cfg` is the real data, loaded once per test session."""

from __future__ import annotations

import pytest

from beacon import config


@pytest.fixture(scope="session")
def cfg() -> config.Config:
    return config.load()


@pytest.fixture(scope="session")
def cfg_legacy() -> config.Config:
    """The real data with stacking and rations switched back on (off since SPEC_M22), so the
    tests of those dormant rules keep them working."""

    def on(raw):
        raw["tuning"]["combat"]["stacking"]["value"] = True
        raw["tuning"]["food"]["rations_on"] = True

    return config.load(overrides=on)
