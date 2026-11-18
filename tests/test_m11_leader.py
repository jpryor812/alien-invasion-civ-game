"""M11: ocean bridges and the leader (docs/SPEC_M11.md, designer 2026-11-15)."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, add_city, arena, at, east
from test_m5_recruits import make as make_recruit
from test_m9_citizens import person

from beacon import citizens, combat, config, economy, improvements, leader, network, techfx
from beacon.actions import apply_command, legal_commands
from beacon.aliens import pillage
from beacon.commands import (
    BuildImprovement,
    ChooseLeaderBonus,
    CommandError,
    CreateLeader,
    MoveUnit,
    RaiseSkill,
    SetCitizenJob,
    SetWardrobe,
    StartFamily,
)
from beacon.config import DOMAINS
from beacon.game import new_game
from beacon.state import ACTIVE, ALIENS, state_from_json, state_to_json
from beacon.tiles import is_passable_land
from beacon.units import create_unit


def strait(cfg, cols=(6,)):
    """The arena split by a north-south channel of shallow water in the given columns."""
    s = arena(cfg)
    for i, t in enumerate(s.tiles):
        if i % s.width in cols:
            t.terrain = "coast"
    return s


def build_bridge(s, cfg, unit, target):
    apply_command(
        s,
        cfg,
        BuildImprovement(player=EU, unit=unit.id, improvement="sea_bridge", target=target),
    )
    for _ in range(unit.job.turns_left):
        improvements.progress_jobs(s, cfg, EU)


def test_a_sea_bridge_needs_robotics_and_goes_on_shallow_water_beside_the_engineers(cfg):
    s = strait(cfg)
    eng = create_unit(s, cfg, "engineers", EU, at(5, 4))
    water = at(6, 4)
    with pytest.raises(CommandError, match="robotics"):
        build_bridge(s, cfg, eng, water)
    s.players[EU].techs.append("robotics")
    with pytest.raises(CommandError):
        build_bridge(s, cfg, eng, at(8, 4))  # not beside the engineers
    with pytest.raises(CommandError):  # other improvements stay on the engineers' own hex
        apply_command(
            s, cfg, BuildImprovement(player=EU, unit=eng.id, improvement="road", target=water)
        )
    s.tiles[at(7, 3)].terrain = "ocean"
    eng2 = create_unit(s, cfg, "engineers", EU, at(8, 3))
    assert at(7, 3) not in improvements.bridge_targets(s, cfg, eng2)  # deep ocean: no bridge
    offered = [
        c
        for c in legal_commands(s, cfg, EU)
        if isinstance(c, BuildImprovement) and c.unit == eng.id and c.improvement == "sea_bridge"
    ]
    assert water in {c.target for c in offered}
    build_bridge(s, cfg, eng, water)
    assert s.tiles[water].route == "sea_bridge"
    assert is_passable_land(cfg, s.tiles[water])
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_land_units_cross_a_bridge_and_it_connects_cities(cfg):
    s = strait(cfg)
    s.players[EU].techs.append("robotics")
    west = add_city(s, cfg, at(3, 4), ACTIVE, EU, pop=2)
    west.is_capital = True
    other = add_city(s, cfg, at(10, 4), ACTIVE, EU, pop=1)
    for col in range(4, 10):
        if col != 6:
            s.tiles[at(col, 4)].route = "road"
    network.update_connections(s, cfg, EU)
    assert not other.connected
    inf = create_unit(s, cfg, "infantry", EU, at(5, 2))
    with pytest.raises(CommandError, match="no path"):  # the channel stops it
        apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=at(8, 2)))
    eng = create_unit(s, cfg, "engineers", EU, at(5, 4))
    build_bridge(s, cfg, eng, at(6, 4))
    network.update_connections(s, cfg, EU)
    assert other.connected  # the bridge counts as a road
    inf.tile, inf.moves_left = at(5, 4), cfg.units["infantry"]["moves"] * cfg.t("movement.scale")
    apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=east(at(5, 4), 3)))
    assert inf.tile == east(at(5, 4), 3)  # across at road speed


def test_aliens_cross_and_pillage_a_bridge(cfg):
    s = strait(cfg)
    s.players[EU].techs.append("robotics")
    eng = create_unit(s, cfg, "engineers", EU, at(5, 4))
    build_bridge(s, cfg, eng, at(6, 4))
    assert s.tiles[at(6, 4)].built_by == EU
    raider = create_unit(s, cfg, "alien_pillager", ALIENS, at(6, 4))  # anyone may stand on it
    events = pillage(s, cfg, raider)
    assert events and s.tiles[at(6, 4)].route is None
    assert is_passable_land(cfg, s.tiles[raider.tile])  # stepped back ashore


def test_an_ai_with_robotics_bridges_toward_its_ally(cfg):
    from test_m3_units_combat import NA

    from beacon import fog
    from beacon.ai import AIPlayer

    s = strait(cfg)
    for i, t in enumerate(s.tiles):  # the far shore is the ally's continent
        if i % s.width > 6:
            t.continent = NA
    for pid in (EU, NA):
        s.players[pid].character = sorted(cfg.ai("characters"))[0]
        s.players[pid].allies = [NA if pid == EU else EU]
    s.players[EU].techs.append("robotics")
    home = add_city(s, cfg, at(3, 4), ACTIVE, EU, pop=2)
    home.is_capital = home.connected = True
    friend = add_city(s, cfg, at(10, 4), ACTIVE, NA, pop=2, continent=NA)
    for col in (4, 5):
        s.tiles[at(col, 4)].route = "road"
    eng = create_unit(s, cfg, "engineers", EU, at(4, 4))
    fog.reveal_around(s, cfg, EU, at(7, 4), 7)  # the AI has explored the arena
    assert str(friend.id) in s.players[EU].known_cities
    ai = AIPlayer(s, cfg, EU, lambda cmd: apply_command(s, cfg, cmd))
    net = ai._network()
    shore, water = ai.bridge_site(net)
    assert s.tiles[water].terrain == "coast" and shore in net
    ai.engineer(eng, net, set())
    assert eng.job is not None and eng.job.improvement == "sea_bridge" and eng.job.tile == water


# -- the leader ------------------------------------------------------------------------------------


def led(cfg, pop=3):
    """The arena with a leader for Europe and a capital."""
    s = arena(cfg)
    s.players[EU].leader = leader.generate(cfg, 1, EU)
    home = add_city(s, cfg, at(3, 4), ACTIVE, EU, pop=pop)
    home.is_capital = True
    citizens.assign_all(s, cfg)
    return s, home


def test_every_player_gets_a_seeded_leader(cfg):
    s = new_game(cfg, seed=3)
    leaders = [p.leader for p in s.players.values()]
    assert len({lead.name for lead in leaders}) == len(leaders)
    start = cfg.leader("start")
    for lead in leaders:
        # 15 points spread by seed, at most 5 in one skill (designer 2026-11-16)
        assert set(lead.skills) == set(DOMAINS) and sum(lead.skills.values()) == 15
        assert max(lead.skills.values()) <= 5
        assert len(lead.traits) == start["traits"] and lead.level == 1
        assert start["age_min"] <= lead.start_age <= start["age_max"]
        assert leader.looks(cfg)[lead.look] == lead.sex
    assert [p.leader for p in new_game(cfg, seed=3).players.values()] == leaders
    assert any(c.refuses_hybrids for c in s.cities) and not all(c.refuses_hybrids for c in s.cities)
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_creation_screen_remakes_the_leader_before_the_first_turn(cfg):
    s, _ = led(cfg)
    make = CreateLeader(
        player=EU,
        name="Rhea Calder",
        sex="woman",
        look="woman_1",
        age=42,
        traits=("steady", "visionary"),
        skills={"science": 5, "production": 4, "military": 3, "food": 3},
    )
    sk = make.skills
    for bad in (
        CreateLeader(
            player=EU, name="X", sex="man", look="woman_1", age=42, traits=make.traits, skills=sk
        ),
        CreateLeader(
            player=EU, name="X", sex="woman", look="woman_1", age=90, traits=make.traits, skills=sk
        ),
        CreateLeader(
            player=EU, name="X", sex="woman", look="woman_1", age=42, traits=("steady",), skills=sk
        ),
        # all 15 points must be spent, at most 5 in one skill
        CreateLeader(
            player=EU,
            name="X",
            sex="woman",
            look="woman_1",
            age=42,
            traits=make.traits,
            skills={"science": 5},
        ),
        CreateLeader(
            player=EU,
            name="X",
            sex="woman",
            look="woman_1",
            age=42,
            traits=make.traits,
            skills={"science": 6, "gold": 5, "food": 4},
        ),
    ):
        with pytest.raises(CommandError):
            apply_command(s, cfg, bad)
    apply_command(s, cfg, make)
    lead = s.players[EU].leader
    assert lead.skills["science"] == 5 and lead.skills["beacon"] == 0
    assert (lead.name, lead.start_age, lead.traits, lead.custom) == (
        "Rhea Calder",
        42,
        ["steady", "visionary"],
        True,
    )
    s.turn = 24
    assert leader.age(cfg, s, lead) == 44  # a year every twelve turns (a turn is a month)
    with pytest.raises(CommandError, match="first turn"):
        apply_command(s, cfg, make)
    apply_command(s, cfg, SetWardrobe(player=EU, outfit="field_uniform", accessories=("medal",)))
    assert lead.outfit == "field_uniform" and lead.accessories == ["medal"]


def test_skills_add_to_every_city_and_military_to_city_strength(cfg):
    s, home = led(cfg)
    other = add_city(s, cfg, at(10, 6), ACTIVE, EU, pop=1)
    lead = s.players[EU].leader
    lead.skills = {**lead.skills, "science": 4, "military": 3}
    for city in (home, other):
        lines = economy.city_yields(s, cfg, city).lines
        assert (f"leader:{lead.name}", "science", 4) in lines
    line = next(
        x["value"]
        for x in combat.city_strength(s, cfg, other).lines
        if x["source"] == f"leader:{lead.name}"
    )
    assert line == 3 * cfg.t("citizens.military_strength")


def test_achievements_level_the_leader_and_milestones_offer_bonuses(cfg):
    s, _ = led(cfg)
    lead = s.players[EU].leader
    lead.traits = ["steady", "visionary"]
    s.players[EU].credits["cities_liberated"] = 2  # 60 XP: level 2 (40)
    events = leader.end_of_turn(s, cfg)
    assert {"leader_level", "leader_milestone"} <= {e["kind"] for e in events}
    assert lead.level == 2 and leader.points(cfg, lead) == 1
    before = lead.skills["production"]
    apply_command(s, cfg, RaiseSkill(player=EU, skill="production"))
    assert lead.skills["production"] == before + 1
    with pytest.raises(CommandError, match="no skill points"):
        apply_command(s, cfg, RaiseSkill(player=EU, skill="production"))
    assert lead.choices == ["liberator:1"]
    with pytest.raises(CommandError):
        apply_command(s, cfg, ChooseLeaderBonus(player=EU, choice="liberator:1", option="ranged"))
    flank = techfx.total(cfg, s.players[EU], "flanking_pct")
    apply_command(s, cfg, ChooseLeaderBonus(player=EU, choice="liberator:1", option="flanking"))
    assert techfx.total(cfg, s.players[EU], "flanking_pct") == flank + 10
    assert techfx.total(cfg, s.players[EU], "city_strength") == 5  # the Steady trait
    # level 5 (280 XP) adds a third trait to choose
    s.players[EU].credits["kills"] = 120
    leader.end_of_turn(s, cfg)
    assert lead.level >= 5 and "trait" in lead.choices and "hunter:30" in lead.choices
    apply_command(s, cfg, ChooseLeaderBonus(player=EU, choice="trait", option="builder"))
    assert lead.traits == ["steady", "visionary", "builder"]
    assert leader.xp_for_level(cfg, 2) == 40 and leader.xp_for_level(cfg, 4) == 180


def test_a_family_child_is_born_in_the_capital_and_grows_up_for_xp(cfg):
    s, home = led(cfg)
    partner = person(s, home, {"food": 3, "gold": 3})
    s.cities[home.id].pop += 1
    with pytest.raises(CommandError):
        apply_command(s, cfg, StartFamily(player=EU, partner="citizen:999"))
    apply_command(s, cfg, StartFamily(player=EU, partner=f"citizen:{partner.id}"))
    lead = s.players[EU].leader
    with pytest.raises(CommandError, match="on the way"):
        apply_command(s, cfg, StartFamily(player=EU, partner=f"citizen:{partner.id}"))
    pop = home.pop
    s.turn = lead.due
    events = leader.end_of_turn(s, cfg)
    born = next(e for e in events if e["kind"] == "leader_child_born")
    child = s.citizens[str(born["citizen"])]
    assert home.pop == pop + 1 and child.kin and not child.hybrid and not child.adult
    assert sum(child.stats.values()) == 6
    with pytest.raises(CommandError, match="grow again"):
        apply_command(s, cfg, StartFamily(player=EU, partner=f"citizen:{partner.id}"))
    s.turn += cfg.leader("family.cooldown_turns")
    with pytest.raises(CommandError, match="grown up"):  # the cooldown is over, the child is not
        apply_command(s, cfg, StartFamily(player=EU, partner=f"citizen:{partner.id}"))
    child.growth = 99
    citizens.grow(s, cfg, home, 5)
    assert child.adult and s.players[EU].credits["leader_children"] == 1
    leader.end_of_turn(s, cfg)
    assert "parent:1" in s.players[EU].leader.choices


def test_a_hybrid_averages_its_parents_and_some_cities_refuse_it(cfg):
    s, home = led(cfg)
    rec = make_recruit(s, EU, {"science": 20, "beacon": 10})
    with pytest.raises(CommandError, match="seated"):
        apply_command(s, cfg, StartFamily(player=EU, partner=f"recruit:{rec.id}"))
    rec.seats = ["science"]
    apply_command(s, cfg, StartFamily(player=EU, partner=f"recruit:{rec.id}"))
    s.turn = s.players[EU].leader.due
    born = next(e for e in leader.end_of_turn(s, cfg) if e["kind"] == "leader_child_born")
    child = s.citizens[str(born["citizen"])]
    lead_total = sum(s.players[EU].leader.skills.values())
    assert child.hybrid and sum(child.stats.values()) == (lead_total + 30) // 2  # the average
    assert child.stats["science"] > child.stats.get("food", 0)
    child.adult = True
    home.refuses_hybrids = True
    tile = at(4, 4)
    s.tiles[tile].improvement = "farm"
    with pytest.raises(CommandError, match="refuses"):
        apply_command(s, cfg, SetCitizenJob(player=EU, citizen=child.id, job=f"tile:{tile}"))
    citizens.assign_all(s, cfg)
    assert child.tile is None


def test_a_hybrid_on_the_council_can_be_voted_out_and_moves(cfg):
    def always(raw):
        raw["leaders"]["hybrids"]["vote_out_pct"] = 100

    hard = config.load(overrides=always)
    s, home = led(hard)
    home.refuses_hybrids = True
    away = add_city(s, hard, at(10, 6), ACTIVE, EU, pop=1)
    c = person(s, home, {"science": 9}, adult=True)
    c.hybrid = True
    home.pop += 1
    apply_command(s, hard, SetCitizenJob(player=EU, citizen=c.id, job="council"))
    assert c.seats
    events = leader.end_of_turn(s, hard)
    assert any(e["kind"] == "hybrid_voted_out" for e in events)
    assert c.city == away.id and away.pop == 2 and c.banned_until > s.turn
    citizens.assign_all(s, hard)
    assert not c.seats
    with pytest.raises(CommandError, match="voted off"):
        apply_command(s, hard, SetCitizenJob(player=EU, citizen=c.id, job="council"))


def test_ai_leaders_level_spend_points_and_start_families(cfg):
    from beacon.ai import AIPlayer
    from beacon.runner import play

    state, events, _ = play(cfg, seed=2, turns=40, driver="ai")
    for pid in state.player_ids():  # milestones reached on the last turn end are answered next
        AIPlayer(state, cfg, pid, lambda c: apply_command(state, cfg, c)).lead()
    leaders = [p.leader for p in state.players.values()]
    assert any(lead.level > 1 for lead in leaders)
    for lead in leaders:
        assert leader.points(cfg, lead) == 0 and not lead.choices
        assert sum(lead.skills.values()) == 15 + lead.spent
    assert any(e["kind"] == "family_started" for e in events)


def test_leader_screen_career_and_wardrobe_locks(cfg, tmp_path, monkeypatch):
    from web import profile
    from web import session as session_mod
    from web.session import Session

    monkeypatch.setattr(session_mod, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(profile, "PROFILE", tmp_path / "profile.json")
    sess = Session(cfg, seed=3, human=EU)
    d = sess.leader()
    assert d["can_create"] and d["level"] == 1 and len(d["traits"]) == 2
    assert [o["unlocked"] for o in d["wardrobe"]["outfits"]] == [True, False]
    locked = sess.command({"kind": "set_wardrobe", "outfit": "field_uniform", "accessories": []})
    assert locked["ok"] is False and "unlocked" in locked["error"]
    assert sess.council()["leader"]["name"] == d["name"]
    assert sess.end_turn()["ok"]
    assert profile.totals(profile.load(tmp_path / "profile.json"))["games_played"] == 1
    profile.record("old", {"cities_liberated": 12}, False, tmp_path / "profile.json")
    assert sess.command({"kind": "set_wardrobe", "outfit": "field_uniform", "accessories": []})[
        "ok"
    ]
    assert sess.leader()["career"]["cities_liberated"] >= 12
