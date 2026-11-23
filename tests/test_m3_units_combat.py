"""M3: movement, one unit per hex, stacking, combat, liberation, replay and batch determinism.

Most tests use a small synthetic arena (flat grassland) so every modifier is controlled.
"""

from __future__ import annotations

import pytest

from beacon import combat, config, fog, hexgrid
from beacon.actions import apply_command, legal_commands
from beacon.commands import (
    Attack,
    CityAttack,
    CommandError,
    MergeUnits,
    MoveUnit,
    SplitUnit,
)
from beacon.game import new_players
from beacon.runner import play, replay
from beacon.state import (
    ACTIVE,
    ALIENS,
    DORMANT,
    OVERRUN,
    City,
    GameState,
    Tile,
    state_digest,
    state_from_json,
    state_to_json,
)
from beacon.units import create_unit

W, H = 14, 10
EU, NA = "europe", "north_america"


def arena(cfg) -> GameState:
    tiles = [Tile(terrain="grassland", continent=EU) for _ in range(W * H)]
    players = new_players(cfg, [EU, NA])
    players[EU].met, players[NA].met = [NA], [EU]  # the arena's two players have met
    return GameState(
        seed=5,
        config_digest=cfg.digest,
        width=W,
        height=H,
        tiles=tiles,
        players=players,
    )


def at(col: int, row: int) -> int:
    return hexgrid.index(col, row, W)


def east(tile: int, steps: int = 1) -> int:
    col, row = hexgrid.col_row(tile, W)
    return hexgrid.index(col + steps, row, W)


def add_city(state, cfg, tile, status, owner, pop=4, continent=EU) -> City:
    city = City(
        id=len(state.cities),
        name=f"City{len(state.cities)}",
        continent=continent,
        tile=tile,
        status=status,
        owner=owner,
        pop=pop,
    )
    from beacon.cities import max_hp

    city.hp = max_hp(cfg, city)
    state.cities.append(city)
    state.tiles[tile].city = city.id
    return city


@pytest.fixture(scope="module")
def calm_cfg():
    """Real data with combat variance switched off, so previews equal results exactly."""

    def zero(raw):
        raw["tuning"]["combat"]["variance_pct"]["value"] = 0

    return config.load(overrides=zero)


# -- movement --------------------------------------------------------------------------------


def test_every_land_hex_costs_one_move_roads_and_rail_less(cfg):
    s = arena(cfg)
    a = at(2, 4)
    inf = create_unit(s, cfg, "infantry", EU, a)
    apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(a, 5)))
    assert inf.tile == east(a, 2) and inf.moves_left == 0  # 2 moves on flat

    s = arena(cfg)
    inf = create_unit(s, cfg, "infantry", EU, a)
    s.tiles[east(a)].elevation = "hills"
    s.tiles[east(a, 2)].elevation = "hills"
    s.tiles[east(a, 3)].feature = "forest"
    apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(a, 3)))
    assert inf.tile == east(a, 2)  # one move per hex on hills and forest too (designer 2026-11-14)

    s = arena(cfg)
    for k in range(0, 9):
        s.tiles[east(at(1, 4), k)].route = "road"
    inf = create_unit(s, cfg, "infantry", EU, at(1, 4))
    apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(at(1, 4), 8)))
    assert inf.tile == east(at(1, 4), 6)  # road: a third of a move per step

    s = arena(cfg)
    for k in range(0, 12):
        s.tiles[east(at(0, 4), k)].route = "railway"
    inf = create_unit(s, cfg, "infantry", EU, at(0, 4))
    apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(at(0, 4), 11)))
    assert inf.tile == east(at(0, 4), 11)


def test_mountains_and_water_block_land_units(cfg):
    s = arena(cfg)
    a = at(5, 4)
    inf = create_unit(s, cfg, "infantry", EU, a)
    s.tiles[east(a)].elevation = "mountain"
    with pytest.raises(CommandError):
        apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(a)))
    s.tiles[east(a, -1)].terrain = "coast"
    with pytest.raises(CommandError):
        apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(a, -1)))


