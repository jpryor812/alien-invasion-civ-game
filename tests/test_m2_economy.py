"""M2: yields and breakdowns, growth, production, tech gating, connection, resources, gold."""

from __future__ import annotations

import pytest

from beacon import cities, citizens, economy, hexgrid, network
from beacon.actions import apply_command, pending_decisions
from beacon.commands import (
    BuildImprovement,
    CommandError,
    Purchase,
    SetFocus,
    SetProduction,
    SetResearch,
)
from beacon.config import YIELDS
from beacon.game import new_game
from beacon.paths import shortest_path
from beacon.state import ACTIVE, OVERRUN, state_digest, state_from_json, state_to_json
from beacon.tiles import is_passable_land
from beacon.turn import advance_turn
from beacon.units import create_unit

PID = "north_america"


@pytest.fixture
def game(cfg):
    return new_game(cfg, seed=11)


def capital(state, pid=PID):
    return next(c for c in state.cities if c.owner == pid and c.is_capital)


def test_yield_totals_equal_breakdown(cfg, game):
    for city in game.cities:
        if city.status != ACTIVE:
            continue
        cy = economy.city_yields(game, cfg, city)
        for y in YIELDS:
            assert cy.totals[y] == sum(v for _, yy, v in cy.lines if yy == y)
        # one citizen per worked tile, and only improved tiles are worked (designer 2026-11-14)
        working = [c for c in citizens.of_city(game, city.id) if c.tile is not None]
        assert sorted(c.tile for c in working) == cy.worked
        assert all(game.tiles[t].improvement for t in cy.worked)


def test_focus_changes_worked_tiles(cfg, game):
    city = capital(game)
    city.pop = 4
    food = economy.city_yields(game, cfg, city).totals
    apply_command(game, cfg, SetFocus(player=PID, city=city.id, focus="production"))
    prod = economy.city_yields(game, cfg, city).totals
    assert prod["production"] >= food["production"]
    with pytest.raises(CommandError):
        apply_command(game, cfg, SetFocus(player=PID, city=city.id, focus="vibes"))


def test_growth_and_starvation(cfg, game):
    city = capital(game)
    player = game.players[PID]
    surplus = economy.city_yields(game, cfg, city).surplus_food
    assert surplus > 0
    city.food_store = economy.growth_threshold(cfg, city.pop) - surplus
    pop = city.pop
    economy.process_city(game, cfg, city, player)
    assert city.pop == pop + 1 and city.food_store == 0

    city.pop = len(cities.work_tiles(game, cfg, city)) + 10  # more mouths than tiles
    city.food_store = 0
    assert economy.city_yields(game, cfg, city).surplus_food < 0
    starving = city.pop
    economy.process_city(game, cfg, city, player)
    assert city.pop == starving - 1


def test_growth_threshold_formula(cfg):
    base, per, quad = (cfg.t(f"economy.growth_{k}") for k in ("base", "per_pop", "quad"))
    assert economy.growth_threshold(cfg, 1) == base
    assert economy.growth_threshold(cfg, 4) == base + 3 * per + 9 * quad


def test_building_completes_and_changes_yields(cfg, game):
    city = capital(game)  # players start with the capital only (designer 2026-11-14)
    assert "water_treatment" not in city.buildings
    before = economy.city_yields(game, cfg, city).totals["food"]
    item = ("building:water_treatment",)
    city.stores.update(timber=150, stone=150)  # paid up front, built by the crew (SPEC_M17)
    apply_command(game, cfg, SetProduction(player=PID, city=city.id, items=item))
    city.works[0]["left"] = 1
    events, _ = economy.process_city(game, cfg, city, game.players[PID])
    assert any(e["kind"] == "building_completed" for e in events)
    assert "water_treatment" in city.buildings and city.queue == []
    after = economy.city_yields(game, cfg, city).totals["food"]
    assert after >= before + cfg.buildings["water_treatment"]["yields"]["food"]  # +% bonuses


def test_tech_gating(cfg, game):
    city = capital(game)
    city.stores.update(timber=150, stone=150, iron=80)
    with pytest.raises(CommandError, match="advanced_manufacturing"):
        apply_command(
            game, cfg, SetProduction(player=PID, city=city.id, items=("building:factory",))
        )
    with pytest.raises(CommandError, match="not available"):
        apply_command(game, cfg, SetResearch(player=PID, tech="applied_ai"))
    player = game.players[PID]
    apply_command(game, cfg, SetResearch(player=PID, tech="advanced_manufacturing"))
    player.research_progress = cfg.techs["advanced_manufacturing"]["cost"] - 1
    advance_turn(game, cfg)
    assert "advanced_manufacturing" in player.techs and player.research is None
    assert "factory" in economy.building_options(game, cfg, city)
    apply_command(game, cfg, SetProduction(player=PID, city=city.id, items=("building:factory",)))
    assert city.works[-1]["what"] == "building:factory"  # a work for the crew (SPEC_M17)


