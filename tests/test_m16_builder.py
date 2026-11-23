"""M16: materials and the city builder in the main game (docs/SPEC_M16.md, designer 2026-11-16)."""

from __future__ import annotations

import pytest

from beacon import cities, combat, economy, layout, materials
from beacon.actions import apply_command
from beacon.commands import CommandError, MoveBuilding, PlaceBuilding, PlaceWalls, Purchase
from beacon.game import new_game
from beacon.state import state_from_json, state_to_json
from beacon.turn import advance_turn

EU = "europe"


@pytest.fixture
def world(cfg):
    s = new_game(cfg, seed=2, start="classic")
    capital = next(c for c in s.cities if c.owner == EU and c.is_capital)
    return s, capital


def test_cities_start_with_stores_a_hall_and_placed_buildings(cfg, world):
    s, c = world
    assert c.stores == cfg.materials("goods.start")
    hall = c.layout[0]
    assert hall["what"] == layout.HALL and hall["done"]
    assert {e["what"] for e in c.layout} == {layout.HALL, *c.buildings}
    land = layout.territory(s, cfg, c)
    for e in c.layout:  # inside the land, with a gap between buildings
        assert layout.footprint(cfg, e["what"], e["x"], e["y"]) <= land
        assert layout.place_problem(s, cfg, c, e["what"], e["x"], e["y"], skip=e["id"]) is None
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_worked_tiles_bring_materials_up_to_a_cap(cfg, world):
    s, c = world
    t = s.tiles[c.tile]
    got = materials.income(s, cfg, c, [])
    assert got["timber"] >= 1 and got["stone"] >= 1  # the city's own hex
    forest = next(i for i, x in enumerate(s.tiles) if x.feature == "forest")
    s.tiles[forest].improvement = "lumber_camp"
    assert materials.income(s, cfg, c, [forest])["timber"] >= got["timber"] + 5
    c.stores["timber"] = 149
    materials.gather(s, cfg, c, [forest])
    assert c.stores["timber"] == materials.caps(cfg, c)["timber"]
    c.buildings.append("storehouse")
    assert materials.caps(cfg, c)["timber"] > cfg.materials("goods.cap.timber")
    assert t is s.tiles[c.tile]


def test_placing_a_building_orders_it_and_it_waits_for_materials(cfg, world):
    s, c = world
    land = layout.territory(s, cfg, c)
    with pytest.raises(CommandError, match="land"):
        apply_command(
            s, cfg, PlaceBuilding(player=EU, city=c.id, building="storehouse", x=500, y=0)
        )
    hall = c.layout[0]
    with pytest.raises(CommandError, match="gap"):  # touching the hall
        apply_command(
            s,
            cfg,
            PlaceBuilding(
                player=EU, city=c.id, building="storehouse", x=hall["x"] + 4, y=hall["y"]
            ),
        )
    spot = layout.auto_spot(s, cfg, c, "storehouse")
    assert spot and layout.footprint(cfg, "storehouse", *spot) <= land
    apply_command(
        s, cfg, PlaceBuilding(player=EU, city=c.id, building="storehouse", x=spot[0], y=spot[1])
    )
    assert layout.pending(c, "storehouse")["x"] == spot[0]  # built by the crew (SPEC_M17)


def test_moving_a_building_and_unplaced_buildings_find_a_spot(cfg, world):
    s, c = world
    e = next(x for x in c.layout if x["what"] == "library")
    spot = None
    for cx, cy in sorted(layout.territory(s, cfg, c), key=lambda p: (-(p[0] ** 2 + p[1] ** 2), p)):
        if layout.place_problem(s, cfg, c, "library", cx, cy, skip=e["id"]) is None:
            spot = (cx, cy)
            break
    apply_command(s, cfg, MoveBuilding(player=EU, city=c.id, entry=e["id"], x=spot[0], y=spot[1]))
    assert (e["x"], e["y"]) == spot
    c.stores.update(timber=150, stone=150)
    c.buildings = [b for b in c.buildings if b != "storehouse"]
    economy.complete_item(s, cfg, c, "building:storehouse")  # ordered from the queue: auto-placed
    assert any(x["what"] == "storehouse" and x["done"] for x in c.layout)


