"""Citizens, healing, the city alert and the branching tech tree (designer, 2026-11-14)."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, add_city, arena, at, east

from beacon import citizens, economy, hexgrid, tech
from beacon.actions import apply_command, pending_decisions
from beacon.commands import CommandError, HoldFire, SetCitizenJob
from beacon.config import DOMAINS
from beacon.game import new_game
from beacon.state import ACTIVE, ALIENS, Citizen, state_from_json, state_to_json
from beacon.turn import advance_turn, reset_units
from beacon.units import create_unit


def city_with_tiles(cfg, s, pop=2, improved=("mine",)):
    city = add_city(s, cfg, at(5, 5), ACTIVE, EU, pop=pop)
    city.connected = True
    for t in hexgrid.within(city.tile, cfg.t("cities.work_radius"), s.width, s.height):
        s.tiles[t].city = city.id
    for k, imp in enumerate(improved):
        t = east(city.tile, k + 1)
        s.tiles[t].improvement = imp
        if imp == "mine":
            s.tiles[t].elevation = "hills"
    return city


def person(s, city, stats, traits=(), adult=True):
    c = Citizen(
        id=s.new_id(),
        city=city.id,
        name="Test",
        stats=stats,
        traits=list(traits),
        born=0,
        growth=100 if adult else 0,
        adult=adult,
    )
    s.citizens[str(c.id)] = c
    return c


def test_stats_follow_the_three_patterns(cfg):
    state = new_game(cfg, seed=4)
    seen = set()
    for c in state.citizens.values():
        assert sum(c.stats.values()) == cfg.t("citizens.stats.points") == 6
        assert set(c.stats) <= set(DOMAINS)
        seen.add(tuple(sorted(c.stats.values())))
        assert len(c.traits) <= 1
    assert seen <= {(1, 1, 1, 1, 1, 1), (3, 3), (2, 2, 2)}
    assert len(seen) == 3


def test_tile_gives_half_and_council_gives_full(cfg):
    # The designer's example: a mine gives +3 production; a +2/+2/+2 citizen on it makes the
    # tile give +4 production, +1 science and +1 gold. On the council: +2, +2, +2 to the city.
    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=1)
    mine = east(city.tile)
    c = person(s, city, {"production": 2, "science": 2, "gold": 2})
    c.job = f"tile:{mine}"
    citizens.assign(s, cfg, EU)
    assert c.tile == mine
    assert citizens.tile_bonus(cfg, c) == {  # hundredths: +2 gives +1, +3 would give +1.5
        "food": 0,
        "production": 100,
        "science": 100,
        "gold": 100,
        "beacon": 0,
    }
    on_tile = economy.city_yields(s, cfg, city)
    c.job = "council"
    citizens.assign(s, cfg, EU)
    assert c.tile is None and c.seats
    on_council = economy.city_yields(s, cfg, city)
    assert citizens.council_bonus(cfg, c)["science"] == 2
    assert on_council.totals["science"] - on_tile.totals["science"] == 1


def test_only_improved_tiles_are_worked(cfg):
    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=3, improved=("farm",))
    for _ in range(3):
        person(s, city, {"food": 3, "gold": 3})
    citizens.assign(s, cfg, EU)
    people = citizens.of_city(s, city.id)
    working = [c for c in people if c.tile is not None]
    assert len(working) == 1 and s.tiles[working[0].tile].improvement == "farm"
    assert all(c.seats for c in people if c.tile is None)  # the rest fill free council seats
    with pytest.raises(CommandError, match="no improvement"):
        apply_command(
            s, cfg, SetCitizenJob(player=EU, citizen=people[0].id, job=f"tile:{east(city.tile, 2)}")
        )


def test_children_grow_up_faster_with_more_food(cfg):
    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=2)
    slow, fast = (
        person(s, city, {"food": 6}, adult=False),
        person(s, city, {"food": 6}, adult=False),
    )
    citizens.grow(s, cfg, city, surplus_food=0)
    assert slow.growth == cfg.t("citizens.growing_up.base")
    fast.growth = 0
    citizens.grow(s, cfg, city, surplus_food=5)
    g = cfg.t("citizens.growing_up")
    assert fast.growth == g["base"] + 5 * g["per_food"] > g["base"]
    assert citizens.turns_to_grow(cfg, fast, 5) < citizens.turns_to_grow(cfg, slow, 0)
    with pytest.raises(CommandError, match="grown up"):
        apply_command(s, cfg, SetCitizenJob(player=EU, citizen=slow.id, job="council"))


def test_birth_brings_a_child_with_odds(cfg):
    state = new_game(cfg, seed=2)
    city = next(c for c in state.cities if c.owner == "europe" and c.is_capital)
    city.food_store = economy.growth_threshold(cfg, city.pop) + 50
    events, _ = economy.process_city(state, cfg, city, state.players["europe"])
    born = [e for e in events if e["kind"] == "citizen_born"]
    assert born and born[0]["stats"] == {} and born[0]["odds"]  # stats come at growing up (M21)
    child = state.citizens[str(born[0]["citizen"])]
    assert not child.adult and len(citizens.of_city(state, city.id)) == city.pop


def test_citizens_round_trip(cfg):
    state = new_game(cfg, seed=3)
    assert state.citizens
    assert state_to_json(state_from_json(state_to_json(state))) == state_to_json(state)


def test_healing_is_20_at_home_and_10_outside(cfg):
    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=1)
    home = create_unit(s, cfg, "infantry", EU, east(city.tile))
    away = create_unit(s, cfg, "infantry", EU, east(city.tile, 6))  # outside its territory
    home.hp = away.hp = 50
    reset_units(s, cfg)
    assert home.hp == 70 and away.hp == 60


def test_city_alert_when_an_enemy_is_in_range(cfg):
    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=1)
    create_unit(s, cfg, "infantry", EU, east(city.tile))  # sees around the city
    assert not any(p["kind"] == "city_can_attack" for p in pending_decisions(s, cfg, EU))
    create_unit(s, cfg, "alien_warrior", ALIENS, east(city.tile, 2))
    alerts = [p for p in pending_decisions(s, cfg, EU) if p["kind"] == "city_can_attack"]
    assert alerts == [{"kind": "city_can_attack", "city": city.id}]
    apply_command(s, cfg, HoldFire(player=EU, city=city.id))
    assert not any(p["kind"] == "city_can_attack" for p in pending_decisions(s, cfg, EU))


def test_tech_tree_branches_two_four_eight_sixteen(cfg):
    tree = {t: s for t, s in cfg.techs.items() if s["tree"] != "alien" and not s["known_at_start"]}
    assert all(len(s["prereqs"]) <= 1 for s in tree.values())
    by_level = {}
    for t, s in tree.items():
        by_level.setdefault(s["tier"], []).append(t)
    assert [len(by_level[k]) for k in (1, 2, 3, 4)] == [2, 4, 8, 16]
    children = {}
    for t, s in tree.items():
        for p in s["prereqs"]:
            children.setdefault(p, []).append(t)
    assert max(len(v) for v in children.values()) == 2
    player = new_game(cfg, seed=1).players["europe"]
    assert sorted(tech.available(cfg, player)) == sorted(by_level[1])


def test_whole_game_turns_with_citizens(cfg):
    state = new_game(cfg, seed=6)
    for _ in range(3):
        advance_turn(state, cfg)
    for city in state.cities:
        if city.owner in state.players:
            assert len(citizens.of_city(state, city.id)) == city.pop


def test_half_stats_are_not_rounded(cfg):
    # +3 production on a tile is +1.5: the city gets +1 one turn and +2 the next
    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=1)
    c = person(s, city, {"production": 3, "gold": 3})
    c.job = f"tile:{east(city.tile)}"
    citizens.assign(s, cfg, EU)
    cy = economy.city_yields(s, cfg, city)
    assert cy.fraction["production"] == 50
    player = s.players[EU]
    gold = []
    for _ in range(2):
        before = player.gold
        economy.process_city(s, cfg, city, player)
        gold.append(player.gold - before)
    assert gold[1] - gold[0] == 1  # the two halves made a whole


# -- promotions and alien raids (designer, 2026-11-14) -------------------------------------------


def test_promotion_thresholds_double_then_grow_by_half(cfg):
    from beacon import promotions

    assert promotions.thresholds(cfg, 100) == [2, 4, 8, 16, 24, 36, 54, 81]
    assert promotions.next_threshold(cfg, 16) == 24


def test_combat_earns_experience_and_promotions_add_strength(cfg):
    from beacon import combat, promotions
    from beacon.commands import Attack, PromoteUnit

    s = arena(cfg)
    a = at(4, 4)
    inf = create_unit(s, cfg, "infantry", EU, a)
    alien = create_unit(s, cfg, "alien_hatchling", ALIENS, east(a))
    alien.hp = 100
    apply_command(s, cfg, Attack(player=EU, unit=inf.id, target=east(a)))
    assert inf.xp == 1 and promotions.due(cfg, inf) == 0
    inf.xp = 2  # a second combat, attacking or attacked
    assert promotions.due(cfg, inf) == 1
    assert {"kind": "unit_promotion", "unit": inf.id} in pending_decisions(s, cfg, EU)
    before = combat.unit_strength(s, cfg, inf, ranged=False, defending=False).total
    apply_command(s, cfg, PromoteUnit(player=EU, unit=inf.id, promotion="attack_10"))
    after = combat.unit_strength(s, cfg, inf, ranged=False, defending=False).total
    assert after == before * 110 // 100
    with pytest.raises(CommandError, match="no promotion due"):
        apply_command(s, cfg, PromoteUnit(player=EU, unit=inf.id, promotion="defence_10"))


def test_aliens_leave_player_cities_alone_for_25_turns(cfg):
    from beacon.runner import play

    _, events, _ = play(cfg, seed=2, turns=40)
    alien_types = {t for t, u in cfg.units.items() if u["faction"] == "alien"}
    hits = [
        e["turn"]
        for e in events
        if e["kind"] == "attack"
        and e["attacker_type"] in alien_types
        and e["defender_kind"] == "city"
    ]
    strikes = [e["turn"] for e in events if e["kind"] == "mothership_strike"]
    grace = cfg.alien("director")["city_grace_turns"]
    assert grace == 25
    assert all(t >= grace for t in hits + strikes)
    early_hunts = [
        e
        for e in events
        if e["kind"] == "attack" and e["attacker_type"] in alien_types and e["turn"] < grace
    ]
    assert early_hunts  # but hunters pick off units in the field from early on


# -- turrets, gold upgrades, merging by moving, cancelling jobs (designer, 2026-11-14) -----------


def test_turret_fires_and_must_fall_before_pillage(cfg):
    from beacon import aliens, turrets
    from beacon.commands import BuildImprovement, UpgradeTurret

    s = arena(cfg)
    farm = at(6, 6)
    s.tiles[farm].improvement, s.tiles[farm].built_by = "farm", EU
    eng = create_unit(s, cfg, "engineers", EU, farm)
    apply_command(s, cfg, BuildImprovement(player=EU, unit=eng.id, improvement="turret"))
    for _ in range(cfg.improvements["turret"]["turns"]):
        from beacon.improvements import progress_jobs

        progress_jobs(s, cfg, EU)
    assert s.tiles[farm].turret == 1 and s.tiles[farm].turret_hp == turrets.max_hp(cfg, 1)
    raider = create_unit(s, cfg, "alien_pillager", ALIENS, east(farm))
    events = turrets.fire(s, cfg)
    assert events and events[0]["defender"] == raider.id and raider.hp < 100
    raider.tile = farm
    assert aliens.pillage(s, cfg, raider) == []  # the turret still stands
    s.players[EU].gold = 1000
    apply_command(s, cfg, UpgradeTurret(player=EU, tile=farm))
    assert s.tiles[farm].turret == 2 and s.players[EU].gold == 1000 - 50
    s.tiles[farm].turret, s.tiles[farm].turret_hp = 0, 0
    assert aliens.pillage(s, cfg, raider)[0]["lost"] == "farm"


def test_city_guns_upgrade_with_gold_not_experience(cfg):
    from beacon import combat, promotions
    from beacon.commands import UpgradeDefence

    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=1)
    gun = create_unit(s, cfg, "city_artillery", EU, city.tile)
    promotions.gain(s, cfg, gun)
    assert gun.xp == 0
    s.players[EU].gold = 100
    before = combat.unit_strength(s, cfg, gun, ranged=True, defending=False).total
    apply_command(s, cfg, UpgradeDefence(player=EU, unit=gun.id))
    assert s.players[EU].gold == 40
    assert combat.unit_strength(s, cfg, gun, ranged=True, defending=False).total > before


def test_moving_onto_a_twin_merges_and_jobs_can_be_cancelled(cfg_legacy):
    cfg = cfg_legacy  # stacking and rations are off by default (SPEC_M22)
    from beacon.commands import BuildImprovement, CancelJob, MoveUnit

    s = arena(cfg)
    a = at(4, 4)
    one = create_unit(s, cfg, "infantry", EU, a)
    two = create_unit(s, cfg, "infantry", EU, east(a))
    apply_command(s, cfg, MoveUnit(player=EU, unit=one.id, target=east(a)))
    assert two.count == 2 and str(one.id) not in s.units
    eng = create_unit(s, cfg, "engineers", EU, at(8, 8))
    apply_command(s, cfg, BuildImprovement(player=EU, unit=eng.id, improvement="road"))
    apply_command(s, cfg, CancelJob(player=EU, unit=eng.id))
    assert eng.job is None and eng.order == "none"


def test_unlinked_roads_cost_gold_until_connected(cfg):
    from beacon.economy import road_upkeep
    from beacon.fog import touch_built

    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=1)
    far = [at(12, 2), east(at(12, 2))]
    for t in far:
        s.tiles[t].route, s.tiles[t].built_by = "road", EU
    touch_built(s)
    assert road_upkeep(s, cfg, EU) == 2 * cfg.t("economy.unlinked_road_upkeep")
    near = east(city.tile)
    s.tiles[near].route, s.tiles[near].built_by = "road", EU
    touch_built(s)
    assert road_upkeep(s, cfg, EU) == 2  # the road beside the city is joined to it: free


def test_assign_best_citizen_and_no_fortify_after_attack(cfg):
    from beacon.commands import AssignBestCitizen, Attack, Fortify

    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=2)
    mine = east(city.tile)
    weak = person(s, city, {"food": 3, "gold": 3})
    strong = person(s, city, {"production": 3, "science": 3})
    strong.job = "council"  # the weaker one works the mine at first
    citizens.assign(s, cfg, EU)
    assert weak.tile == mine
    apply_command(s, cfg, AssignBestCitizen(player=EU, city=city.id, tile=mine))
    assert strong.tile == mine and strong.job == f"tile:{mine}"
    assert weak.tile is None
    a = at(10, 3)
    inf = create_unit(s, cfg, "infantry", EU, a)
    create_unit(s, cfg, "alien_hatchling", ALIENS, east(a))
    apply_command(s, cfg, Attack(player=EU, unit=inf.id, target=east(a)))
    with pytest.raises(CommandError, match="attacked this turn"):
        apply_command(s, cfg, Fortify(player=EU, unit=inf.id))


# -- shuffled layout and contact (designer, 2026-11-14) ------------------------------------------


def test_layout_is_shuffled_by_seed(cfg):
    from beacon import mapgen

    a = mapgen.layout(cfg, 1, cfg.continent_ids())
    b = mapgen.layout(cfg, 2, cfg.continent_ids())
    assert a != b and a == mapgen.layout(cfg, 1, cfg.continent_ids())
    for boxes in (a, b):  # boxes fit the map; only their ocean margins may overlap (SPEC_M10)
        items = [mapgen._region(cfg, box) for box in boxes.values()]
        for i, (c0, c1, r0, r1) in enumerate(items):
            assert 0 <= c0 < c1 <= cfg.t("map.width") and 0 <= r0 < r1 <= cfg.t("map.height")
            for d0, d1, s0, s1 in items[i + 1 :]:
                assert c1 <= d0 or d1 <= c0 or r1 <= s0 or s1 <= r0


def test_contact_gates_diplomacy_and_is_made_by_sighting(cfg):
    from test_m3_units_combat import NA

    from beacon import config, contact
    from beacon.commands import ProposeDeal

    def no_radio(raw):  # sighting contact as built in M9; off while contact is by radio only
        raw["tuning"]["contact"]["radio_building"]["value"] = None

    cfg = config.load(overrides=no_radio)
    s = arena(cfg)
    s.players[EU].met, s.players[NA].met = [], []
    with pytest.raises(CommandError, match="not met"):
        apply_command(
            s, cfg, ProposeDeal(player=EU, to_player=NA, give={"gold": 10}, take={}, duration=0)
        )
    for t in range(s.width * 3):  # NA's land in sight of an EU unit
        s.tiles[t].continent = NA
    create_unit(s, cfg, "infantry", EU, at(2, 3))  # sees row 2
    events = contact.check(s, cfg)
    assert [e["kind"] for e in events] == ["contact_made"]
    assert contact.met(s, EU, NA) and contact.met(s, NA, EU)


# -- tech effects, support units, matchups, class promotions (designer, 2026-11-14) ---------------


def test_every_tech_does_something(cfg):
    unlocks = {
        s.get("tech")
        for table in (cfg.buildings, cfg.units, cfg.improvements)
        for s in table.values()
    }
    special = {
        cfg.t("trade.alliance_tech"),
        cfg.t("endgame.barrage_tech"),
        *cfg.t("endgame.radar_techs"),
        *cfg.alien("recruits")["rarity_techs"],
    }
    for t, spec in cfg.techs.items():
        if spec["tree"] == "alien" or spec["known_at_start"]:
            continue
        assert t in unlocks or t in special or spec.get("effects"), t


def test_tech_effects_change_the_rules(cfg):
    from beacon import combat

    s = arena(cfg)
    city = city_with_tiles(cfg, s, pop=1)
    player = s.players[EU]
    base_cost = economy.item_cost(cfg, "unit:infantry", player)
    gold = economy.city_yields(s, cfg, city).totals["gold"]
    player.techs += ["mass_production", "carbon_markets", "orbital_defence_grid"]
    assert economy.item_cost(cfg, "unit:infantry", player) == base_cost * 85 // 100
    assert economy.city_yields(s, cfg, city).totals["gold"] == gold + 2
    assert any(x["source"] == "defence grid" for x in combat.city_strength(s, cfg, city).lines)


def test_medics_heal_and_repair_crews_rebuild(cfg):
    from beacon import aliens
    from beacon.commands import BuildImprovement
    from beacon.improvements import progress_jobs

    s = arena(cfg)
    a = at(5, 5)
    medic = create_unit(s, cfg, "medical_team", EU, a)
    hurt = create_unit(s, cfg, "infantry", EU, east(a))
    hurt.hp, hurt.acted = 50, True  # it fought: no ordinary healing
    reset_units(s, cfg)
    assert hurt.hp == 50 + cfg.units["medical_team"]["heal_adjacent"]
    farm = at(9, 5)
    s.tiles[farm].improvement, s.tiles[farm].built_by = "farm", EU
    raider = create_unit(s, cfg, "alien_pillager", ALIENS, farm)
    aliens.pillage(s, cfg, raider)
    assert s.tiles[farm].improvement is None and s.tiles[farm].pillaged == "farm"
    del s.units[str(raider.id)]
    crew = create_unit(s, cfg, "nanorepair_crew", EU, farm)
    with pytest.raises(CommandError, match="only rebuild"):
        apply_command(s, cfg, BuildImprovement(player=EU, unit=crew.id, improvement="mine"))
    apply_command(s, cfg, BuildImprovement(player=EU, unit=crew.id, improvement="farm"))
    progress_jobs(s, cfg, EU)
    assert s.tiles[farm].improvement == "farm" and s.tiles[farm].pillaged is None
    assert medic.tile == a


def test_matchups_and_class_promotions(cfg):
    from beacon import combat, promotions

    s = arena(cfg)
    a = at(4, 4)
    at_team = create_unit(s, cfg, "anti_tank_team", EU, a)
    brute = create_unit(s, cfg, "alien_brute", ALIENS, east(a, 2))
    lines = combat.preview_attack(s, cfg, at_team, brute.tile)["attacker"]["lines"]
    assert {"source": "vs heavy", "kind": "pct", "value": 50} in lines
    inf = create_unit(s, cfg, "infantry", EU, at(10, 8))
    s.tiles[inf.tile].feature = "forest"
    dfn = combat.unit_strength(s, cfg, inf, ranged=False, defending=True)
    assert any(x["source"] == "rough ground" for x in dfn.lines)
    assert "dig_in" in promotions.options(cfg, inf) and "blitz" not in promotions.options(cfg, inf)
    tank = create_unit(s, cfg, "tank", EU, at(12, 2))
    tank.promotions = ["blitz"]
    reset_units(s, cfg)
    assert tank.moves_left == (cfg.units["tank"]["moves"] + 1) * cfg.t("movement.scale")