def test_unconnected_city_produces_and_a_road_adds_connection_gold(cfg, game):
    # SPEC_M10 (designer 2026-11-15): a city produces from the start; a road to the capital pays
    w, h = game.width, game.height
    dormant = next(
        c
        for c in game.cities
        if c.continent == PID
        and c.status == OVERRUN
        and not any(game.tiles[n].route for n in hexgrid.within(c.tile, 1, w, h))
    )
    dormant.status, dormant.owner = ACTIVE, PID
    dormant.queue = ["building:food_depot"]
    network.update_connections(game, cfg, PID)
    assert not dormant.connected
    economy.player_turn(game, cfg, PID)
    assert dormant.progress.get("building:food_depot", 0) > 0
    sources = {src for src, y, _ in economy.city_yields(game, cfg, dormant).lines if y == "gold"}
    assert "connection" not in sources

    # Lay a road from the dormant city to the capital's network, as engineers would.
    net_tiles = {i for i, t in enumerate(game.tiles) if t.route} | {capital(game).tile}
    path = shortest_path(
        dormant.tile,
        net_tiles,
        lambda i: hexgrid.neighbours(i, w, h),
        lambda a, b: 1 if is_passable_land(cfg, game.tiles[b]) else None,
    )
    assert path
    for t in path[1:]:
        game.tiles[t].route = game.tiles[t].route or "road"
    network.update_connections(game, cfg, PID)
    assert dormant.connected
    lines = economy.city_yields(game, cfg, dormant).lines
    assert ("connection", "gold", cfg.t("economy.connection_gold")) in lines


def test_engineers_build_a_road_over_turns(cfg, game):
    city = capital(game)
    w, h = game.width, game.height
    tile = next(
        n
        for n in hexgrid.neighbours(city.tile, w, h)
        if is_passable_land(cfg, game.tiles[n])
        and game.tiles[n].route is None
        and game.city_at(n) is None
        and game.tiles[n].elevation in ("flat", "hills")
    )
    eng = create_unit(game, cfg, "engineers", PID, tile)
    with pytest.raises(CommandError, match="needs tech high_speed_rail"):
        apply_command(game, cfg, BuildImprovement(player=PID, unit=eng.id, improvement="railway"))
    apply_command(game, cfg, BuildImprovement(player=PID, unit=eng.id, improvement="road"))
    assert eng.job is not None and eng.moves_left == 0
    for _ in range(cfg.improvements["road"]["turns"]):
        advance_turn(game, cfg)
    assert game.tiles[tile].route == "road" and game.tiles[tile].built_by == PID
    assert eng.job is None


def test_tank_needs_oil(cfg, game):
    city = capital(game)
    apply_command(game, cfg, SetProduction(player=PID, city=city.id, items=("unit:tank",)))
    for t in cities.work_tiles(game, cfg, city):
        if game.tiles[t].resource == "oil":
            game.tiles[t].resource = None
    city.production_store = cfg.units["tank"]["cost"]
    events, _ = economy.process_city(game, cfg, city, game.players[PID])
    assert any(e["kind"] == "production_stalled" for e in events)
    oil_tile = next(
        t for t in cities.work_tiles(game, cfg, city) if is_passable_land(cfg, game.tiles[t])
    )
    game.tiles[oil_tile].resource, game.tiles[oil_tile].improvement = "oil", "extractor"
    assert economy.resource_supply(game, cfg, PID)["oil"] >= 1
    city.stores["iron"] = 80  # tanks also cost iron (SPEC_M16)
    events, _ = economy.process_city(game, cfg, city, game.players[PID])
    assert any(e["kind"] == "unit_completed" and e["type"] == "tank" for e in events)
    assert economy.resource_usage(game, cfg, PID)["oil"] == 1


def test_purchase(cfg, game):
    city = capital(game)
    player = game.players[PID]
    item = ("unit:recon_team",)  # gold buys units (buildings are the crew's, SPEC_M17)
    apply_command(game, cfg, SetProduction(player=PID, city=city.id, items=item))
    price = economy.purchase_price(cfg, item[0], player, 0, city)
    player.gold = price - 1
    before = state_digest(game)
    with pytest.raises(CommandError, match="costs"):
        apply_command(game, cfg, Purchase(player=PID, city=city.id))
    assert state_digest(game) == before
    player.gold = price
    events = apply_command(game, cfg, Purchase(player=PID, city=city.id))
    assert any(e["kind"] == "unit_completed" for e in events) and player.gold == 0


def test_gold_deficit_eats_research(cfg, game):
    player = game.players[PID]
    player.gold = 0
    player.research_progress = 1000
    for c in game.cities:
        if c.owner == PID:
            c.buildings = sorted(cfg.buildings)  # maintenance far above income
    science = sum(
        economy.city_yields(game, cfg, c).totals["science"]
        for c in game.cities
        if c.owner == PID and c.connected
    )
    events = economy.player_turn(game, cfg, PID)
    deficit = [e for e in events if e["kind"] == "gold_deficit"]
    assert deficit and player.gold == 0
    # The shortfall comes out of research progress before this turn's science goes in.
    assert player.research_progress == 1000 - deficit[0]["shortfall"] + science


def test_pending_decisions_at_start(cfg, game):
    kinds = {d["kind"] for d in pending_decisions(game, cfg, PID)}
    assert kinds == {"choose_research", "choose_production", "unit_needs_orders"}


def test_turns_advance_and_state_round_trips(cfg, game):
    for pid in game.player_ids():
        apply_command(game, cfg, SetResearch(player=pid, tech="urban_planning"))
        for c in game.cities:
            if c.owner == pid:
                apply_command(
                    game,
                    cfg,
                    SetProduction(player=pid, city=c.id, items=("building:workshop",))
                    if "workshop" not in c.buildings
                    else SetProduction(player=pid, city=c.id, items=("unit:infantry",)),
                )
    turns = 40  # a reclaimed-size city makes 3-4 production; a workshop costs 70
    for _ in range(turns):
        advance_turn(game, cfg)
    assert game.turn == turns
    assert state_to_json(state_from_json(state_to_json(game))) == state_to_json(game)
    # every connected city finished it (alien raiders may cut a road after turn 25)
    linked = [c for c in game.cities if c.status == ACTIVE and c.connected]
    assert linked and all("workshop" in c.buildings for c in linked)
