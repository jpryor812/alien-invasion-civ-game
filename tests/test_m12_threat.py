"""M12: a readable alien that reacts to you (docs/SPEC_M12.md, designer 2026-11-15)."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, NA, add_city, arena, at

from beacon import config, liberation, threat
from beacon.actions import apply_command
from beacon.aliens import Director
from beacon.commands import ArmResistance, CommandError, Sabotage
from beacon.game import new_game
from beacon.state import ACTIVE, ALIENS, OVERRUN, state_from_json, state_to_json
from beacon.units import create_unit
from web.session import Session


def test_heat_counts_population_buildings_and_convoys(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(3, 3), ACTIVE, EU, pop=4)
    base = threat.heat(s, cfg, EU)
    assert base == 4 * cfg.alien("heat.per_pop")
    city.buildings = ["beacon_i", "factory"]
    h = cfg.alien("heat.buildings")
    assert threat.heat(s, cfg, EU) == base + h["beacon_i"] + h["factory"]


def test_a_siege_is_announced_then_launched_on_time(cfg):
    s = arena(cfg)
    s.turn = 40
    city = add_city(s, cfg, at(3, 4), ACTIVE, EU, pop=3)
    a = create_unit(s, cfg, "alien_warrior", ALIENS, at(9, 4))
    b = create_unit(s, cfg, "alien_warrior", ALIENS, at(10, 4))
    d = Director(s, cfg)
    d.announce(a, city.tile)
    plan = next(iter(s.aliens.plans.values()))
    assert plan.player == EU and plan.launch == 40 + cfg.alien("plans.strike_turns")
    assert set(plan.units) >= {a.id, b.id}
    assert s.aliens.orders[str(a.id)].kind == "gather"
    assert any(e["kind"] == "strike_announced" and e["player"] == EU for e in d.events)
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)
    s.turn = plan.launch - 1
    Director(s, cfg).launch_plans()
    assert s.aliens.plans  # not yet
    s.turn = plan.launch
    d2 = Director(s, cfg)
    d2.launch_plans()
    assert not s.aliens.plans and s.aliens.orders[str(a.id)].kind == "siege"
    assert any(e["kind"] == "strike_launched" for e in d2.events)


def test_a_plan_on_a_lost_city_is_dropped(cfg):
    s = arena(cfg)
    s.turn = 40
    city = add_city(s, cfg, at(3, 4), ACTIVE, EU, pop=3)
    a = create_unit(s, cfg, "alien_warrior", ALIENS, at(9, 4))
    Director(s, cfg).announce(a, city.tile)
    city.status, city.owner = OVERRUN, ALIENS
    Director(s, cfg).launch_plans()
    assert not s.aliens.plans and str(a.id) not in s.aliens.orders


def test_hotter_players_are_better_targets(cfg):
    s = arena(cfg)
    s.turn = 40
    quiet = add_city(s, cfg, at(3, 4), ACTIVE, EU, pop=3)
    loud = add_city(s, cfg, at(11, 4), ACTIVE, NA, pop=3)
    a = create_unit(s, cfg, "alien_warrior", ALIENS, at(7, 4))
    d = Director(s, cfg)
    first = d.siege_target(a)
    loud.buildings = ["beacon_v", "factory", "quantum_lab", "fusion_plant"]
    hot = Director(s, cfg).siege_target(a)
    assert hot == loud.tile and (first == quiet.tile or first == loud.tile)


def test_alien_cities_hold_contents_seen_as_rumours_and_given_on_liberation(cfg):
    s = new_game(cfg, seed=2)
    held = [c for c in s.cities if c.status == OVERRUN]
    assert all(c.contents in cfg.alien("contents") for c in held)
    assert len({c.contents for c in held}) >= 4
    assert sum(1 for t in s.tiles if t.nest is not None) >= len(held)
    city = held[0]
    assert threat.rumour(cfg, city) == cfg.alien(f"contents.{city.contents}.rumour")
    # a recon unit beside it learns the truth
    pid = "europe"
    near = next(
        n
        for n in __import__("beacon").hexgrid.neighbours(city.tile, s.width, s.height)
        if not s.units_at(n)
    )
    create_unit(s, cfg, "recon_team", pid, near)
    events = threat.update_intel(s, cfg)
    assert city.id in s.players[pid].intel and events[0]["contents"] == city.contents
    city.contents = "depot"
    gold = s.players[pid].gold
    out = liberation.liberate(s, cfg, city, pid)
    found = next(e for e in out if e["kind"] == "contents_found")
    assert s.players[pid].gold == gold + cfg.alien("contents.depot.gold") and found["result"]
    assert city.contents is None


def test_sabotage_and_arming_the_resistance(cfg):
    s = arena(cfg)
    alien = add_city(s, cfg, at(6, 4), OVERRUN, ALIENS, pop=3)
    alien.contents = "lab"
    eng = create_unit(s, cfg, "engineers", EU, at(5, 4))
    far = create_unit(s, cfg, "engineers", EU, at(2, 2))
    with pytest.raises(CommandError, match="beside"):
        apply_command(s, cfg, Sabotage(player=EU, unit=far.id, city=alien.id))
    hp = alien.hp
    apply_command(s, cfg, Sabotage(player=EU, unit=eng.id, city=alien.id))
    assert alien.hp < hp and alien.damage_by[EU] > 0
    with pytest.raises(CommandError, match="moves"):
        apply_command(s, cfg, Sabotage(player=EU, unit=eng.id, city=alien.id))
    inf = create_unit(s, cfg, "infantry", EU, at(7, 4))
    s.players[EU].gold = 1000
    apply_command(s, cfg, ArmResistance(player=EU, unit=inf.id, city=alien.id))
    assert alien.resistance == 1 and s.players[EU].gold == 1000 - cfg.alien("resistance.gold")


def test_an_armed_city_rises(cfg):
    def sure(raw):
        raw["aliens"]["resistance"]["uprising_pct"] = 100

    hard = config.load(overrides=sure)
    s = arena(hard)
    alien = add_city(s, hard, at(6, 4), OVERRUN, ALIENS, pop=3)
    guard = create_unit(s, hard, "alien_hive_guard", ALIENS, alien.tile)
    alien.resistance, alien.armed_by = 1, {EU: 1}
    hp, ghp = alien.hp, guard.hp
    events = threat.uprisings(s, hard)
    assert events and events[0]["kind"] == "uprising" and events[0]["player"] == EU
    assert alien.hp < hp and guard.hp < ghp and alien.resistance == 0


def test_nests_feed_their_city_until_a_soldier_destroys_one(cfg):
    s = arena(cfg)
    alien = add_city(s, cfg, at(6, 4), OVERRUN, ALIENS, pop=3)
    s.tiles[at(8, 4)].nest = alien.id
    alien.hp -= 50
    hp, store = alien.hp, alien.production_store
    threat.nest_turn(s, cfg)
    assert alien.hp == hp + cfg.alien("nests.heal") and alien.production_store > store
    create_unit(s, cfg, "infantry", EU, at(8, 4))
    events = threat.nest_turn(s, cfg)
    assert events[0]["kind"] == "nest_destroyed" and s.tiles[at(8, 4)].nest is None


def test_session_shows_strikes_heat_and_actions(cfg, tmp_path, monkeypatch):
    from web import profile
    from web import session as session_mod

    monkeypatch.setattr(session_mod, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(profile, "PROFILE", tmp_path / "profile.json")
    sess = Session(cfg, seed=3, human=EU)
    s = sess.state
    s.turn = 40
    capital = next(c for c in s.cities if c.owner == EU and c.is_capital)
    a = create_unit(s, cfg, "alien_warrior", ALIENS, capital.tile + 8)
    Director(s, cfg).announce(a, capital.tile)
    v = sess.view()
    assert v["heat"] > 0 and v["strikes"][0]["city"] == capital.id
    assert v["strikes"][0]["turns"] == cfg.alien("plans.strike_turns")
