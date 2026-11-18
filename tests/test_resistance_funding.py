"""Funding the resistance with gold (designer 2026-11-16): the band's first town falls by half
for the starting 100 gold; later cities cost more the stronger they are."""

from __future__ import annotations

import pytest

from beacon import combat, threat
from beacon.actions import apply_command, pending_decisions
from beacon.commands import CommandError, FundResistance
from beacon.game import new_game
from beacon.state import OVERRUN, CityMemory, state_from_json, state_to_json

EU = "europe"


def _know(s, city):
    s.players[EU].known_cities[str(city.id)] = CityMemory(
        status=city.status, owner=city.owner, pop=city.pop, turn_seen=s.turn
    )


def test_the_first_town_halves_for_the_starting_gold(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    p = s.players[EU]
    town = s.cities[p.band_town]
    assert p.gold == cfg.alien("funding.first_gold") == 100
    with pytest.raises(CommandError, match="found"):
        apply_command(s, cfg, FundResistance(player=EU, city=town.id, gold=100))
    assert not p.band_claimed  # homeless until a town is found (designer 2026-11-17)
    _know(s, town)
    from beacon import survivors

    assert survivors.claim_town(s, cfg, EU)[0]["city"] == town.id and p.band_claimed
    assert {"kind": "fund_resistance", "city": town.id} in pending_decisions(s, cfg, EU)
    before = combat.city_strength(s, cfg, town).total
    assert threat.fund_quotes(s, cfg, EU, town) == [{"gold": 100, "pct": 50}]
    apply_command(s, cfg, FundResistance(player=EU, city=town.id, gold=100))
    assert p.gold == 0 and town.funded_pct == 50
    assert combat.city_strength(s, cfg, town).total == before * 50 // 100
    assert not any(d["kind"] == "fund_resistance" for d in pending_decisions(s, cfg, EU))
    from beacon import survivors

    assert not survivors.barricades_hold(s, cfg, town, EU)  # the people open the gates
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_later_cities_cost_more_and_funding_is_capped(cfg):
    s = new_game(cfg, seed=2, start="classic")
    city = next(c for c in s.cities if c.status == OVERRUN and c.continent == EU)
    _know(s, city)
    p = s.players[EU]
    p.gold, p.agenda = 5000, None  # no agenda perk
    strength = combat.city_strength(s, cfg, city).total // 100
    pct = threat.fund_pct(s, cfg, EU, city, 500)
    assert 0 < pct < 50  # far less than the first town's deal
    assert pct == 500 // max(1, strength * cfg.alien("funding.pct_cost_tenths") // 10)
    for _ in range(10):
        if threat.fund_problem(s, cfg, EU, city, 500):
            break
        apply_command(s, cfg, FundResistance(player=EU, city=city.id, gold=500))
    assert city.funded_pct == cfg.alien("funding.max_pct")
    with pytest.raises(CommandError, match="all the help"):
        apply_command(s, cfg, FundResistance(player=EU, city=city.id, gold=500))


def test_ai_bands_fund_their_towns(cfg):
    from beacon.runner import play

    _, events, _ = play(cfg, seed=1, turns=15, driver="ai", start="survivor")
    funded = [e for e in events if e["kind"] == "resistance_funded"]
    assert funded and all(e["pct"] == 50 for e in funded)


def test_the_first_town_found_is_the_first_town(cfg):
    from beacon import survivors

    s = new_game(cfg, seed=2, start="survivor")
    p = s.players[EU]
    old = p.band_town
    other = next(c for c in s.cities if c.status == OVERRUN and c.continent == EU and c.id != old)
    big = combat.city_strength(s, cfg, other).total
    _know(s, other)
    survivors.claim_town(s, cfg, EU)
    assert p.band_town == other.id and p.band_claimed
    assert other.pop <= cfg.t("survivor.town_pop")  # weakened like the old capital
    assert combat.city_strength(s, cfg, other).total < big
    assert threat.fund_quotes(s, cfg, EU, other) == [{"gold": 100, "pct": 50}]
    _know(s, s.cities[old])  # a later find does not move it
    survivors.claim_town(s, cfg, EU)
    assert p.band_town == other.id


def test_band_strengths_and_agenda_perks(cfg):
    from beacon import exchange

    assert cfg.units["band_leader"]["strength"] == 30 and cfg.units["survivor"]["strength"] == 20
    s = new_game(cfg, seed=2, start="classic")
    p = s.players[EU]
    p.agenda = "scientist"
    plain = exchange.quotes(s, cfg, EU)["iron"]
    p.agenda = "merchant"
    better = exchange.quotes(s, cfg, EU)["iron"]
    assert better["sell"] >= plain["sell"] and better["buy"] < plain["buy"]
    city = next(c for c in s.cities if c.status == OVERRUN and c.continent == EU)
    p.agenda = "warden"
    base = threat.fund_pct(s, cfg, EU, city, 500)
    p.agenda = "liberator"
    assert threat.fund_pct(s, cfg, EU, city, 500) > base
