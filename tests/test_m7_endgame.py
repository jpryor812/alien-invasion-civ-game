"""M7: mothership strikes, reinforcement stop, the barrage, radar, espionage, endings, MVP."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, NA, add_city, arena, at, east

from beacon import aliens, combat, config, endgame, mvp, tech
from beacon.actions import apply_command
from beacon.commands import (
    ChooseEspionageTech,
    CommandError,
    FundProject,
    SetProduction,
    StartBarrage,
    StartEspionage,
)
from beacon.economy import process_city
from beacon.liberation import liberation_shares, update_fallen
from beacon.runner import play
from beacon.state import ACTIVE, ALIENS, OVERRUN
from beacon.units import create_unit


def with_barrage_tech(s, cfg, *pids):
    for pid in pids:
        s.players[pid].techs.append(cfg.t("endgame.barrage_tech"))


def overrides(**paths):
    def apply(raw):
        for dotted, value in paths.items():
            node = raw
            *head, last = dotted.split(".")
            for part in head:
                node = node[part]
            node[last] = value

    return config.load(overrides=apply)


# -- mothership ------------------------------------------------------------------------------


def test_strikes_damage_and_favour_the_barrage_host():
    cfg = overrides(
        **{
            "tuning.endgame.mothership.strike_permille": 1000,
            "tuning.endgame.mothership.host_weight": 100000,
        }
    )
    s = arena(cfg)
    host = add_city(s, cfg, at(3, 3), ACTIVE, EU, pop=8)
    host.connected = True
    add_city(s, cfg, at(10, 6), ACTIVE, EU, pop=8)
    with_barrage_tech(s, cfg, EU)
    apply_command(s, cfg, StartBarrage(player=EU, city=host.id))
    events = endgame.strikes(s, cfg)
    assert events[0]["city"] == host.id
    assert host.pop == 8 - 8 * cfg.t("endgame.mothership.strike_pop_pct") // 100
    from beacon.cities import max_hp

    assert host.hp == max_hp(cfg, host) * cfg.t("endgame.mothership.strike_hp_pct") // 100
    s.aliens.mothership_alive = False
    assert endgame.strikes(s, cfg) == []


def test_researching_the_barrage_stops_reinforcements(cfg):
    s = arena(cfg)
    add_city(s, cfg, at(6, 5), OVERRUN, ALIENS)
    s.aliens.reinforcement_store = 10_000
    with_barrage_tech(s, cfg, NA)
    events = endgame.end_of_turn(s, cfg)
    assert any(e["kind"] == "reinforcements_stopped" for e in events)
    assert aliens.reinforcements(s, cfg) == [] and aliens.surge(s, cfg) == []


# -- the barrage -----------------------------------------------------------------------------


def test_barrage_needs_tech_cost_and_time_and_pauses_without_its_host(cfg):
    s = arena(cfg)
    host = add_city(s, cfg, at(4, 4), ACTIVE, EU, pop=6)
    host.connected = True
    helper = add_city(s, cfg, at(10, 6), ACTIVE, NA, pop=6)
    helper.connected = True
    with pytest.raises(CommandError, match="needs"):
        apply_command(s, cfg, StartBarrage(player=EU, city=host.id))
    with_barrage_tech(s, cfg, EU)
    apply_command(s, cfg, StartBarrage(player=EU, city=host.id))
    with pytest.raises(CommandError, match="already"):
        apply_command(s, cfg, StartBarrage(player=EU, city=host.id))
    b = endgame.barrage(s)
    # any player can build it: North America has no tech but sends production
    apply_command(s, cfg, SetProduction(player=NA, city=helper.id, items=("project:barrage",)))
    process_city(s, cfg, helper, s.players[NA])
    assert b.contributions[NA] > 0 and s.players[NA].credits["barrage"] == b.contributions[NA]
    s.players[EU].gold = 100_000
    apply_command(s, cfg, FundProject(player=EU, project=b.id, gold=100_000))
    assert b.progress == b.cost  # capped at the cost
    assert s.players[EU].gold > 0  # paid only for what it could take
    assert endgame.end_of_turn(s, cfg) == [] or s.aliens.mothership_alive  # too early to fire
    s.turn = b.started_turn + cfg.t("endgame.barrage.min_turns")
    host.status, host.owner = OVERRUN, ALIENS
    endgame.end_of_turn(s, cfg)
    assert s.aliens.mothership_alive  # paused: host lost
    host.status, host.owner = ACTIVE, EU
    events = endgame.end_of_turn(s, cfg)
    assert any(e["kind"] == "barrage_fired" for e in events)
    assert not s.aliens.mothership_alive and s.aliens.reinforcements_stopped


def test_director_targets_the_barrage_host(cfg):
    s = arena(cfg)
    s.turn = cfg.alien("director.grace_turns")
    plain = add_city(s, cfg, at(3, 3), ACTIVE, EU, pop=4)
    host = add_city(s, cfg, at(10, 3), ACTIVE, EU, pop=4)
    host.connected = True
    brute = create_unit(s, cfg, "alien_brute", ALIENS, at(6, 3))
    d = aliens.Director(s, cfg)
    assert d.siege_target(brute) in (plain.tile, host.tile)
    with_barrage_tech(s, cfg, EU)
    apply_command(s, cfg, StartBarrage(player=EU, city=host.id))
    assert aliens.Director(s, cfg).siege_target(brute) == host.tile


# -- radar and alien tree ----------------------------------------------------------------------


def test_radar_reveals_alien_cities(cfg):
    s = arena(cfg)
    hidden = add_city(s, cfg, at(12, 8), OVERRUN, ALIENS)
    endgame.radar(s, cfg)
    assert str(hidden.id) not in s.players[EU].known_cities
    s.players[EU].techs.append(cfg.t("endgame.radar_techs")[0])
    endgame.radar(s, cfg)
    assert str(hidden.id) in s.players[EU].known_cities


def test_alien_tree_is_not_researchable(cfg):
    s = arena(cfg)
    s.players[EU].techs = sorted(cfg.techs)  # everything
    s.players[EU].techs = [t for t in s.players[EU].techs if cfg.techs[t]["tree"] != "alien"]
    assert tech.available(cfg, s.players[EU]) == []


# -- espionage -----------------------------------------------------------------------------------


def test_solo_and_shared_espionage(cfg):
    s = arena(cfg)
    cost = cfg.t("endgame.espionage.cost")
    s.players[EU].gold = s.players[NA].gold = cost * 2
    apply_command(s, cfg, StartEspionage(player=EU, mode="solo"))
    solo = endgame.open_operation(s, EU)
    with pytest.raises(CommandError, match="solo"):
        apply_command(s, cfg, FundProject(player=NA, project=solo.id, gold=10))
    apply_command(s, cfg, FundProject(player=EU, project=solo.id, gold=cost))
    events = endgame.end_of_turn(s, cfg)
    offered = next(e for e in events if e["kind"] == "espionage_complete")["offered"]
    assert len(offered) == cfg.t("endgame.espionage.offered")
    apply_command(s, cfg, ChooseEspionageTech(player=EU, project=solo.id, tech=offered[1]))
    assert offered[1] in s.players[EU].techs and offered[1] not in s.players[NA].techs

    apply_command(s, cfg, StartEspionage(player=EU, mode="shared"))
    shared = endgame.open_operation(s, EU)
    apply_command(s, cfg, FundProject(player=EU, project=shared.id, gold=cost // 4))
    apply_command(s, cfg, FundProject(player=NA, project=shared.id, gold=cost))
    endgame.end_of_turn(s, cfg)
    assert shared.chooser == NA  # the largest contributor chooses
    with pytest.raises(CommandError, match="largest"):
        apply_command(
            s, cfg, ChooseEspionageTech(player=EU, project=shared.id, tech=shared.offered[0])
        )
    first = shared.offered[0]
    s.turn = shared.choose_by
    endgame.end_of_turn(s, cfg)  # no choice made: the first offered is taken
    assert first in s.players[EU].techs and first in s.players[NA].techs


# -- endings -------------------------------------------------------------------------------------


def test_victory_needs_both_conditions_in_either_order(cfg):
    s = arena(cfg)
    add_city(s, cfg, at(3, 3), ACTIVE, EU)
    add_city(s, cfg, at(10, 3), ACTIVE, NA, continent=NA)
    last = add_city(s, cfg, at(6, 6), OVERRUN, ALIENS)
    s.aliens.mothership_alive = False
    assert endgame.check_outcome(s, cfg) == []
    last.status, last.owner = ACTIVE, EU
    assert endgame.check_outcome(s, cfg)[0]["outcome"] == "victory"

    s2 = arena(cfg)
    add_city(s2, cfg, at(3, 3), ACTIVE, EU)
    assert endgame.check_outcome(s2, cfg) == []  # no alien cities but the mothership lives
    s2.aliens.mothership_alive = False
    assert s2.outcome is None and endgame.check_outcome(s2, cfg)[0]["outcome"] == "victory"


def test_defeat_when_every_continent_falls(cfg):
    s = arena(cfg)
    add_city(s, cfg, at(6, 6), OVERRUN, ALIENS)
    update_fallen(s)
    assert endgame.check_outcome(s, cfg)[0]["outcome"] == "defeat"


def test_turn_limit_ends_the_run():
    cfg = overrides(**{"tuning.time.max_turns.value": 3})
    state, events, _ = play(cfg, seed=4, turns=10, driver="ai")
    assert state.outcome == "turn_limit" and state.turn == 3
    assert events[-1]["kind"] == "game_over"


# -- MVP -----------------------------------------------------------------------------------------


def test_liberation_credit_splits_by_damage(cfg):
    s = arena(cfg)
    shares = liberation_shares(s, {EU: 75, NA: 25, ALIENS: 50}, NA)
    assert shares == {EU: 75, NA: 25}
    assert liberation_shares(s, {}, EU) == {EU: 100}
    assert sum(liberation_shares(s, {EU: 1, NA: 2}, EU).values()) == 100


def test_mvp_lines_sum_to_the_total(calm_cfg):
    cfg = calm_cfg
    s = arena(cfg)
    city = add_city(s, cfg, at(5, 5), OVERRUN, ALIENS, pop=4)
    s.aliens.start_cities = 1
    art = create_unit(s, cfg, "artillery", EU, east(city.tile, -2))
    inf = create_unit(s, cfg, "infantry", NA, east(city.tile, -1))
    combat.attack(s, cfg, art, city.tile)
    city.hp = 1
    combat.attack(s, cfg, inf, city.tile)
    assert city.status == ACTIVE
    for pid in (EU, NA):
        sc = mvp.score(s, cfg, pid)
        assert sc["total"] == sum(line["points"] for line in sc["lines"])
    assert s.players[EU].credits["liberation_share"] > 0  # the artillery shared the credit
    ranking = mvp.ranking(s, cfg)
    assert [r["player"] for r in ranking] == sorted(
        [EU, NA], key=lambda p: (-mvp.score(s, cfg, p)["total"], p)
    )


@pytest.fixture(scope="module")
def calm_cfg():
    return overrides(**{"tuning.combat.variance_pct.value": 0})
