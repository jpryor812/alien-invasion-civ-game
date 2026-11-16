"""M10: the designer's playtest changes (docs/SPEC_M10.md, 2026-11-15)."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, NA, add_city, arena, at, east
from test_m9_citizens import person

from beacon import economy
from beacon.actions import apply_command
from beacon.commands import CommandError, Purchase, SetConvoy, SetProduction
from beacon.state import ACTIVE, state_from_json, state_to_json


def test_council_stats_count_in_every_city(cfg):
    s = arena(cfg)
    home = add_city(s, cfg, at(2, 2), ACTIVE, EU, pop=1)
    other = add_city(s, cfg, at(9, 6), ACTIVE, EU, pop=1)
    c = person(s, home, {"science": 3, "gold": 3})
    c.seats = ["general"]
    for city in (home, other):
        lines = economy.city_yields(s, cfg, city).lines
        assert (f"citizen:{c.name} (council)", "science", 3) in lines


def test_each_item_keeps_its_own_progress(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(3, 3), ACTIVE, EU, pop=3)
    city.buildings = ["military_base"]  # soldiers need a barracks (designer 2026-11-16)
    apply_command(s, cfg, SetProduction(player=EU, city=city.id, items=("unit:infantry",)))
    economy.player_turn(s, cfg, EU)
    kept = city.progress["unit:infantry"]
    assert kept > 0
    apply_command(s, cfg, SetProduction(player=EU, city=city.id, items=("unit:marines",)))
    economy.player_turn(s, cfg, EU)
    assert city.progress["unit:infantry"] == kept  # switching away keeps it
    assert 0 < city.progress["unit:marines"] <= kept  # the new item started from scratch
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_any_item_can_be_bought_without_touching_the_queue(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(3, 3), ACTIVE, EU, pop=3)
    city.queue = ["unit:infantry"]
    city.buildings = ["military_base"]
    city.stores = {"timber": 150, "stone": 150, "iron": 80}  # buildings cost materials (SPEC_M16)
    s.players[EU].gold = 10_000
    full = economy.purchase_price(cfg, "building:market", s.players[EU])
    city.progress["building:market"] = economy.item_cost(cfg, "building:market", s.players[EU]) // 2
    events = apply_command(s, cfg, Purchase(player=EU, city=city.id, item="building:market"))
    paid = next(e for e in events if e["kind"] == "purchased")["gold"]
    assert paid < full and "market" in city.buildings
    assert city.queue == ["unit:infantry"] and "building:market" not in city.progress


def test_a_convoy_needs_a_road_and_moves_a_share(cfg):
    s = arena(cfg)
    a = add_city(s, cfg, at(2, 4), ACTIVE, EU, pop=3)
    b = add_city(s, cfg, at(8, 4), ACTIVE, EU, pop=1)
    b.queue = ["building:market"]
    with pytest.raises(CommandError):
        apply_command(
            s, cfg, SetConvoy(player=EU, city=a.id, target=b.id, goods="production", pct=50)
        )
    for k in range(1, 6):
        s.tiles[east(a.tile, k)].route = "road"
    apply_command(s, cfg, SetConvoy(player=EU, city=a.id, target=b.id, goods="production", pct=50))
    before = economy.city_yields(s, cfg, a).totals["production"]
    economy.process_city(s, cfg, a, s.players[EU])
    assert b.incoming["production"] == before * 50 // 100
    economy.process_city(s, cfg, b, s.players[EU])
    assert b.progress["building:market"] >= before * 50 // 100 and not b.incoming
    with pytest.raises(CommandError):  # a foreign city that is not an ally
        c = add_city(s, cfg, at(2, 6), ACTIVE, NA, pop=1)
        apply_command(s, cfg, SetConvoy(player=EU, city=a.id, target=c.id, goods="food", pct=25))


def test_every_continent_has_3_to_5_remnants_that_do_not_block_starfall(cfg):
    from beacon import starfall
    from beacon.game import new_game

    s = new_game(cfg, seed=3)
    by = {}
    for x in s.shards.values():
        if x.remnant:
            by[s.tiles[x.tile].continent] = by.get(s.tiles[x.tile].continent, 0) + 1
    assert set(by) == {c.continent for c in s.cities}
    assert all(3 <= n <= 5 for n in by.values())
    assert starfall.active(s) and not starfall.falling(s)  # the sky still drops its own shards


def test_beacon_theory_meets_everyone(cfg):
    """Beacon contact as built in M10; off while contact is by radio only (2026-11-16)."""
    from beacon import config, contact

    s = arena(cfg)
    s.players[EU].techs = sorted([*s.players[EU].techs, cfg.t("contact.beacon_tech")])
    s.players[EU].met, s.players[NA].met = [], []
    assert contact.beacon_contact(s, cfg, EU) == []  # radio only

    def no_radio(raw):
        raw["tuning"]["contact"]["radio_building"]["value"] = None

    cfg = config.load(overrides=no_radio)
    s = arena(cfg)
    s.players[EU].met, s.players[NA].met = [], []
    assert contact.beacon_contact(s, cfg, EU) == []
    s.players[EU].techs = sorted([*s.players[EU].techs, cfg.t("contact.beacon_tech")])
    events = contact.beacon_contact(s, cfg, EU)
    assert events and contact.met(s, EU, NA)


def test_library_is_available_from_the_start_and_the_school_needs_it(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(3, 3), ACTIVE, EU, pop=2)
    options = economy.production_options(s, cfg, city)
    assert "building:library" in options and "building:school" not in options
    city.buildings = ["library"]
    assert "building:school" in economy.production_options(s, cfg, city)


def test_the_map_wraps_east_to_west_and_is_about_60_percent_land(cfg):
    from beacon import hexgrid
    from beacon.game import new_game
    from beacon.tiles import is_water

    s = new_game(cfg, seed=2)
    assert s.wrap and hexgrid.wraps(s.width)
    west, east_edge = hexgrid.index(0, 10, s.width), hexgrid.index(s.width - 1, 10, s.width)
    assert east_edge in hexgrid.neighbours(west, s.width, s.height)
    assert hexgrid.distance(west, east_edge, s.width) == 1
    land = sum(1 for t in s.tiles if not is_water(cfg, t))
    assert 55 <= land * 100 // len(s.tiles) <= 65
    assert state_from_json(state_to_json(s)).wrap
