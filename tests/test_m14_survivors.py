"""M14: the survivor start (docs/SPEC_M14.md, designer 2026-11-15)."""

from __future__ import annotations

import pytest

from beacon import combat, fog, hexgrid, survivors
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
            cfg.units["band_leader"]["strength"] == 30 and cfg.units["survivor"]["strength"] == 20
        )
        assert not p.founded and not p.fallen
        assert not any(c.owner == pid for c in world.cities)
        town = world.cities[p.band_town]
        assert town.status == OVERRUN and not town.is_capital and town.contents is None
        assert hexgrid.distance(p.band_home, town.tile, world.width) == sv["band_distance"]
        sight = fog.visible_tiles(world, cfg, pid)
        assert town.tile not in sight  # the band finds its town second (designer 2026-11-16)
        mine = [int(k) for k in world.caches if world.tiles[int(k)].continent == pid]
        assert all(t not in sight for t in mine)  # no crate in view, none beside the band
        to_town = hexgrid.distance(p.band_home, town.tile, world.width)
        near = [
            t
            for t in mine
            if world.caches[str(t)] in ("weapon", "armour")
            and hexgrid.distance(t, p.band_home, world.width) <= to_town
        ]
        assert len(near) >= sv["near_caches"]  # gear just past the band's sight, before the town
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
    s.players[EU].band_claimed = True  # the band has found it (designer 2026-11-17)
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
    assert {u.type for u in s.units.values() if u.owner == EU} >= {"recon_team"}
    assert town.engineers == cfg.materials("labour.town_start")  # the crew (SPEC_M17)


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
    assert len(taken) >= 3 and min(taken) <= 10
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


# -- radio contact and the AI's tools (designer 2026-11-16) -------------------------------------


def test_contact_needs_a_founded_city_with_a_radio_tower(cfg):
    from beacon import contact, council
    from beacon.state import Measure

    s = new_game(cfg, seed=2, start="survivor")
    assert all(p.met == [] for p in s.players.values())
    assert all(
        cfg.t("contact.radio_building") not in s.cities[p.band_town].buildings
        for p in s.players.values()
    )
    towns = {}
    for pid in ("europe", "asia", "africa"):
        town = s.cities[s.players[pid].band_town]
        town.status, town.owner = ACTIVE, pid
        s.players[pid].founded = True
        towns[pid] = town
    towns["europe"].buildings.append(cfg.t("contact.radio_building"))
    assert contact.radio(s, cfg) == []  # one on the air: nobody to hear
    towns["asia"].buildings.append(cfg.t("contact.radio_building"))
    contact.radio(s, cfg)
    assert s.players["europe"].met == ["asia"] and s.players["africa"].met == []
    assert council.members(s, cfg) == ["asia", "europe"]
    s.council.measures = [Measure(id=s.new_id(), kind="research_pact")]
    assert council.unvoted(s, "africa", cfg) == []  # off the air: no seat
    assert "radio" in council.vote_problem(s, cfg, "africa", s.council.measures[0].id, "yes", 0)


def test_the_ai_builds_its_radio_first_and_a_uav_when_it_can(cfg):
    from beacon.ai import AIPlayer

    s = new_game(cfg, seed=2, start="classic")
    capital = next(c for c in s.cities if c.owner == EU and c.is_capital)
    capital.buildings = [b for b in capital.buildings if b != "radio_tower"]
    capital.queue = []
    AIPlayer(s, cfg, EU, lambda c: apply_command(s, cfg, c)).buildings()
    assert capital.works[0]["what"] == "building:radio_tower"  # a work for the crew (SPEC_M17)
    capital.works = []
    capital.buildings.append("radio_tower")
    capital.queue = []
    s.players[EU].techs.append("drone_warfare")
    for _ in range(2):  # an army comes first
        from beacon.units import place_unit

        place_unit(s, cfg, "infantry", EU, capital.tile, 2)
    AIPlayer(s, cfg, EU, lambda c: apply_command(s, cfg, c)).production()
    assert capital.queue == ["unit:uav_patrol"]


def test_ai_soldiers_arm_resistance_clear_nests_and_defend_seen_strikes(cfg):
    from test_m3_units_combat import EU as E
    from test_m3_units_combat import add_city, arena, at

    from beacon.ai import AIPlayer
    from beacon.aliens import Director

    s = arena(cfg)
    s.players[E].character = sorted(cfg.ai("characters"))[0]
    home = add_city(s, cfg, at(2, 4), ACTIVE, E, pop=3)
    home.is_capital = True
    alien = add_city(s, cfg, at(9, 4), OVERRUN, "aliens", pop=3)
    s.players[E].known_cities[str(alien.id)] = __import__(
        "beacon.state", fromlist=["CityMemory"]
    ).CityMemory(status=OVERRUN, owner="aliens", pop=3, turn_seen=0)
    s.players[E].gold = 1000
    inf = create_unit(s, cfg, "infantry", E, at(8, 4))
    from beacon import fog

    fog.reveal_around(s, cfg, E, at(6, 4), 6)
    ai = AIPlayer(s, cfg, E, lambda c: apply_command(s, cfg, c))
    assert ai.tools(inf) and alien.resistance == 1
    s.tiles[at(7, 6)].nest = alien.id
    sol = create_unit(s, cfg, "infantry", E, at(6, 6))
    ai._armed = True
    assert ai.tools(sol) and sol.tile == at(7, 6)
    # a strike the city's UAV has seen pulls nearby soldiers home
    s.turn = 40
    raider = create_unit(s, cfg, "alien_warrior", "aliens", at(10, 7))
    Director(s, cfg).announce(raider, home.tile)
    create_unit(s, cfg, "uav_patrol", E, home.tile)
    guard = create_unit(s, cfg, "infantry", E, at(5, 2))
    assert ai.tools(guard) and hexgrid.distance(guard.tile, home.tile, s.width) < 3