def test_one_military_unit_per_hex_but_civilians_share(cfg):
    s = arena(cfg)
    a = at(4, 4)
    first = create_unit(s, cfg, "infantry", EU, a)
    second = create_unit(s, cfg, "artillery", EU, east(a))
    with pytest.raises(CommandError):
        apply_command(s, cfg, MoveUnit(player=EU, unit=second.id, target=a))
    eng = create_unit(s, cfg, "engineers", EU, east(a, 2))
    apply_command(s, cfg, MoveUnit(player=EU, unit=eng.id, target=a))
    assert eng.tile == a == first.tile
    # friendly units can be passed through
    runner = create_unit(s, cfg, "recon_team", EU, east(a, -1))
    apply_command(s, cfg, MoveUnit(player=EU, unit=runner.id, target=east(a, 2)))
    assert runner.tile == east(a, 2)


def test_unseen_enemy_interrupts_a_move(cfg):
    s = arena(cfg)
    a = at(2, 4)
    inf = create_unit(s, cfg, "infantry", EU, a)
    alien = create_unit(s, cfg, "alien_warrior", ALIENS, east(a, 2))
    assert alien.tile not in fog.visible_tiles(s, cfg, EU)
    events = apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(a, 3)))
    assert inf.tile == east(a)
    assert any(e["kind"] == "move_interrupted" for e in events)


# -- stacking --------------------------------------------------------------------------------


def test_merge_doubles_strength_and_pools_hp(cfg_legacy):
    cfg = cfg_legacy  # stacking and rations are off by default (SPEC_M22)
    s = arena(cfg)
    a = at(5, 5)
    one = create_unit(s, cfg, "infantry", EU, a)
    single = combat.unit_strength(s, cfg, one, ranged=False, defending=True).total
    two = create_unit(s, cfg, "infantry", EU, east(a))
    two.hp = 70
    apply_command(s, cfg, MergeUnits(player=EU, unit=two.id, into=one.id))
    assert str(two.id) not in s.units
    assert one.count == 2 and one.hp == 170
    full = cfg.t("combat.unit_max_hp")
    one.hp = 2 * full
    assert combat.unit_strength(s, cfg, one, ranged=False, defending=True).total == 2 * single


def test_merge_rules(cfg_legacy):
    cfg = cfg_legacy  # stacking and rations are off by default (SPEC_M22)
    s = arena(cfg)
    a = at(5, 5)
    inf = create_unit(s, cfg, "infantry", EU, a)
    art = create_unit(s, cfg, "artillery", EU, east(a))
    with pytest.raises(CommandError, match="same type"):
        apply_command(s, cfg, MergeUnits(player=EU, unit=art.id, into=inf.id))
    other = create_unit(s, cfg, "infantry", NA, east(a, -1))
    with pytest.raises(CommandError):
        apply_command(s, cfg, MergeUnits(player=EU, unit=inf.id, into=other.id))
    b = create_unit(s, cfg, "infantry", EU, east(a, 2))
    c = create_unit(s, cfg, "infantry", EU, at(5, 6))
    apply_command(s, cfg, MergeUnits(player=EU, unit=c.id, into=inf.id))
    with pytest.raises(CommandError, match="at most 2"):
        apply_command(s, cfg, MergeUnits(player=EU, unit=b.id, into=inf.id))
    e1 = create_unit(s, cfg, "engineers", EU, at(9, 2))
    e2 = create_unit(s, cfg, "engineers", EU, at(10, 2))
    with pytest.raises(CommandError, match="civilians"):
        apply_command(s, cfg, MergeUnits(player=EU, unit=e1.id, into=e2.id))


def test_stack_loses_a_member_below_half_and_dies_at_zero(cfg):
    s = arena(cfg)
    stack = create_unit(s, cfg, "infantry", EU, at(3, 3))
    stack.count, stack.hp = 2, 200
    assert combat.damage_unit(s, cfg, stack, 100, ALIENS) == []
    assert stack.count == 2  # lost exactly half, not more
    events = combat.damage_unit(s, cfg, stack, 1, ALIENS)
    assert stack.count == 1 and stack.hp == 99
    assert events[0]["kind"] == "stack_member_lost"
    assert s.players[EU].credits["units_lost"] == 1
    combat.damage_unit(s, cfg, stack, 99, ALIENS)
    assert str(stack.id) not in s.units


