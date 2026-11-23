"""People, alien leaders, trading (docs/SPEC_M21.md, designer 2026-11-21)."""

from __future__ import annotations

import pytest

from beacon import alien_leaders, citizens, diplomacy, liberation, threat
from beacon.actions import apply_command, pending_decisions
from beacon.commands import AcceptDeal, AnswerAlienLeader, CommandError, ProposeDeal
from beacon.game import new_game
from beacon.state import OVERRUN, CityMemory, state_from_json, state_to_json

EU = "europe"


def _alien_town(s):
    return next(c for c in s.cities if c.status == OVERRUN and c.continent == EU)


def _know(s, city, pid=EU):
    s.players[pid].known_cities[str(city.id)] = CityMemory(
        status=city.status, owner=city.owner, pop=city.pop, turn_seen=s.turn
    )


def test_map_size_and_birth_cost(cfg):
    from beacon import economy

    assert (cfg.t("map.width"), cfg.t("map.height")) == (188, 112)
    assert economy.growth_threshold(cfg, 1) == 25
    assert economy.growth_threshold(cfg, 3) == 37


def test_freeing_a_town_pays_gold_per_citizen(cfg):
    s = new_game(cfg, seed=2, start="classic")
    city = _alien_town(s)
    city.pop = 6
    before = s.players[EU].gold
    events = liberation.liberate(s, cfg, city, EU)
    assert s.players[EU].gold >= before + 6 * 25  # plus whatever the town held
    assert next(e for e in events if e["kind"] == "city_liberated")["gold"] == 150


def test_children_get_their_stats_when_they_grow_up(cfg):
    s = new_game(cfg, seed=2, start="classic")
    city = next(c for c in s.cities if c.owner == EU and c.is_capital)
    born = citizens.born(s, cfg, city)
    child = s.citizens[str(born["citizen"])]
    assert child.stats == {} and not child.adult
    odds = born["odds"]
    assert sum(p["pct"] for p in odds["patterns"]) >= 99
    assert all(0 < v <= 100 for v in odds["domains"].values())
    city.focus = "science"
    focused = citizens.stat_odds(cfg, city)["domains"]
    assert focused["science"] > focused["gold"]
    child.growth = cfg.t("citizens.growing_up.needed") - 1
    events = citizens.grow(s, cfg, city, 10)
    grown = next(e for e in events if e["kind"] == "citizen_grew_up")
    assert child.adult and sum(child.stats.values()) == cfg.t("citizens.stats.points")
    assert grown["stats"] == child.stats and grown["player"] == EU


def test_meeting_and_bribing_alien_leaders(cfg):
    s = new_game(cfg, seed=2, start="classic")
    towns = [c for c in s.cities if c.status == OVERRUN and c.alien_leader]
    assert towns and all(
        c.alien_leader["temper"] in {"bribable", "greedy", "aggressive", "stoic"} for c in towns
    )
    by = {
        t: next(c for c in towns if c.alien_leader["temper"] == t)
        for t in ("bribable", "greedy", "aggressive", "stoic")
    }
    for c in by.values():
        _know(s, c)
    events = alien_leaders.meet(s, cfg)
    assert {e["city"] for e in events} >= {c.id for c in by.values()}
    assert {"kind": "alien_leader", "city": by["stoic"].id} in pending_decisions(s, cfg, EU)
    p = s.players[EU]
    p.gold = 10_000
    heat = threat.heat(s, cfg, EU)
    with pytest.raises(CommandError, match="bribe"):
        apply_command(s, cfg, AnswerAlienLeader(player=EU, city=by["stoic"].id, bribe=True))
    apply_command(s, cfg, AnswerAlienLeader(player=EU, city=by["stoic"].id, bribe=False))
    assert by["stoic"].id not in alien_leaders.pending(s, EU)
    good = by["bribable"]
    cost = alien_leaders.bribe_cost(s, cfg, good)
    recruits = len(s.recruits)
    out = apply_command(s, cfg, AnswerAlienLeader(player=EU, city=good.id, bribe=True))
    assert out[0]["kind"] == "alien_leader_defected" and p.gold == 10_000 - cost
    assert len(s.recruits) == recruits + 1 and good.funded_pct == cfg.alien("funding.max_pct")
    bad = by["greedy"]
    gold = p.gold
    out = apply_command(s, cfg, AnswerAlienLeader(player=EU, city=bad.id, bribe=True))
    assert out[0]["kind"] == "alien_bribe_taken" and p.gold < gold and bad.funded_pct == 0
    with pytest.raises(CommandError, match="again"):
        apply_command(s, cfg, AnswerAlienLeader(player=EU, city=bad.id, bribe=True))
    assert EU in by["aggressive"].alien_leader["angry"]
    assert threat.heat(s, cfg, EU) >= heat  # the aggressive leader adds heat
    assert alien_leaders.angry_heat(s, cfg, EU) == cfg.alien("leaders.aggressive_heat")
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_deals_trade_materials_once_and_every_turn(cfg):
    s = new_game(cfg, seed=2, start="classic")
    other = "asia"
    s.players[EU].met = [other]
    s.players[other].met = [EU]
    mine = next(c for c in s.cities if c.owner == EU and c.is_capital)
    theirs = diplomacy.capital(s, other)
    mine.stores["timber"] = 100
    t0 = theirs.stores.get("timber", 0)
    apply_command(
        s,
        cfg,
        ProposeDeal(
            player=EU,
            to_player=other,
            give={"materials": {"timber": 30}, "materials_per_turn": {"timber": 5}},
            take={"gold": 0, "gold_per_turn": 0},
            duration=10,
        ),
    )
    deal = next(iter(s.deals.values()))
    apply_command(s, cfg, AcceptDeal(player=other, deal=deal.id))
    assert mine.stores["timber"] == 70 and theirs.stores["timber"] == t0 + 30
    diplomacy.end_of_turn(s, cfg)
    assert mine.stores["timber"] == 65 and theirs.stores["timber"] == t0 + 35
    with pytest.raises(CommandError, match="only"):
        apply_command(
            s,
            cfg,
            ProposeDeal(
                player=EU,
                to_player=other,
                give={"materials": {"iron": 10_000}},
                take={},
                duration=10,
            ),
        )


def test_the_trade_screen_shows_one_civ(cfg):
    from web.session import Session

    sess = Session(cfg, seed=2, human=EU, start="classic")
    sess.state.players[EU].met = ["asia"]
    d = sess.trade("asia")
    assert d["other"]["id"] == "asia" and set(d["me"]["materials"]) >= {"timber", "stone"}
    assert "alliance_ready" in d and d["durations"]
    with pytest.raises(ValueError):
        sess.trade("africa")
