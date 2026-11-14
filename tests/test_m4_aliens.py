"""M4: alien progress and tech, fortresses, spawning, reinforcements, decay, sieges, capital
succession, raids, fallen continents and reproducibility."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, NA, add_city, arena, at, east

from beacon import aliens, combat, config, fog, network
from beacon.game import new_game
from beacon.liberation import update_fallen
from beacon.runner import play
from beacon.state import (
    ACTIVE,
    ALIENS,
    DORMANT,
    OVERRUN,
    state_digest,
    state_from_json,
    state_to_json,
)
from beacon.tiles import is_passable_land
from beacon.turn import reset_units
from beacon.units import create_unit


def test_progress_follows_cities_and_has_a_floor(cfg):
    s = arena(cfg)
    p = cfg.alien("progress")
    assert aliens.progress_rate(s, cfg) == p["floor"]
    for k in range(6):
        add_city(s, cfg, at(1 + 2 * k, 1), OVERRUN, ALIENS, pop=5)
    expected = p["base"] + 6 * p["per_city"] + 30 * p["per_pop_pct"] // 100
    assert aliens.progress_rate(s, cfg) == max(p["floor"], expected)


def test_alien_techs_unlock_in_order_with_effects(cfg):
    s = arena(cfg)
    order = cfg.alien_tech_order()
    s.aliens.progress = sum(cfg.alien_techs[t]["cost"] for t in order[:2])
    aliens.research(s, cfg)  # adds this turn's progress, then buys what it can
    assert s.aliens.techs[:2] == order[:2]
    assert "alien_spitter" in aliens.unlocked_units(s, cfg)
    assert "alien_titan" not in aliens.unlocked_units(s, cfg)
    city = add_city(s, cfg, at(5, 5), OVERRUN, ALIENS)
    sources = {line["source"] for line in combat.city_strength(s, cfg, city).lines}
    assert "alien_walls" in sources


def test_alien_cities_harden_as_they_shrink_and_over_time(cfg):
    s = arena(cfg)
    for k in range(4):
        add_city(s, cfg, at(1 + 3 * k, 2), OVERRUN, ALIENS)
    s.aliens.start_cities = 4
    assert combat.hardening_pct(s, cfg) == 0
    s.cities[0].status, s.cities[0].owner = ACTIVE, EU
    f = cfg.alien("fortress")
    assert combat.hardening_pct(s, cfg) == 25 * f["per_lost_share_pct"] // 100
    s.turn = f["interval_turns"] * 2
    assert combat.hardening_pct(s, cfg) == min(
        f["cap_pct"], 25 * f["per_lost_share_pct"] // 100 + 2 * f["per_interval_pct"]
    )


def test_alien_cities_rebuild_garrisons_and_respect_the_cap(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(6, 5), OVERRUN, ALIENS, pop=3)
    city.production_store = cfg.units[cfg.alien("cities.garrison")]["cost"]
    aliens.city_turn(s, cfg)
    guards = s.units_at(city.tile)
    assert guards and guards[0].type == cfg.alien("cities.garrison")
    cap_units = cfg.alien("cities.units_per_city_pct") * 1 // 100  # one alien city
    city.production_store = 10_000
    for _ in range(5):
        aliens.city_turn(s, cfg)
    alien_units = [u for u in s.units.values() if u.owner == ALIENS]
    assert len(alien_units) <= max(1, cap_units) + 1


def test_reinforcements_land_when_the_store_is_full(cfg):
    s = arena(cfg)
    add_city(s, cfg, at(6, 5), OVERRUN, ALIENS)
    r = cfg.alien("reinforcements")
    s.aliens.reinforcement_store = r["cost"] - r["per_turn"]
    events = aliens.reinforcements(s, cfg)
    assert len(events) == len(r["units"])
    assert s.aliens.reinforcement_store == 0


@pytest.fixture(scope="module")
def doom_cfg():
    def certain(raw):
        d = raw["aliens"]["decay"]
        d["base_permille"], d["cap_permille"] = 1000, 1000

    return config.load(overrides=certain)


def test_lost_cities_fall_unless_guarded(doom_cfg):
    cfg = doom_cfg
    s = arena(cfg)
    open_city = add_city(s, cfg, at(2, 2), DORMANT, None, pop=2)
    guarded = add_city(s, cfg, at(10, 7), DORMANT, None, pop=2)
    create_unit(s, cfg, "infantry", EU, east(guarded.tile, -1))
    events = aliens.decay(s, cfg)
    assert [e["city"] for e in events] == [open_city.id]
    assert open_city.status == OVERRUN and s.units_at(open_city.tile)
    assert guarded.status == DORMANT


def test_capture_moves_the_capital_and_counts_the_loss(cfg):
    s = arena(cfg)
    capital = add_city(s, cfg, at(4, 4), ACTIVE, EU, pop=3)
    capital.is_capital = True
    other = add_city(s, cfg, at(10, 4), ACTIVE, EU, pop=5)
    brute = create_unit(s, cfg, "alien_brute", ALIENS, east(capital.tile))
    capital.hp = 1
    events = combat.attack(s, cfg, brute, capital.tile)
    kinds = [e["kind"] for e in events]
    assert "city_overrun" in kinds and "capital_moved" in kinds
    assert capital.owner == ALIENS and not capital.is_capital
    assert other.is_capital
    assert s.players[EU].credits["cities_lost"] == 1


def test_director_besieges_a_weak_player_city(cfg):
    s = arena(cfg)
    s.turn = cfg.alien("director.grace_turns")
    city = add_city(s, cfg, at(7, 5), ACTIVE, EU, pop=1)
    city.is_capital = True
    for tile in (at(4, 3), at(4, 5), at(4, 7)):
        create_unit(s, cfg, "alien_brute", ALIENS, tile)
    for _ in range(8):
        aliens.Director(s, cfg).run()
        reset_units(s, cfg)
        if city.status == OVERRUN:
            break
    assert city.status == OVERRUN


def test_pillage_cuts_a_connection(cfg):
    s = arena(cfg)
    capital = add_city(s, cfg, at(2, 4), ACTIVE, EU)
    capital.is_capital = True
    town = add_city(s, cfg, at(6, 4), ACTIVE, EU)
    for k in range(1, 4):
        s.tiles[east(capital.tile, k)].route = "road"
        s.tiles[east(capital.tile, k)].built_by = EU
    network.update_connections(s, cfg, EU)
    assert town.connected
    raider = create_unit(s, cfg, "alien_drone", ALIENS, east(capital.tile, 2))
    events = aliens.pillage(s, cfg, raider)
    assert events[0]["kind"] == "pillaged"
    network.update_connections(s, cfg, EU)
    assert not town.connected
    assert s.tiles[east(capital.tile, 2)].built_by is None
    assert east(capital.tile, 2) not in fog.built_tiles(s).get(EU, [])


def test_aliens_capture_lone_civilians(cfg):
    s = arena(cfg)
    a = at(5, 5)
    drone = create_unit(s, cfg, "alien_drone", ALIENS, a)
    eng = create_unit(s, cfg, "engineers", EU, east(a))
    assert combat.preview_attack(s, cfg, drone, east(a))["kind"] == "capture"
    combat.attack(s, cfg, drone, east(a))
    assert str(eng.id) not in s.units and drone.tile == east(a)


def test_besieged_cities_do_not_heal(cfg):
    from beacon.turn import heal_cities

    s = arena(cfg)
    city = add_city(s, cfg, at(5, 5), OVERRUN, ALIENS)
    city.hp = 100
    art = create_unit(s, cfg, "artillery", NA, east(city.tile, -1))
    combat.attack(s, cfg, art, city.tile)
    hit = city.hp
    heal_cities(s, cfg)
    assert city.hp == hit
    heal_cities(s, cfg)
    assert city.hp > hit


def test_fallen_and_revived(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(5, 5), ACTIVE, NA)
    events = update_fallen(s)
    assert [(e["kind"], e["player"]) for e in events] == [("continent_fallen", EU)]
    city.owner = EU
    events = update_fallen(s)
    kinds = {(e["kind"], e["player"]) for e in events}
    assert ("continent_revived", EU) in kinds and ("continent_fallen", NA) in kinds
    assert s.players[EU].times_fallen == 1


def test_alien_phase_is_reproducible_and_stays_on_land(cfg):
    base = new_game(cfg, seed=8)
    for _ in range(12):
        from beacon.turn import advance_turn

        advance_turn(base, cfg)
    text = state_to_json(base)
    a, b = state_from_json(text), state_from_json(text)
    aliens.alien_phase(a, cfg)
    aliens.alien_phase(b, cfg)
    assert state_digest(a) == state_digest(b)
    for unit in a.units.values():
        if unit.owner == ALIENS:
            assert is_passable_land(cfg, a.tiles[unit.tile])


def test_lost_cities_split_by_quota(cfg):
    state = new_game(cfg, seed=5)
    per = {}
    for city in state.cities:
        if city.status == OVERRUN:
            per[city.continent] = per.get(city.continent, 0) + 1
    weights = cfg.t("cities.lost_state_weights")
    share = weights["overrun"] * 100 // sum(weights.values())
    for cid, count in per.items():
        lost = sum(1 for c in state.cities if c.continent == cid) - cfg.t("cities.known_count")
        assert abs(count * 100 - lost * share) <= 100, cid


def test_aliens_take_cities_in_a_bot_game(cfg):
    state, events, _ = play(cfg, seed=2, turns=40)
    kinds = {e["kind"] for e in events}
    assert {"alien_spawned", "alien_tech", "attack"} <= kinds
    assert any(e["kind"] == "city_liberated" for e in events)
