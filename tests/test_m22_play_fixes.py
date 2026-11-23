"""Fixes from play (docs/SPEC_M22.md, designer 2026-11-22)."""

from __future__ import annotations

import pytest

from beacon import contact, materials, starfall, works
from beacon.actions import apply_command
from beacon.commands import CommandError, MineShard
from beacon.game import new_game
from beacon.state import ALIENS, Shard
from beacon.units import create_unit

EU = "europe"


def _capital(cfg, seed=2):
    s = new_game(cfg, seed=seed, start="classic")
    return s, next(c for c in s.cities if c.owner == EU and c.is_capital)


def test_no_goods_without_mines_or_camps(cfg):
    s, city = _capital(cfg)
    tile = s.tiles[city.tile]
    assert materials.income(s, cfg, city, []) == dict.fromkeys(materials.goods(cfg), 0)
    tile.feature = "forest"
    assert sum(materials.tile_goods(cfg, tile).values()) == 0
    tile.feature, tile.improvement = None, "mine"
    assert materials.tile_goods(cfg, tile)["stone"] > 0


def test_a_building_takes_its_materials_when_started(cfg):
    s, city = _capital(cfg)
    from beacon import economy

    b = next(
        x
        for x in economy.building_options(s, cfg, city)
        if materials.building_cost(cfg, x) and works.building_problem(s, cfg, city, x) is None
    )
    city.stores = {"timber": 0, "stone": 0, "iron": 0}
    city.works = []
    works.order_building(s, cfg, city, b)
    job = city.works[0]
    assert job["paid"] == {} and job["cost"]
    works.progress(s, cfg, city)
    assert job["waiting"] and job["left"] == job["total"]  # waits for timber and stone
    city.stores = {g: 999 for g in materials.goods(cfg)}
    works.progress(s, cfg, city)
    assert job["paid"] == job["cost"] and city.stores["timber"] == 999 - job["cost"].get(
        "timber", 0
    )


def test_units_do_not_stack_and_do_not_starve(cfg):
    from beacon import movement
    from beacon.turn import advance_turn

    s, city = _capital(cfg)
    a = create_unit(s, cfg, "infantry", EU, city.tile)
    b = create_unit(s, cfg, "infantry", EU, city.tile)
    assert "stack" in movement.merge_problem(s, cfg, a, b)
    assert not cfg.t("food.rations_on")
    from beacon import hexgrid

    far = next(
        t
        for t in range(len(s.tiles))
        if s.tiles[t].continent == EU
        and not s.units_at(t)
        and s.city_at(t) is None
        and all(hexgrid.distance(t, c.tile, s.width) > 6 for c in s.cities if c.owner == EU)
    )
    a.tile, a.rations = far, 0
    hp = a.hp
    events = advance_turn(s, cfg)
    assert not any(e["kind"] in ("unit_hungry", "unit_starved", "rations_out") for e in events)
    assert str(a.id) not in s.units or s.units[str(a.id)].hp >= hp


def test_founding_keeps_survivors_as_units(cfg):
    from beacon import survivors

    s = new_game(cfg, seed=2, start="survivor")
    p = s.players[EU]
    town = s.cities[p.band_town]
    band = [u for u in s.units.values() if u.owner == EU]
    town.status, town.owner = "active", EU
    survivors.found(s, cfg, town, EU)
    left = [u for u in s.units.values() if u.owner == EU]
    assert all(u.type == "survivor" for u in left)
    assert len(left) == len(band) - 1  # only the leader left the map
    assert town.pop == cfg.t("survivor.town_rescued")


def test_mining_is_an_order_and_the_aliens_come(cfg):
    s, city = _capital(cfg)
    tile = next(
        t
        for t in range(len(s.tiles))
        if s.tiles[t].continent == EU
        and not s.units_at(t)
        and s.city_at(t) is None
        and s.tiles[t].terrain in ("grassland", "plains")
    )
    shard = Shard(
        id=s.new_id(),
        kind=sorted(cfg.story("starfall")["kinds"])[0],
        tile=tile,
        warn_turn=0,
        impact_turn=0,
        cone_center=tile,
        cone_radius=0,
        remnant=True,
    )
    s.shards[str(shard.id)] = shard
    scout = create_unit(s, cfg, "recon_team", EU, tile)
    starfall.end_of_turn(s, cfg)
    assert shard.progress.get(EU, 0) == 0  # standing is not mining
    soldier = create_unit(s, cfg, "infantry", EU, city.tile)
    with pytest.raises(CommandError):
        apply_command(s, cfg, MineShard(player=EU, unit=soldier.id))
    apply_command(s, cfg, MineShard(player=EU, unit=scout.id))
    aliens = sum(1 for u in s.units.values() if u.owner == ALIENS)
    events = starfall.end_of_turn(s, cfg)
    assert shard.progress[EU] == 1 and shard.contested
    assert any(e["kind"] == "aliens_contest_shard" for e in events)
    assert sum(1 for u in s.units.values() if u.owner == ALIENS) > aliens


def test_meeting_shows_each_others_capitals(cfg):
    s, _ = _capital(cfg)
    asia = next(c for c in s.cities if c.owner == "asia" and c.is_capital)
    mine = next(c for c in s.cities if c.owner == EU and c.is_capital)
    s.players[EU].met, s.players["asia"].met = [], []
    s.players[EU].known_cities.pop(str(asia.id), None)
    contact.meet(s, EU, "asia", "radio", share=False)
    assert str(asia.id) in s.players[EU].known_cities
    assert str(mine.id) in s.players["asia"].known_cities
