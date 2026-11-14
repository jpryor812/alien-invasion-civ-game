"""M5: promoted content, beacon levers, recruits, councils, trading and betrayal."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, NA, add_city, arena, at, east

from beacon import combat, economy, recruits
from beacon.actions import apply_command
from beacon.commands import (
    AcceptOffer,
    CommandError,
    DeclineOffer,
    OfferRecruit,
    SeatRecruit,
    UnseatRecruit,
)
from beacon.config import DOMAINS
from beacon.runner import play, replay
from beacon.state import ACTIVE, ALIENS, OVERRUN, Recruit, state_digest
from beacon.units import create_unit

LEVELS = (
    "beacon_theory",
    "signal_amplification",
    "harmonic_lattice",
    "deep_resonance",
    "stellar_chorus",
)


def make(state, pid, scores, traits=(), lifespan=60) -> Recruit:
    rec = Recruit(
        id=state.new_id(),
        name=f"R{state.next_id}",
        kind="soldier",
        legendary=False,
        scores=dict(scores),
        traits=list(traits),
        born=state.turn,
        lifespan=lifespan,
        patron=pid,
    )
    state.recruits[str(rec.id)] = rec
    return rec


# -- content -----------------------------------------------------------------------------------


def test_proposed_content_is_promoted(cfg):
    for name in ("terrain", "units", "buildings", "improvements", "techs", "aliens"):
        assert "additional" not in cfg.raw[name], name
    for unit in ("walker", "swarm_drones", "alien_leviathan"):
        assert unit in cfg.units
    assert {"quantum_lab", "beacon_v"} <= set(cfg.buildings)
    assert {"stellar_chorus", "directed_energy"} <= set(cfg.techs)
    assert len(cfg.alien_techs) == 18
    assert len(cfg.tables["recruit_traits"]) == 11


def test_beacon_levels_are_five_and_steep(cfg):
    levels = cfg.alien("recruits.levels")
    assert len(levels) == 5 == len(cfg.alien("recruits.rarity_techs"))
    costs = [lv["arrival_cost"] for lv in levels]
    assert all(b > a for a, b in zip(costs, costs[1:], strict=False))
    chain = [cfg.buildings[f"beacon_{n}"]["cost"] for n in ("i", "ii", "iii", "iv", "v")]
    assert all(b >= 2 * a for a, b in zip(chain, chain[1:], strict=False))


# -- arrivals and rolled recruits --------------------------------------------------------------


def test_recruit_arrives_when_points_reach_the_cost(cfg):
    s = arena(cfg)
    player = s.players[EU]
    player.beacon_points = 10_000
    assert recruits.arrivals(s, cfg, EU) == []  # no beacon tech yet
    player.techs.append("beacon_theory")
    cost = recruits.arrival_cost(cfg, 1)
    player.beacon_points = cost - 1
    assert recruits.arrivals(s, cfg, EU) == []
    player.beacon_points = cost
    events = recruits.arrivals(s, cfg, EU)
    assert events and events[0]["kind"] == "recruit_arrived"
    assert player.beacon_points == 0 and len(recruits.recruits_of(s, EU)) == 1


def test_rolled_recruits_follow_budget_focus_traits_and_lifespan(cfg):
    s = arena(cfg)
    rs = cfg.alien("recruits")
    for level in (1, 3, 5):
        budget = rs["levels"][level - 1]["budget"]
        for k in range(40):
            s.turn = k
            rec = recruits.make_recruit(s, cfg, EU, level)
            if rec.legendary:
                continue
            spec = cfg.tables["recruit_types"][rec.kind]
            assert set(rec.scores) <= set(spec["focus"])
            raw_total = sum(rec.scores.values())
            assert budget <= raw_total <= budget * 2  # traits only ever raise scores
            assert set(rec.traits) - {"immortal"} <= set(spec["traits"])
            if "immortal" in rec.traits:
                assert rec.lifespan is None
            else:
                assert rs["min_lifespan"] <= rec.lifespan <= rs["max_lifespan"]


def test_higher_rarity_brings_legends_and_bigger_budgets(cfg):
    s = arena(cfg)
    legends = 0
    for k in range(200):
        s.turn = k
        legends += recruits.make_recruit(s, cfg, EU, 5).legendary
    assert 0 < legends <= len(cfg.tables["legendary_recruits"])  # each legend is unique
    s2 = arena(cfg)
    for k in range(200):
        s2.turn = k
        assert not recruits.make_recruit(s2, cfg, EU, 1).legendary


def test_rarity_counts_beacon_techs_in_order(cfg):
    assert recruits.rarity_level(cfg, []) == 0
    assert recruits.rarity_level(cfg, list(LEVELS[:3])) == 3
    assert recruits.rarity_level(cfg, [LEVELS[0], LEVELS[2]]) == 1


# -- councils ----------------------------------------------------------------------------------


def test_domain_seats_two_each_and_multi_domain_sitting(cfg):
    s = arena(cfg)
    a = make(s, EU, {"science": 8, "production": 8})
    apply_command(s, cfg, SeatRecruit(player=EU, recruit=a.id, seats=("production", "science")))
    assert a.seats == ["production", "science"]
    b = make(s, EU, {"science": 5})
    apply_command(s, cfg, SeatRecruit(player=EU, recruit=b.id, seats=("science",)))
    c = make(s, EU, {"science": 4})
    with pytest.raises(CommandError, match="both science seats"):
        apply_command(s, cfg, SeatRecruit(player=EU, recruit=c.id, seats=("science",)))
    with pytest.raises(CommandError, match="no food score"):
        apply_command(s, cfg, SeatRecruit(player=EU, recruit=c.id, seats=("food",)))


def test_general_seats_apply_everything_and_hold_three(cfg):
    s = arena(cfg)
    flat = {d: 3 for d in DOMAINS}
    seated = []
    for _ in range(3):
        r = make(s, EU, flat)
        apply_command(s, cfg, SeatRecruit(player=EU, recruit=r.id, seats=("general",)))
        seated.append(r)
    extra = make(s, EU, flat)
    with pytest.raises(CommandError, match="general seats"):
        apply_command(s, cfg, SeatRecruit(player=EU, recruit=extra.id, seats=("general",)))
    with pytest.raises(CommandError, match="no other council"):
        apply_command(s, cfg, SeatRecruit(player=EU, recruit=extra.id, seats=("general", "food")))
    for d in DOMAINS:
        assert sum(p for _, p in recruits.council_lines(s, EU, d)) == 9
    apply_command(s, cfg, UnseatRecruit(player=EU, recruit=seated[0].id))
    assert sum(p for _, p in recruits.council_lines(s, EU, "food")) == 6


def test_gold_council(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(5, 5), ACTIVE, EU, pop=3)
    city.connected = True
    before = economy.city_yields(s, cfg, city).totals["gold"]
    rec = make(s, EU, {"gold": 50}, traits=["greedy"])
    apply_command(s, cfg, SeatRecruit(player=EU, recruit=rec.id, seats=("gold",)))
    assert economy.city_yields(s, cfg, city).totals["gold"] == before + before * 50 // 100
    assert "gold" in cfg.alien("recruits.domains")
    rolled = recruits.make_recruit(s, cfg, EU, 1)
    assert set(rolled.scores) <= set(DOMAINS)


def test_council_bonuses_show_in_yields_and_combat(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(5, 5), ACTIVE, EU, pop=3)
    city.connected = True
    before = economy.city_yields(s, cfg, city).totals["production"]
    rec = make(s, EU, {"production": 50, "military": 20})
    apply_command(s, cfg, SeatRecruit(player=EU, recruit=rec.id, seats=("production", "military")))
    cy = economy.city_yields(s, cfg, city)
    assert any(src.startswith("council:") for src, y, _ in cy.lines if y == "production")
    assert cy.totals["production"] == before + before * 50 // 100
    inf = create_unit(s, cfg, "infantry", EU, east(city.tile))
    strength = combat.unit_strength(s, cfg, inf, ranged=False, defending=False)
    assert any(line["source"].startswith("council:") for line in strength.lines)
    assert strength.total == 30 * 100 * 120 // 100


# -- trading -----------------------------------------------------------------------------------


def test_gift_sale_and_decline(cfg):
    s = arena(cfg)
    gift = make(s, EU, {"food": 5})
    apply_command(s, cfg, SeatRecruit(player=EU, recruit=gift.id, seats=("food",)))
    events = apply_command(s, cfg, OfferRecruit(player=EU, recruit=gift.id, to_player=NA, price=0))
    offer_id = events[0]["offer"]
    apply_command(s, cfg, AcceptOffer(player=NA, offer=offer_id))
    assert gift.patron == NA and gift.seats == []
    assert s.players[EU].credits["recruits_given"] == 1

    sale = make(s, EU, {"science": 6})
    s.players[NA].gold, s.players[EU].gold = 100, 0
    oid = apply_command(s, cfg, OfferRecruit(player=EU, recruit=sale.id, to_player=NA, price=40))[
        0
    ]["offer"]
    with pytest.raises(CommandError):
        apply_command(s, cfg, AcceptOffer(player=EU, offer=oid))  # only the recipient answers
    apply_command(s, cfg, AcceptOffer(player=NA, offer=oid))
    assert s.players[NA].gold == 60
    assert s.players[EU].gold == 40
    assert s.players[EU].credits["recruits_sold"] == 1

    keep = make(s, EU, {"beacon": 4})
    oid = apply_command(s, cfg, OfferRecruit(player=EU, recruit=keep.id, to_player=NA, price=1000))[
        0
    ]["offer"]
    with pytest.raises(CommandError, match="price"):
        apply_command(s, cfg, AcceptOffer(player=NA, offer=oid))
    apply_command(s, cfg, DeclineOffer(player=NA, offer=oid))
    assert keep.patron == EU and not s.offers


# -- death and betrayal ------------------------------------------------------------------------


def test_mortal_recruits_die_and_immortals_do_not(cfg):
    s = arena(cfg)
    mortal = make(s, EU, {"food": 3}, lifespan=50)
    immortal = make(s, EU, {"food": 3}, traits=["immortal"], lifespan=None)
    s.turn = 49
    recruits.end_of_turn(s, cfg)
    assert str(mortal.id) in s.recruits
    s.turn = 50
    events = recruits.end_of_turn(s, cfg)
    assert [e["kind"] for e in events] == ["recruit_died"]
    s.turn = 10_000
    recruits.end_of_turn(s, cfg)
    assert str(immortal.id) in s.recruits


def test_betrayal_joins_an_alien_city_and_liberation_frees(calm_cfg):
    cfg = calm_cfg
    s = arena(cfg)
    capital = add_city(s, cfg, at(2, 2), ACTIVE, NA)
    capital.is_capital = True
    alien_city = add_city(s, cfg, at(9, 5), OVERRUN, ALIENS)
    s.aliens.start_cities = 1
    rec = make(s, NA, {"military": 15}, traits=["traitor"])
    before = combat.city_strength(s, cfg, alien_city).total
    event = recruits.betray(s, rec)
    assert event["alien_city"] == alien_city.id and rec.patron is None
    assert combat.city_strength(s, cfg, alien_city).total == before * 115 // 100
    assert s.players[NA].credits["recruits_lost"] == 1
    inf = create_unit(s, cfg, "infantry", EU, east(alien_city.tile, -1))
    alien_city.hp = 1
    combat.attack(s, cfg, inf, alien_city.tile)
    assert alien_city.status == ACTIVE
    assert rec.patron == EU and rec.alien_city is None  # it joins the liberator


@pytest.fixture(scope="module")
def calm_cfg():
    from beacon import config

    def zero(raw):
        raw["tuning"]["combat"]["variance_pct"]["value"] = 0

    return config.load(overrides=zero)


def test_betrayal_with_no_alien_city_just_leaves(cfg):
    s = arena(cfg)
    rec = make(s, EU, {"food": 3}, traits=["traitor"])
    recruits.betray(s, rec)
    assert str(rec.id) not in s.recruits


def test_offers_lapse_at_turn_end(cfg):
    s = arena(cfg)
    rec = make(s, EU, {"food": 3})
    apply_command(s, cfg, OfferRecruit(player=EU, recruit=rec.id, to_player=NA, price=0))
    recruits.end_of_turn(s, cfg)
    assert not s.offers


def test_recruit_games_replay_exactly(cfg):
    turns = 45
    state, events, log = play(cfg, seed=2, turns=turns)
    assert any(e["kind"] == "recruit_arrived" for e in events)
    assert state_digest(replay(cfg, 2, turns, log)) == state_digest(state)
