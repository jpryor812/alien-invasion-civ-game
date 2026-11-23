"""M13: the council of continents (docs/SPEC_M13.md, designer 2026-11-15)."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, NA, add_city, arena, at

from beacon import combat, council, mvp, techfx
from beacon.actions import apply_command, pending_decisions
from beacon.commands import CastVote, CommandError, ProposeMeasure, SetAgenda
from beacon.game import new_game
from beacon.state import ACTIVE, ALIENS, OVERRUN, Measure, state_from_json, state_to_json
from beacon.units import create_unit


@pytest.fixture(scope="module")
def cfg():
    """Sessions and votes are off in the data until redesigned (SPEC_M20); these tests keep the
    dormant feature working."""
    from beacon import config

    def on(raw):
        raw["council"]["sessions"]["enabled"] = True

    return config.load(overrides=on)


def on_air(s, cfg):
    """The arena's two players each hold a city with a radio tower (they sit on the council)."""
    for pid, tile in ((EU, at(1, 1)), (NA, at(12, 8))):
        city = add_city(s, cfg, tile, ACTIVE, pid, pop=1, continent=pid)
        city.buildings = [cfg.t("contact.radio_building")]
    return s


def test_radio_contact_at_the_start_without_sharing_cities(cfg):
    s = new_game(cfg, seed=2)
    ids = s.player_ids()
    for pid in ids:
        assert sorted(s.players[pid].met) == sorted(p for p in ids if p != pid)
        for cid in s.players[pid].known_cities:
            city = s.cities[int(cid)]
            assert city.continent == pid or city.owner == pid or city.status == OVERRUN
    agendas = [s.players[p].agenda for p in ids]
    goals = [s.players[p].objective for p in ids]
    assert len(set(agendas)) == len(cfg.council("agendas")) and len(set(goals)) == len(ids)


def test_influence_comes_from_credits_and_agenda(cfg):
    s = arena(cfg)
    p = s.players[EU]
    assert council.influence(cfg, p) == 0
    p.credits = {"cities_liberated": 2, "aid_gold": 120}
    base = 2 * 10 + 120 // 50
    assert council.influence(cfg, p) == base
    p.agenda = "liberator"
    assert council.influence(cfg, p) == base + 2 * 5
    p.credits["cities_liberated"] = 10
    assert council.weight(cfg, p) == 1 + council.influence(cfg, p) // 50


def test_sessions_open_on_schedule_and_elect_a_chair(cfg):
    s = on_air(arena(cfg), cfg)
    s.turn = 4
    events = council.end_of_turn(s, cfg)
    assert any(e["kind"] == "council_session" for e in events)
    (m,) = s.council.measures
    assert m.kind == "chair_election"  # no chair yet: the first session elects one
    assert {"kind": "council_vote"} in pending_decisions(s, cfg, EU)
    apply_command(s, cfg, CastVote(player=EU, measure=m.id, choice=NA))
    apply_command(s, cfg, CastVote(player=NA, measure=m.id, choice=NA))
    assert {"kind": "council_vote"} not in pending_decisions(s, cfg, EU)
    s.turn = 5
    council.end_of_turn(s, cfg)
    assert s.council.chair == NA and s.players[NA].times_chair == 1 and not s.council.measures
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_a_passed_research_pact_applies_to_everyone_then_expires(cfg):
    s = on_air(arena(cfg), cfg)
    m = Measure(id=s.new_id(), kind="research_pact")
    s.council.measures = [m]
    apply_command(s, cfg, CastVote(player=EU, measure=m.id, choice="yes"))
    council.resolve(s, cfg)
    for pid in (EU, NA):
        assert techfx.by_key(cfg, s.players[pid], "yield_pct")["science"] == 10
    s.turn += cfg.council("measures.research_pact.turns")
    council.end_of_turn(s, cfg)
    assert techfx.by_key(cfg, s.players[EU], "yield_pct").get("science", 0) == 0


