"""M6: deals, delivery by sea and convoy, lending, alliances, troops abroad, rescue, the AI."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from test_m3_units_combat import EU, NA, add_city, arena, at

from beacon import combat, diplomacy, economy, fog, hexgrid
from beacon.actions import apply_command
from beacon.commands import AcceptDeal, CommandError, DeclineDeal, ProposeDeal, ShipUnit
from beacon.runner import play, replay
from beacon.state import ACTIVE, ALIENS, DORMANT, state_digest
from beacon.units import create_unit

SEA_COL = 7  # column of sea between Europe (west) and North America (east)


def two_continents(cfg):
    s = arena(cfg)
    for i, tile in enumerate(s.tiles):
        col, _ = hexgrid.col_row(i, s.width)
        if col == SEA_COL:
            tile.terrain, tile.continent = "coast", None
        elif col > SEA_COL:
            tile.continent = NA
    eu = add_city(s, cfg, at(6, 4), ACTIVE, EU, pop=3)
    na = add_city(s, cfg, at(8, 4), ACTIVE, NA, pop=3, continent=NA)
    for city in (eu, na):
        city.is_capital, city.connected = True, True
    return s, eu, na


def give_port(city):
    city.buildings = sorted([*city.buildings, "port"])


def propose(s, cfg, frm, to, give, take, duration=10):
    events = apply_command(
        s, cfg, ProposeDeal(player=frm, to_player=to, give=give, take=take, duration=duration)
    )
    return events[0]["deal"]


def end_turn(s, cfg):
    events = diplomacy.end_of_turn(s, cfg)
    s.turn += 1
    return events


# -- deals ---------------------------------------------------------------------------------------


def test_tech_swap_ships_by_sea_with_a_delay(cfg):
    s, eu, na = two_continents(cfg)
    give_port(eu)
    give_port(na)
    s.players[EU].techs.append("urban_planning")
    s.players[NA].techs.append("advanced_manufacturing")
    deal = propose(
        s, cfg, EU, NA, {"techs": ["urban_planning"]}, {"techs": ["advanced_manufacturing"]}
    )
    apply_command(s, cfg, AcceptDeal(player=NA, deal=deal))
    assert "urban_planning" not in s.players[NA].techs  # still at sea
    assert len(s.shipments) == 2
    for _ in range(3):
        end_turn(s, cfg)
    assert "urban_planning" in s.players[NA].techs
    assert "advanced_manufacturing" in s.players[EU].techs
    assert not s.shipments


def test_sea_delay_grows_with_distance(cfg):
    assert diplomacy.sea_turns(cfg, 1) == 1
    speed = cfg.t("trade.shipping.speed")
    assert diplomacy.sea_turns(cfg, speed * 3) == 3
    assert diplomacy.sea_turns(cfg, speed * 3 + 1) == 4


def test_decline_and_lapse(cfg):
    s, _, _ = two_continents(cfg)
    s.players[EU].gold = 50
    d1 = propose(s, cfg, EU, NA, {"gold": 10}, {})
    apply_command(s, cfg, DeclineDeal(player=NA, deal=d1))
    assert s.players[EU].gold == 50 and not s.deals
    propose(s, cfg, EU, NA, {"gold": 10}, {})
    end_turn(s, cfg)
    assert not s.deals  # unanswered proposals lapse
    with pytest.raises(CommandError, match="has only"):
        propose(s, cfg, EU, NA, {"gold": 999}, {})


def test_gold_aid_is_credited(cfg):
    s, _, _ = two_continents(cfg)
    s.players[EU].gold, s.players[NA].gold = 100, 0
    deal = propose(s, cfg, EU, NA, {"gold": 40}, {})
    apply_command(s, cfg, AcceptDeal(player=NA, deal=deal))
    assert (s.players[EU].gold, s.players[NA].gold) == (60, 40)
    assert s.players[EU].credits["aid_gold"] == 40


def test_per_turn_gold_runs_its_duration_and_breaks_when_unpaid(cfg):
    s, _, _ = two_continents(cfg)
    s.players[EU].gold, s.players[NA].gold = 1000, 0
    deal = propose(s, cfg, EU, NA, {"gold_per_turn": 5}, {}, duration=10)
    apply_command(s, cfg, AcceptDeal(player=NA, deal=deal))
    for _ in range(12):
        end_turn(s, cfg)
    assert s.players[NA].gold == 50 and not s.deals
    s.players[EU].gold = 7
    deal = propose(s, cfg, EU, NA, {"gold_per_turn": 5}, {}, duration=10)
    apply_command(s, cfg, AcceptDeal(player=NA, deal=deal))
    events = end_turn(s, cfg) + end_turn(s, cfg)
    assert any(e["kind"] == "deal_ended" and e["broken"] for e in events)


def test_resource_lending_moves_supply(cfg):
    s, eu, _ = two_continents(cfg)
    oil_tile = at(5, 4)
    s.tiles[oil_tile].city = eu.id
    s.tiles[oil_tile].resource, s.tiles[oil_tile].improvement = "oil", "extractor"
    assert economy.resource_supply(s, cfg, EU)["oil"] == 2
    deal = propose(s, cfg, NA, EU, {"gold_per_turn": 1}, {"resources": {"oil": 1}}, duration=20)
    s.players[NA].gold = 100
    apply_command(s, cfg, AcceptDeal(player=EU, deal=deal))
    assert economy.resource_supply(s, cfg, EU)["oil"] == 1
    assert economy.resource_supply(s, cfg, NA)["oil"] == 1
    with pytest.raises(CommandError, match="spare oil"):
        propose(s, cfg, EU, NA, {"resources": {"oil": 2}}, {}, duration=20)


def test_tech_gifts_need_prerequisites(cfg):
    s, _, _ = two_continents(cfg)
    s.players[EU].techs += ["advanced_manufacturing", "applied_ai"]
    with pytest.raises(CommandError, match="cannot learn applied_ai"):
        propose(s, cfg, EU, NA, {"techs": ["applied_ai"]}, {})


# -- convoys ---------------------------------------------------------------------------------------


def test_convoy_carries_goods_to_a_port(cfg):
    s, eu, na = two_continents(cfg)
    eu.is_capital = False
    inland = add_city(s, cfg, at(2, 4), ACTIVE, EU, pop=2)
    inland.is_capital = inland.connected = True
    give_port(eu)
    eu.connected = True
    eu.is_capital = False
    s.players[EU].techs.append("urban_planning")
    # No port reachable without walking: put the port out of action for the dispatch.
    eu.buildings.remove("port")
    deal = propose(s, cfg, EU, NA, {"techs": ["urban_planning"]}, {})
    events = apply_command(s, cfg, AcceptDeal(player=NA, deal=deal))
    assert any(e["kind"] == "convoy_formed" for e in events)
    convoy = next(u for u in s.units.values() if u.type == "trade_convoy")
    give_port(eu)
    convoy.tile = eu.tile  # walk it to the port
    events = end_turn(s, cfg)
    assert any(e["kind"] == "shipment_sailed" for e in events)
    for _ in range(3):
        end_turn(s, cfg)
    assert "urban_planning" in s.players[NA].techs


def test_lone_convoys_are_captured_but_escorts_protect(cfg):
    s, _, _ = two_continents(cfg)
    a = at(3, 6)
    convoy = create_unit(s, cfg, "trade_convoy", EU, a)
    raider = create_unit(s, cfg, "alien_drone", ALIENS, hexgrid.neighbours(a, s.width, s.height)[0])
    assert combat.preview_attack(s, cfg, raider, a)["kind"] == "capture"
    guard = create_unit(s, cfg, "infantry", EU, a)
    p = combat.preview_attack(s, cfg, raider, a)
    assert p["kind"] == "melee" and p["defender"]["unit"] == guard.id
    assert convoy.id in {u.id for u in s.units_at(a)}


# -- alliances -------------------------------------------------------------------------------------


def test_alliance_needs_the_tech_on_both_sides_and_shares_vision(cfg):
    s, _, na = two_continents(cfg)
    needed = cfg.t("trade.alliance_tech")
    with pytest.raises(CommandError, match=needed):
        propose(s, cfg, EU, NA, {"alliance": True}, {"alliance": True})
    s.players[EU].techs.append(needed)
    with pytest.raises(CommandError, match=needed):
        propose(s, cfg, EU, NA, {"alliance": True}, {"alliance": True})
    s.players[NA].techs.append(needed)
    with pytest.raises(CommandError, match="both sides"):
        propose(s, cfg, EU, NA, {"alliance": True}, {})
    far = at(12, 8)
    create_unit(s, cfg, "recon_team", NA, far)
    assert far not in fog.visible_tiles(s, cfg, EU)
    deal = propose(s, cfg, EU, NA, {"alliance": True}, {"alliance": True})
    apply_command(s, cfg, AcceptDeal(player=NA, deal=deal))
    assert s.players[EU].allies == [NA] and s.players[NA].allies == [EU]
    assert far in fog.visible_tiles(s, cfg, EU)


# -- troops abroad ---------------------------------------------------------------------------------


def test_shipping_troops_abroad(cfg):
    s, eu, na = two_continents(cfg)
    give_port(eu)
    s.players[EU].gold = 100
    inf = create_unit(s, cfg, "infantry", EU, eu.tile)
    s.players[EU].known_cities = {
        str(c.id): fog.CityMemory(c.status, c.owner, c.pop, 0) for c in (eu, na)
    }
    price = diplomacy.ship_price(s, cfg, eu, na)
    events = apply_command(s, cfg, ShipUnit(player=EU, unit=inf.id, city=na.id))
    assert events[0]["kind"] == "unit_shipped" and str(inf.id) not in s.units
    assert s.players[EU].gold == 100 - price
    with pytest.raises(CommandError):
        apply_command(s, cfg, ShipUnit(player=EU, unit=inf.id, city=na.id))
    for _ in range(2):
        end_turn(s, cfg)
    landed = s.unit(inf.id)
    assert landed.owner == EU and s.tiles[landed.tile].continent == NA
    assert diplomacy.units_abroad(s, EU) == 1
    base = economy.unit_upkeep(s, cfg, EU)
    landed.tile = eu.tile
    assert base > economy.unit_upkeep(s, cfg, EU)  # abroad costs extra upkeep


def test_troops_can_rescue_a_fallen_continent(cfg):
    s, eu, na = two_continents(cfg)
    give_port(eu)
    na.status, na.owner, na.is_capital = DORMANT, None, False
    from beacon.liberation import update_fallen

    update_fallen(s)
    assert s.players[NA].fallen
    s.players[EU].known_cities[str(na.id)] = fog.CityMemory(DORMANT, None, 3, 0)
    s.players[EU].gold = 100
    inf = create_unit(s, cfg, "infantry", EU, eu.tile)
    apply_command(s, cfg, ShipUnit(player=EU, unit=inf.id, city=na.id))
    for _ in range(2):
        end_turn(s, cfg)
    assert na.status == ACTIVE and na.owner == NA
    assert s.players[EU].credits["cities_reclaimed"] == 1
    update_fallen(s)
    assert not s.players[NA].fallen


# -- the AI ----------------------------------------------------------------------------------------


def test_ai_uses_no_randomness():
    tree = ast.parse(Path("beacon/ai.py").read_text())
    imported = {
        a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names
    } | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "rng" not in imported and "random" not in imported


def test_ai_games_trade_help_and_replay(cfg):
    # Troops go abroad only once home is quiet, which now takes well over 100 turns (every lost
    # city starts alien-held); shipping itself is covered by the ShipUnit tests and batch runs.
    turns = 100
    state, events, log = play(cfg, seed=3, turns=turns, driver="ai")
    kinds = {e["kind"] for e in events}
    assert "deal_accepted" in kinds
    assert any(p.allies for p in state.players.values())
    assert len({p.character for p in state.players.values()}) >= 3
    assert state_digest(replay(cfg, 3, turns, log)) == state_digest(state)


def test_human_seat_issues_no_commands(cfg):
    state, _, log = play(cfg, seed=3, turns=5, driver="ai", humans=(EU,))
    assert state.players[EU].controller == "human"
    assert not [e for e in log if e["cmd"]["player"] == EU]