def test_split_full_health_unit_moves_rest_stays(cfg):
    s = arena(cfg)
    a = at(6, 4)
    stack = create_unit(s, cfg, "infantry", EU, a)
    stack.count, stack.hp = 2, 150
    events = apply_command(s, cfg, SplitUnit(player=EU, unit=stack.id, target=east(a)))
    mover = s.unit(next(e["new_unit"] for e in events if e["kind"] == "unit_split"))
    assert mover.tile == east(a) and mover.hp == 100 and mover.count == 1
    assert stack.tile == a and stack.hp == 50 and stack.count == 1
    stack.count, stack.hp = 2, 100
    with pytest.raises(CommandError, match="too little HP"):
        apply_command(s, cfg, SplitUnit(player=EU, unit=stack.id, target=east(a, -1)))


# -- combat ----------------------------------------------------------------------------------


def test_preview_matches_result_at_zero_variance(calm_cfg):
    cfg = calm_cfg
    s = arena(cfg)
    a = at(4, 4)
    inf = create_unit(s, cfg, "infantry", EU, a)
    alien = create_unit(s, cfg, "alien_warrior", ALIENS, east(a))
    p = combat.preview_attack(s, cfg, inf, east(a))
    assert p["legal"] and p["kind"] == "melee"
    apply_command(s, cfg, Attack(player=EU, unit=inf.id, target=east(a)))
    assert inf.hp == 100 - p["damage_to_attacker"]["expected"]
    assert alien.hp == 100 - p["damage_to_defender"]["expected"]
    assert p["damage_to_defender"]["min"] == p["damage_to_defender"]["max"]


def test_equal_strength_deals_base_damage(calm_cfg):
    cfg = calm_cfg
    assert combat.raw_damage(cfg, 3000, 3000) == cfg.t("combat.base_damage")
    assert combat.raw_damage(cfg, 1500, 3000) > combat.raw_damage(cfg, 3000, 1500)


def test_ranged_attack_takes_no_retaliation(cfg):
    s = arena(cfg)
    a = at(3, 4)
    art = create_unit(s, cfg, "artillery", EU, a)
    create_unit(s, cfg, "recon_team", EU, east(a))  # spotter: artillery sees only 1 hex
    alien = create_unit(s, cfg, "alien_warrior", ALIENS, east(a, 2))
    p = combat.preview_attack(s, cfg, art, east(a, 2))
    assert p["kind"] == "ranged" and p["damage_to_attacker"]["expected"] == 0
    apply_command(s, cfg, Attack(player=EU, unit=art.id, target=east(a, 2)))
    assert art.hp == 100 and alien.hp < 100 and art.moves_left == 0


def test_ranged_needs_a_visible_target(cfg):
    s = arena(cfg)
    a = at(3, 4)
    art = create_unit(s, cfg, "artillery", EU, a)
    create_unit(s, cfg, "alien_warrior", ALIENS, east(a, 2))
    with pytest.raises(CommandError, match="not visible"):
        apply_command(s, cfg, Attack(player=EU, unit=art.id, target=east(a, 2)))


def test_terrain_fortify_and_flanking_modifiers(cfg):
    s = arena(cfg)
    a = at(6, 5)
    target = east(a)
    alien = create_unit(s, cfg, "alien_warrior", ALIENS, target)
    flat = combat.unit_strength(s, cfg, alien, ranged=False, defending=True).total
    s.tiles[target].elevation, s.tiles[target].feature = "hills", "forest"
    alien.fortified = True
    lines = combat.unit_strength(s, cfg, alien, ranged=False, defending=True)
    sources = {line["source"] for line in lines.lines}
    assert {"elevation:hills", "feature:forest", "fortified"} <= sources
    assert lines.total == flat * (100 + 25 + 25 + cfg.t("combat.fortify_pct")) // 100

    inf = create_unit(s, cfg, "infantry", EU, a)
    alone = combat.unit_strength(s, cfg, inf, ranged=False, defending=False, target=target).total
    flank_spot = next(n for n in hexgrid.neighbours(target, W, H) if n != a and not s.units_at(n))
    create_unit(s, cfg, "infantry", NA, flank_spot)  # an ally from another continent flanks too
    flanked = combat.unit_strength(s, cfg, inf, ranged=False, defending=False, target=target)
    assert flanked.total == alone * (100 + cfg.t("combat.flanking_pct")) // 100


def test_players_never_attack_each_other(cfg):
    s = arena(cfg)
    a = at(5, 5)
    inf = create_unit(s, cfg, "infantry", EU, a)
    create_unit(s, cfg, "infantry", NA, east(a))
    with pytest.raises(CommandError, match="nothing hostile"):
        apply_command(s, cfg, Attack(player=EU, unit=inf.id, target=east(a)))


