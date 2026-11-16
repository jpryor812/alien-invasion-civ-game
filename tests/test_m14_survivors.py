"""M14: the survivor start (docs/SPEC_M14.md, designer 2026-11-15)."""

from __future__ import annotations

import pytest

from beacon import combat, hexgrid, survivors
from beacon.actions import apply_command
from beacon.commands import Attack, MoveUnit
from beacon.game import new_game
from beacon.liberation import update_fallen
from beacon.state import ACTIVE, OVERRUN, state_from_json, state_to_json
from beacon.turn import advance_turn
from beacon.units import create_unit, remove_unit

EU = "europe"


@pytest.fixture(scope="module")
def world(cfg):
    return new_game(cfg, seed=2, start="survivor")


def band_of(state, pid):
    return [u for u in state.sorted_units() if u.owner == pid]


def test_each_player_starts_as_a_band_near_its_first_town(cfg, world):
    sv = cfg.t("survivor")
    for pid in world.player_ids():
        p = world.players[pid]
        band = band_of(world, pid)
        assert sorted(u.type for u in band) == ["band_leader"] + ["survivor"] * 4
        assert (
            cfg.units["band_leader"]["strength"] == 20 and cfg.units["survivor"]["strength"] == 10
        )
        assert not p.founded and not p.fallen
        assert not any(c.owner == pid for c in world.cities)
        town = world.cities[p.band_town]
        assert town.status == OVERRUN and not town.is_capital and town.contents is None
        assert hexgrid.distance(p.band_home, town.tile, world.width) == sv["band_distance"]
        near = [
            int(k)
            for k, kind in world.caches.items()
            if hexgrid.distance(int(k), p.band_home, world.width) <= sv["near_radius"]
            and kind in ("weapon", "armour")
        ]
        assert len(near) >= sv["near_caches"]  # an upgrade within the first few turns
    assert state_to_json(state_from_json(state_to_json(world))) == state_to_json(world)
    assert update_fallen(world) == []  # a band without a city has not fallen


def test_caches_give_gear_people_and_scrap(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    lead = next(u for u in band_of(s, EU) if u.type == "band_leader")
    s.caches = {}
    spots = [
        n
        for n in hexgrid.within(lead.tile, 3, s.width, s.height)
        if not s.units_at(n) and s.city_at(n) is None and s.tiles[n].continent == EU
    ]
    for tile, kind in zip(spots, ("weapon", "alien_weapon", "survivor", "scrap"), strict=False):
        s.caches[str(tile)] = kind
    before = combat.unit_strength(s, cfg, lead, ranged=False, defending=False).total
    for tile in spots[:4]:
        lead.tile = tile
        survivors.pick_up(s, cfg)
    assert lead.gear == ["alien_weapon"]  # the better weapon replaced the rifle
    after = combat.unit_strength(s, cfg, lead, ranged=False, defending=False).total
    assert after > before
    assert len(band_of(s, EU)) == 6 and s.players[EU].scrap == 20
    assert s.players[EU].band_finds == 3 and not s.caches


def test_the_town_holds_against_a_bare_band_and_falls_after_a_find(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    s.caches = {}
    town = s.cities[s.players[EU].band_town]
    lead = next(u for u in band_of(s, EU) if u.type == "band_leader")
    lead.tile = next(
        n for n in hexgrid.neighbours(town.tile, s.width, s.height) if not s.units_at(n)
    )
    town.hp = 5
    for g in [u for u in s.units_at(town.tile)]:
        remove_unit(s, g)
    apply_command(s, cfg, Attack(player=EU, unit=lead.id, target=town.tile))
    assert town.hp == 1 and town.status == OVERRUN  # the barricades hold
    s.players[EU].band_finds = 1
    lead.attacks_left, lead.moves_left, lead.hp = 1, 60, 100
    apply_command(s, cfg, Attack(player=EU, unit=lead.id, target=town.tile))
    assert town.status == ACTIVE and town.owner == EU and town.is_capital
    p = s.players[EU]
    assert p.founded and not any(u.type == "band_leader" for u in band_of(s, EU))
    assert town.pop >= 2 + 3  # the bare survivors moved in
    assert {u.type for u in s.units.values() if u.owner == EU} >= {"engineers", "recon_team"}


def test_a_fallen_leader_escapes_with_two_survivors(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    for u in band_of(s, EU):
        remove_unit(s, u)
    events = survivors.escape(s, cfg)
    assert events[0]["kind"] == "leader_escaped"
    assert sorted(u.type for u in band_of(s, EU)) == ["band_leader", "survivor", "survivor"]


def test_hunters_leave_a_distant_band_alone(cfg):
    from beacon.aliens import Director

    s = new_game(cfg, seed=2, start="survivor")
    s.turn = 20
    lead = next(u for u in band_of(s, EU) if u.type == "band_leader")
    far = hexgrid.within(lead.tile, 4, s.width, s.height)
    spot = next(
        t
        for t in far
        if hexgrid.distance(t, lead.tile, s.width) == 4
        and not s.units_at(t)
        and s.tiles[t].continent == EU
        and s.city_at(t) is None
    )
    hunter = create_unit(s, cfg, "alien_drone", "aliens", spot)
    prey = Director(s, cfg).hunt_target(hunter)
    assert prey is None or s.units[str(prey)].owner != EU


def test_ai_bands_take_their_towns(cfg):
    from beacon.runner import first_city_turns, play

    state, events, _ = play(cfg, seed=4, turns=14, driver="ai", start="survivor")
    turns = first_city_turns(state)
    taken = [t for t in turns.values() if t is not None]
    assert len(taken) >= 4 and min(taken) <= 7
    assert any(e["kind"] == "loot_found" for e in events)


def test_classic_start_is_unchanged(cfg):
    s = new_game(cfg, seed=2, start="classic")
    assert all(p.founded and p.band_town is None for p in s.players.values())
    assert not s.caches and all(
        any(c.owner == pid and c.is_capital for c in s.cities) for pid in s.player_ids()
    )


def test_a_band_unit_moves_onto_a_cache(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    lead = next(u for u in band_of(s, EU) if u.type == "band_leader")
    tile = next(
        n
        for n in hexgrid.neighbours(lead.tile, s.width, s.height)
        if not s.units_at(n) and s.city_at(n) is None
    )
    s.caches = {str(tile): "armour"}
    events = apply_command(s, cfg, MoveUnit(player=EU, unit=lead.id, target=tile))
    assert any(e["kind"] == "loot_found" for e in events) and lead.gear == ["armour"]
    advance_turn(s, cfg)
