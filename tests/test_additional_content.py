"""Proposed content lives in each data file's `additional` block. It must stay out of the active
tables, so balance runs and tests are unchanged, yet be well formed so it can be promoted."""

from __future__ import annotations

import pytest

from beacon import config
from beacon.config import TABLES

ADDITIONAL_TABLES = ("units", "buildings", "improvements", "techs", "alien_techs")


def _additional(cfg: config.Config, table: str) -> dict:
    spec = TABLES[table]
    return cfg.raw[spec.file].get("additional", {}).get(spec.key, {})


@pytest.mark.parametrize("table", ADDITIONAL_TABLES)
def test_additional_entries_stay_out_of_active_tables(cfg, table):
    extra = _additional(cfg, table)
    assert extra, f"{table} has no additional entries"
    assert not set(extra) & set(cfg.tables[table])


def test_additional_content_validates_as_if_promoted(cfg):
    merged = {name: {**cfg.tables[name], **_additional(cfg, name)} for name in TABLES}
    config._validate_tables(merged)  # raises ConfigError on any malformed or dangling entry