def test_weighted_votes_extra_votes_and_the_chairs_tie_break(cfg):
    s = on_air(arena(cfg), cfg)
    s.players[EU].credits["cities_liberated"] = 3  # 30 influence
    m = Measure(id=s.new_id(), kind="shared_arms")
    s.council.measures = [m]
    with pytest.raises(CommandError, match="influence"):
        apply_command(s, cfg, CastVote(player=NA, measure=m.id, choice="no", extra=2))
    apply_command(s, cfg, CastVote(player=EU, measure=m.id, choice="no", extra=1))
    assert council.influence(cfg, s.players[EU]) == 30 - cfg.council("sessions.extra_vote_cost")
    apply_command(s, cfg, CastVote(player=NA, measure=m.id, choice="yes"))
    assert council._tally(s, cfg, m) == {"no": 2, "yes": 1}
    m2 = Measure(id=s.new_id(), kind="shared_arms", votes={EU: "no", NA: "yes"})
    s.council.chair = NA
    assert council._passes(s, m2, council._tally(s, cfg, m2))  # 1-1: the chair decides


def test_relief_fund_pays_the_weakest_and_pledges_count(cfg):
    s = on_air(arena(cfg), cfg)
    add_city(s, cfg, at(2, 2), ACTIVE, EU, pop=3)
    add_city(s, cfg, at(5, 2), ACTIVE, EU, pop=3)
    add_city(s, cfg, at(9, 7), ACTIVE, NA, pop=3, continent=NA)
    s.players[EU].gold, s.players[NA].gold = 100, 0
    m = Measure(id=s.new_id(), kind="relief_fund", votes={EU: "yes", NA: "yes"})
    s.council.measures = [m]
    council.resolve(s, cfg)
    gold = cfg.council("measures.relief_fund.gold")
    assert s.players[EU].gold == 100 - gold and s.players[NA].gold == gold
    assert s.players[EU].influence_adjust == cfg.council("influence.pledge_paid")


def test_a_joint_strike_boosts_attacks_near_its_city(cfg):
    s = on_air(arena(cfg), cfg)
    alien = add_city(s, cfg, at(8, 4), OVERRUN, ALIENS, pop=3)
    foe = create_unit(s, cfg, "alien_warrior", ALIENS, at(7, 4))
    inf = create_unit(s, cfg, "infantry", EU, at(6, 4))
    before = combat.unit_strength(s, cfg, inf, ranged=False, defending=False, target=foe.tile)
    s.council.measures = [Measure(id=s.new_id(), kind="joint_strike", target=alien.id)]
    s.council.measures[0].votes = {EU: "yes"}
    council.resolve(s, cfg)
    after = combat.unit_strength(s, cfg, inf, ranged=False, defending=False, target=foe.tile)
    assert after.total > before.total
    assert any(x["source"] == "joint strike" for x in after.lines)


def test_proposals_and_agenda_and_objective_points(cfg):
    s = on_air(arena(cfg), cfg)
    with pytest.raises(CommandError, match="influence"):
        apply_command(s, cfg, ProposeMeasure(player=EU, measure="research_pact"))
    s.players[EU].credits["cities_liberated"] = 2
    apply_command(s, cfg, ProposeMeasure(player=EU, measure="research_pact"))
    assert s.council.proposals[0].proposer == EU
    s.turn = 4
    council.end_of_turn(s, cfg)
    assert "research_pact" in [m.kind for m in s.council.measures]
    s2 = arena(cfg)
    apply_command(s2, cfg, SetAgenda(player=EU, agenda="scientist"))
    assert s2.players[EU].agenda == "scientist"
    s2.players[EU].objective = "kills_40"
    before = mvp.score(s2, cfg, EU)["total"]
    s2.players[EU].credits["kills"] = 40
    lines = mvp.score(s2, cfg, EU)["lines"]
    assert {"entry": "objective", "raw": 1, "points": 30} in lines
    assert mvp.score(s2, cfg, EU)["total"] > before


def test_ai_players_vote_every_measure(cfg):
    from beacon.runner import play

    state, events, _ = play(cfg, seed=3, turns=21, driver="ai")
    kinds = {e["kind"] for e in events}
    assert {"council_session", "chair_elected"} <= kinds
    assert state.council.chair in state.players