def test_walls_cost_materials_and_add_strength_and_hp(cfg, world):
    from beacon import works

    s, c = world
    ring = layout.ai_ring(s, cfg, c)[:20]
    with pytest.raises(CommandError, match="tech"):
        apply_command(
            s, cfg, PlaceWalls(player=EU, city=c.id, cells=tuple(ring), material="plasma")
        )
    c.stores["stone"] = 100
    apply_command(s, cfg, PlaceWalls(player=EU, city=c.id, cells=tuple(ring), material="stone"))
    w = cfg.materials("walls.stone")
    assert len(c.wall_orders) == 20 and c.stores["stone"] == 100 - 20 * w["cost"]["stone"]
    before_hp, before = cities.max_hp(cfg, c), combat.city_strength(s, cfg, c).total
    while c.works:
        works.progress(s, cfg, c)
    assert cities.max_hp(cfg, c) == before_hp + 20 * w["hp"]
    assert combat.city_strength(s, cfg, c).total > before and not c.wall_orders
    with pytest.raises(CommandError, match="as strong"):
        apply_command(s, cfg, PlaceWalls(player=EU, city=c.id, cells=(ring[0],), material="wood"))
    with pytest.raises(CommandError, match="building"):
        apply_command(s, cfg, PlaceWalls(player=EU, city=c.id, cells=((0, 0),), material="wood"))


def test_military_needs_a_barracks_and_industry_needs_iron(cfg, world):
    s, c = world
    assert economy.unit_allowed(s, cfg, c, "infantry") is None  # capitals start with one
    c.buildings = [b for b in c.buildings if b != "military_base"]
    assert economy.unit_allowed(s, cfg, c, "infantry") == "needs a barracks"
    assert economy.unit_allowed(s, cfg, c, "recon_team") is None
    assert economy.unit_allowed(s, cfg, c, "engineers") is None
    assert (
        materials.unit_cost(cfg, "tank")["iron"] > 0 and materials.unit_cost(cfg, "infantry") == {}
    )
    c.buildings.append("military_base")
    s.players[EU].gold = 5000
    c.stores["iron"] = 0
    with pytest.raises(CommandError, match="iron"):
        apply_command(s, cfg, Purchase(player=EU, city=c.id, item="unit:tank"))


def test_ai_cities_build_walls_and_keep_producing(cfg):
    from beacon.runner import play

    s, events, _ = play(cfg, seed=1, turns=40, driver="ai", start="classic")
    kinds = [e["kind"] for e in events]
    assert "walls_ordered" in kinds  # building them takes the crew a while (SPEC_M17)
    stalls = [e for e in events if e["kind"] == "production_stalled" and e.get("needs")]
    assert len(stalls) < len(events) // 50  # the AI chooses what it has materials for
    walled = [c for c in s.cities if c.owner in s.players and (c.walls or c.wall_orders)]
    assert walled
    advance_turn(s, cfg)


def test_builder_view(cfg, tmp_path, monkeypatch):
    from web import profile
    from web import session as session_mod
    from web.session import Session

    monkeypatch.setattr(session_mod, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(profile, "PROFILE", tmp_path / "profile.json")
    sess = Session(cfg, seed=2, human=EU, start="classic")
    c = next(x for x in sess.state.cities if x.owner == EU and x.is_capital)
    d = sess.builder(c.id)
    assert d["cells"] and d["tiles"] and d["layout"][0]["what"] == layout.HALL
    assert "storehouse" in d["catalog"] and d["catalog"]["storehouse"]["size"] == 3
    assert any("storage" in g for g in d["catalog"]["storehouse"]["gives"])  # its output
    assert d["train_options"] and d["people"]  # the capital has a barracks
    assert set(d["stores"]) == {"timber", "stone", "iron"}
    detail = sess.city_detail(c.id)
    assert detail["stores"] and all("materials" in o for o in detail["options"])
