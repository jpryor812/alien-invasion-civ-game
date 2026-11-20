"""Fixes from play (docs/SPEC_M20.md, designer 2026-11-19)."""

from __future__ import annotations

import pytest

from beacon import armoury, borders, citizens, council, hexgrid, starfall, works
from beacon.actions import apply_command, pending_decisions
from beacon.cities import work_tiles
from beacon.commands import CommandError, EquipGear, JoinCity, SetCitizenJob
from beacon.game import new_game
from beacon.state import state_from_json, state_to_json
from beacon.units import create_unit

EU = "europe"


def _capital(cfg, seed=2):
    s = new_game(cfg, seed=seed, start="classic")
    return s, next(c for c in s.cities if c.owner == EU and c.is_capital)


def test_land_starts_at_one_ring_and_grows_a_hex_per_birth(cfg):
    s, city = _capital(cfg)
    assert len(city.border) == 7 + (city.pop - 1)
    assert set(work_tiles(s, cfg, city)) == set(city.border) - {city.tile}
    before = set(city.border)
    born = citizens.born(s, cfg, city)
    assert born["claimed"] is not None and set(city.border) == before | {born["claimed"]}
    assert s.tiles[born["claimed"]].city == city.id
    assert all(hexgrid.distance(t, city.tile, s.width) <= 3 for t in city.border)
    for _ in range(60):
        borders.grow(s, cfg, city)
    assert all(hexgrid.distance(t, city.tile, s.width) <= 3 for t in city.border)
    others = {t for c in s.cities if c.id != city.id and c.border for t in c.border}
    assert not others & set(city.border)
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_council_votes_are_off_but_seats_stay(cfg):
    s, city = _capital(cfg)
    assert not council.sessions_on(cfg)
    for _ in range(12):
        assert council.end_of_turn(s, cfg) == []
        s.turn += 1
    assert not s.council.measures and council.unvoted(s, EU, cfg) == []
    person = next(c for c in citizens.of_city(s, city.id) if c.adult)
    apply_command(s, cfg, SetCitizenJob(player=EU, citizen=person.id, job="council:general"))
    citizens.assign(s, cfg, EU)
    assert person.seats == ["general"]
    apply_command(s, cfg, SetCitizenJob(player=EU, citizen=person.id, job="idle"))
    citizens.assign(s, cfg, EU)
    assert person.seats == [] and person.tile is None  # freed: it does not jump back on


def test_the_first_barracks_is_cheap(cfg):
    s, city = _capital(cfg)
    b = cfg.materials("barracks.building")
    city.buildings = [x for x in city.buildings if x != b]
    full = works.building_labour(cfg, b)
    assert works.first_barracks(s, cfg, city, b)
    assert works.labour_for(s, cfg, city, b) < full
    cheap = works.building_cost(s, cfg, city, b)
    from beacon import materials

    assert sum(cheap.values()) < sum(materials.building_cost(cfg, b).values())
    city.buildings.append(b)
    other = next(c for c in s.cities if c.owner != EU)
    other.owner = EU  # a second town of the same player
    assert not works.first_barracks(s, cfg, other, b)


def test_carried_gear_goes_to_the_armoury_and_a_soldier_takes_it(cfg):
    s, city = _capital(cfg)
    scout = create_unit(s, cfg, "recon_team", EU, city.tile)
    scout.pack = ["weapon"]
    assert armoury.carries_only(cfg, scout)
    events = armoury.deposit(s, cfg)
    assert events[0]["kind"] == "gear_stored" and city.armoury == {"weapon": 1}
    assert scout.pack == []
    soldier = create_unit(s, cfg, "infantry", EU, city.tile)
    with pytest.raises(CommandError, match="carry"):
        apply_command(s, cfg, EquipGear(player=EU, unit=scout.id, item="weapon"))
    apply_command(s, cfg, EquipGear(player=EU, unit=soldier.id, item="weapon"))
    assert soldier.gear == ["weapon"] and city.armoury == {}


def test_a_unit_in_its_land_can_join_the_town(cfg):
    s, city = _capital(cfg)
    pop = city.pop
    unit = create_unit(s, cfg, "infantry", EU, city.tile)
    unit.gear = ["armour"]
    apply_command(s, cfg, JoinCity(player=EU, unit=unit.id))
    assert city.pop == pop + 1 and str(unit.id) not in s.units
    assert city.armoury == {"armour": 1}
    assert len(citizens.of_city(s, city.id)) == city.pop
    far = next(
        i
        for i in range(len(s.tiles))
        if hexgrid.distance(i, city.tile, s.width) > 6 and s.tiles[i].continent == EU
    )
    away = create_unit(s, cfg, "infantry", EU, far)
    with pytest.raises(CommandError, match="land"):
        apply_command(s, cfg, JoinCity(player=EU, unit=away.id))


def test_the_band_can_mine_remnants_and_finds_more_crates(cfg):
    assert starfall.can_mine(cfg, EU, "survivor") and starfall.can_mine(cfg, EU, "band_leader")
    s = new_game(cfg, seed=2, start="survivor")
    home = s.players[EU].band_home
    far = [
        k
        for k in s.caches
        if s.tiles[int(k)].continent == EU
        and hexgrid.distance(int(k), home, s.width) > cfg.t("survivor.radius")
    ]
    assert len(far) >= 6


def test_the_first_town_must_repair_its_farm(cfg):
    from web.session import Session

    sess = Session(cfg, seed=2, human=EU, start="survivor")
    s = sess.state
    p = s.players[EU]
    town = s.cities[p.band_town]
    town.status, town.owner, p.founded = "active", EU, True
    borders.start(s, cfg, town)
    from beacon.food import damaged_farm

    tile = damaged_farm(s, cfg, town)
    assert tile is not None
    pend = pending_decisions(s, cfg, EU)
    assert pend[0] == {"kind": "repair_farm", "city": town.id, "tile": tile}
    out = sess.end_turn()
    assert out["ok"] is False and "farm" in out["error"]


def test_develop_city_prompts_only_for_idle_engineers(cfg):
    s, city = _capital(cfg)
    works.ensure_crew(cfg, city)
    city.works = []
    assert {"kind": "choose_production", "city": city.id} in pending_decisions(s, cfg, EU)
    tile = next(t for t in work_tiles(s, cfg, city) if s.tiles[t].improvement is None)
    city.works = [{"id": 1, "what": "tile:farm", "left": 8, "total": 8, "paid": {}, "tile": tile}]
    city.queue = []
    assert {"kind": "choose_production", "city": city.id} not in pending_decisions(s, cfg, EU)
