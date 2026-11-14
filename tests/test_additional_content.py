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


def test_alien_tech_orders_are_unique_when_promoted(cfg):
    merged = {**cfg.tables["alien_techs"], **_additional(cfg, "alien_techs")}
    orders = [entry["order"] for entry in merged.values()]
    assert len(set(orders)) == len(orders)


def test_recruit_pool_is_consistent(cfg):
    pool = cfg.raw["aliens"]["additional"]
    traits = set(pool["traits"])
    yields = set(config.YIELDS)
    for trait_id, trait in pool["traits"].items():
        assert set(trait["effects"].get("yield_pct", {})) <= yields, trait_id
    for arch_id, arch in pool["archetypes"].items():
        assert set(arch["traits"]) <= traits, arch_id
        assert set(arch["focus"]) <= yields, arch_id
        lo, hi = arch["lifespan"]
        assert 0 < lo <= hi, f"{arch_id}.lifespan"
    for rec_id, rec in pool["legendary"].items():
        assert set(rec["traits"]) <= traits, rec_id
        assert set(rec["yields"]) <= yields, rec_id
        assert rec["legendary"] is True, rec_id
        assert sum(rec["yields"].values()) == pool["budget"]["legendary"], rec_id
