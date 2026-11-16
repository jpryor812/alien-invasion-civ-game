"""M17: labour and materials, one game (docs/SPEC_M17.md, designer 2026-11-16)."""

from __future__ import annotations

import pytest

from beacon import economy, exchange, improvements, layout, materials, works
from beacon.actions import apply_command, pending_decisions
from beacon.commands import (
    BuildImprovement,
    CancelWork,
    CommandError,
    ImproveTile,
    MoveWork,
    PlaceBuilding,
    Purchase,
    SetProduction,
    Trade,
)
from beacon.game import new_game
from beacon.state import state_from_json, state_to_json
from beacon.turn import advance_turn

EU = "europe"


@pytest.fixture
def world(cfg):
    s = new_game(cfg, seed=2, start="classic")
    capital = next(c for c in s.cities if c.owner == EU and c.is_capital)
    return s, capital


def test_cities_have_a_crew_and_no_engineer_units(cfg, world):
    s, c = world
    assert c.engineers == cfg.materials("labour.capital_start")
    assert not any(u.type == "engineers" for u in s.units.values() if u.owner == EU)
    assert works.rate(s, cfg, c) == c.engineers * cfg.materials("labour.per_engineer")
    assert "engineer" in economy.production_options(s, cfg, c)
    assert not any(i.startswith("building:") for i in economy.production_options(s, cfg, c))


def test_a_building_is_paid_up_front_and_built_by_labour(cfg, world):
    s, c = world
    spot = layout.auto_spot(s, cfg, c, "storehouse")
    c.stores["timber"] = 5
    with pytest.raises(CommandError, match="more timber"):  # must have the materials
        apply_command(
            s, cfg, PlaceBuilding(player=EU, city=c.id, building="storehouse", x=spot[0], y=spot[1])
        )
    c.stores["timber"] = 100
    apply_command(
        s, cfg, PlaceBuilding(player=EU, city=c.id, building="storehouse", x=spot[0], y=spot[1])
    )
    paid = materials.building_cost(cfg, "storehouse")["timber"]
    assert c.stores["timber"] == 100 - paid and not c.queue
    labour = works.building_labour(cfg, "storehouse")
    rate = works.rate(s, cfg, c)
    assert works.turns(s, cfg, c) == [-(-labour // rate)]
    c.engineers += 2  # more engineers, fewer turns
    assert works.turns(s, cfg, c)[0] < -(-labour // rate)
    for _ in range(works.turns(s, cfg, c)[0]):
        events = works.progress(s, cfg, c)
    assert any(e["kind"] == "building_completed" for e in events)
    assert "storehouse" in c.buildings and layout.pending(c, "storehouse") is None
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_works_go_top_down_and_cancel_refunds(cfg, world):
    s, c = world
    c.stores.update(timber=150, stone=150)
    apply_command(
        s, cfg, SetProduction(player=EU, city=c.id, items=("building:storehouse", "unit:infantry"))
    )
    other = next(b for b in economy.building_options(s, cfg, c) if b != "storehouse")
    c.stores.update(timber=150, stone=150, iron=80)
    apply_command(s, cfg, SetProduction(player=EU, city=c.id, items=(f"building:{other}",)))
    assert [w["what"] for w in c.works] == ["building:storehouse", f"building:{other}"]
    assert c.queue == []
    second = c.works[1]["id"]
    apply_command(s, cfg, MoveWork(player=EU, city=c.id, work=second, to=0))
    assert c.works[0]["id"] == second
    before = dict(c.stores)
    apply_command(s, cfg, CancelWork(player=EU, city=c.id, work=second))
    refund = materials.building_cost(cfg, other)
    assert all(c.stores[g] == before[g] + n for g, n in refund.items())
    assert layout.pending(c, other) is None
    with pytest.raises(CommandError, match="engineers"):
        apply_command(s, cfg, Purchase(player=EU, city=c.id, item="building:market"))


def test_the_crew_works_the_land_and_the_map_does_not(cfg, world):
    s, c = world
    land = layout.territory_tiles(s, cfg, c)
    target = next(t for t in land if improvements.tile_problem(s, cfg, c, t, "farm") is None)
    outside = next(t for t in range(len(s.tiles)) if t not in land)
    with pytest.raises(CommandError, match="land"):
        apply_command(s, cfg, ImproveTile(player=EU, city=c.id, tile=outside, improvement="farm"))
    with pytest.raises(CommandError, match="tile works"):
        apply_command(s, cfg, ImproveTile(player=EU, city=c.id, tile=target, improvement="road"))
    apply_command(s, cfg, ImproveTile(player=EU, city=c.id, tile=target, improvement="farm"))
    with pytest.raises(CommandError, match="already"):
        apply_command(s, cfg, ImproveTile(player=EU, city=c.id, tile=target, improvement="farm"))
    while c.works:
        works.progress(s, cfg, c)
    assert s.tiles[target].improvement == "farm" and s.tiles[target].built_by == EU
    # a road crew on the map builds roads, not farms
    from beacon.economy import place_unit

    crew = place_unit(s, cfg, "engineers", EU, c.tile, cfg.t("cities.work_radius"))
    crew.moves_left = 10
    s.tiles[crew.tile].improvement = None
    assert "ordered from the city" in improvements.build_problem(s, cfg, crew, "farm")
    with pytest.raises(CommandError):
        apply_command(s, cfg, BuildImprovement(player=EU, unit=crew.id, improvement="farm"))
    assert not any(
        p["kind"] == "unit_needs_orders" and p["unit"] == crew.id
        for p in pending_decisions(s, cfg, EU)
    )


def test_training_engineers_grows_the_crew_and_costs_upkeep(cfg, world):
    s, c = world
    first = economy.item_cost(cfg, "engineer", s.players[EU], c)
    upkeep = economy.maintenance(s, cfg, EU)
    assert economy.complete_item(s, cfg, c, "engineer")["kind"] == "engineer_trained"
    assert c.engineers == cfg.materials("labour.capital_start") + 1
    assert economy.item_cost(cfg, "engineer", s.players[EU], c) > first
    assert economy.maintenance(s, cfg, EU) == upkeep + cfg.materials("engineers.upkeep")


def test_the_galactic_exchange(cfg, world):
    s, c = world
    q = exchange.quotes(s, cfg)["timber"]
    assert q["buy"] > q["sell"]
    gold = s.players[EU].gold
    c.stores["timber"] = 100
    apply_command(s, cfg, Trade(player=EU, city=c.id, good="timber", amount=50, side="sell"))
    assert s.players[EU].gold == gold + q["sell"] * 50 and c.stores["timber"] == 50
    assert exchange.index(s, "timber") < 100
    with pytest.raises(CommandError, match="only"):
        apply_command(s, cfg, Trade(player=EU, city=c.id, good="timber", amount=500, side="sell"))
    s.players[EU].gold = 0
    with pytest.raises(CommandError, match="gold"):
        apply_command(s, cfg, Trade(player=EU, city=c.id, good="iron", amount=10, side="buy"))
    low = exchange.index(s, "timber")
    advance_turn(s, cfg)
    assert exchange.index(s, "timber") > low  # drifts back toward 100


def test_ai_builds_with_its_crew(cfg):
    from beacon.runner import play

    s, events, _ = play(cfg, seed=1, turns=30, driver="ai", start="classic")
    kinds = [e["kind"] for e in events]
    assert kinds.count("building_completed") >= 5
    assert "improvement_built" in kinds and "engineer_trained" in kinds