def test_melee_kill_advances_and_credits(calm_cfg):
    cfg = calm_cfg
    s = arena(cfg)
    a = at(4, 4)
    inf = create_unit(s, cfg, "infantry", NA, a)
    alien = create_unit(s, cfg, "alien_drone", ALIENS, east(a))
    alien.hp = 5
    apply_command(s, cfg, Attack(player=NA, unit=inf.id, target=east(a)))
    assert str(alien.id) not in s.units
    assert inf.tile == east(a)
    assert s.players[NA].credits["kills"] == 1


# -- cities ----------------------------------------------------------------------------------


def test_liberation_by_melee_and_not_by_ranged(calm_cfg):
    cfg = calm_cfg
    s = arena(cfg)
    a = at(4, 4)
    city_tile = east(a)
    city = add_city(s, cfg, city_tile, OVERRUN, ALIENS, pop=4)
    guard = create_unit(s, cfg, "alien_hive_guard", ALIENS, city_tile)

    inf = create_unit(s, cfg, "infantry", NA, a)  # a North American unit liberating in Europe
    art = create_unit(s, cfg, "artillery", NA, at(3, 3))  # the infantry spots for it
    city.hp = 5
    apply_command(s, cfg, Attack(player=NA, unit=art.id, target=city_tile))
    assert city.hp == 1 and city.status == OVERRUN  # ranged cannot capture

    events = apply_command(s, cfg, Attack(player=NA, unit=inf.id, target=city_tile))
    kinds = [e["kind"] for e in events]
    assert "city_liberated" in kinds
    assert city.status == ACTIVE and city.owner == EU
    assert city.pop == 4 - 4 * cfg.t("cities.liberation_pop_loss_pct") // 100
    assert str(guard.id) not in s.units and inf.tile == city_tile
    assert s.players[NA].credits["cities_liberated"] == 1
    assert "cities_liberated" not in s.players[EU].credits
    assert city.damage_by[NA] > 0


def test_reclaim_dormant_and_refound_empty(cfg):
    s = arena(cfg)
    a = at(3, 4)
    dormant = add_city(s, cfg, east(a), DORMANT, None, pop=2)
    inf = create_unit(s, cfg, "infantry", NA, a)
    apply_command(s, cfg, MoveUnit(player=NA, unit=inf.id, target=east(a)))
    assert dormant.status == ACTIVE and dormant.owner == EU
    assert s.players[NA].credits["cities_reclaimed"] == 1


def test_city_bombards_once_per_turn(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(5, 5), ACTIVE, EU)
    target = east(at(5, 5))
    alien = create_unit(s, cfg, "alien_warrior", ALIENS, target)
    apply_command(s, cfg, CityAttack(player=EU, city=city.id, target=target))
    assert alien.hp < 100 and city.bombarded
    with pytest.raises(CommandError, match="already fired"):
        apply_command(s, cfg, CityAttack(player=EU, city=city.id, target=target))


# -- whole games -----------------------------------------------------------------------------


def test_legal_commands_are_accepted(cfg):
    from beacon.game import new_game

    base = new_game(cfg, seed=6)
    pid = "south_america"
    cmds = legal_commands(base, cfg, pid)
    kinds = {c.kind for c in cmds}
    assert {"set_research", "set_production", "move_unit", "fortify", "skip_unit"} <= kinds
    text = state_to_json(base)
    for cmd in cmds[::7]:
        apply_command(state_from_json(text), cfg, cmd)


def test_bot_games_are_deterministic_and_replay_from_the_log(cfg):
    turns = 15
    state, _, log = play(cfg, seed=3, turns=turns)
    again, _, _ = play(cfg, seed=3, turns=turns)
    assert state_digest(state) == state_digest(again)
    assert state_digest(replay(cfg, 3, turns, log)) == state_digest(state)
    other, _, _ = play(cfg, seed=4, turns=turns)
    assert state_digest(other) != state_digest(state)


def test_bots_recover_cities(cfg):
    # Every lost city starts alien-held (designer 2026-11-14), so recovering one means a siege;
    # the simple test bot manages it on more than one continent within 100 turns.
    state, events, _ = play(cfg, seed=2, turns=100)
    liberators = {e["by"] for e in events if e["kind"] == "city_liberated"}
    assert len(liberators) >= 2
    for pid in liberators:
        assert state.players[pid].credits.get("cities_liberated", 0) >= 1
