"""M15: the settlement sandbox (docs/SPEC_M15.md, designer 2026-11-16)."""

from __future__ import annotations

import pytest

from beacon import settlement as st
from beacon.settlement import SettlementError


def hex_with(s, resource):
    return next(i for i, h in enumerate(s.hexes) if h.resource == resource)


def test_a_new_city_has_its_hexes_slots_and_a_flowing_start(cfg):
    s = st.new(cfg, 3)
    assert len(s.hexes) == 7 and s.hexes[0].buildings == ["city_hall"]
    assert {h.resource for h in s.hexes[1:]} == {"grain", "timber", "stone", "iron"}
    assert st.harvest(cfg, s)["grain"] > 0 and st.harvest(cfg, s)["timber"] > 0
    assert st.new(cfg, 3) == s  # seeded
    assert st.from_json(st.to_json(s)) == s
    # each ring hex has three edges on the border; the centre none
    assert st.outer_edges(s, 0) == [] and all(len(st.outer_edges(s, i)) == 3 for i in range(1, 7))


def test_building_costs_materials_now_and_labour_over_turns(cfg):
    s = st.new(cfg, 3)
    stone = hex_with(s, "stone")
    timber = s.goods["timber"]
    st.build(cfg, s, stone, "quarry")
    assert s.goods["timber"] == timber - cfg.settlement("buildings.quarry.cost.timber")
    assert "quarry" not in s.hexes[stone].buildings
    turns = 0
    while "quarry" not in s.hexes[stone].buildings:
        st.end_turn(cfg, s)
        turns += 1
    assert turns == -(-cfg.settlement("buildings.quarry.labour") // st.labour(cfg, s))
    with pytest.raises(SettlementError, match="needs a grain"):
        st.build(cfg, s, stone, "farm")
    with pytest.raises(SettlementError, match="short of"):
        st.build(cfg, s, 0, "warehouse")
    st.end_turn(cfg, s)
    assert st.harvest(cfg, s)["stone"] == cfg.settlement("buildings.quarry.makes.stone")


def test_slots_fill_up(cfg):
    s = st.new(cfg, 3)
    s.goods["timber"] = 100
    forest = next(i for i, h in enumerate(s.hexes) if h.resource == "timber" and not h.buildings)
    for _ in range(s.hexes[forest].slots):
        st.build(cfg, s, forest, "house")
    assert st.build_problem(cfg, s, forest, "house") == "no free slot on this hex"


def test_people_eat_grow_and_go_hungry_and_workers_staff_buildings(cfg):
    s = st.new(cfg, 3)
    p = cfg.settlement("people")
    s.goods["grain"] = 200
    pop = s.pop
    st.end_turn(cfg, s)
    assert s.pop == pop + 1
    s.goods["grain"] = 0
    for h in s.hexes:  # remove the farm so nothing is grown
        h.buildings = [b for b in h.buildings if b != "farm"]
    events = st.end_turn(cfg, s)
    assert any(e["kind"] == "hunger" for e in events) and s.pop == pop
    s.pop = 1  # one worker: only the first producer is staffed
    assert len(st.staffed(cfg, s)) == 1 and p["eats"] == 2


def test_storage_caps_lose_the_excess(cfg):
    s = st.new(cfg, 3)
    s.goods["timber"] = st.caps(cfg, s)["timber"]
    events = st.end_turn(cfg, s)
    assert s.goods["timber"] == st.caps(cfg, s)["timber"]
    assert any(e["kind"] == "spoiled" for e in events)
    s.hexes[0].buildings.append("warehouse")
    assert st.caps(cfg, s)["timber"] > cfg.settlement("goods.timber.cap")


def test_walls_hold_a_raid_and_a_bare_hex_is_broken(cfg):
    s = st.new(cfg, 3)
    s.raid_hex, s.next_raid = 1, 0
    s.goods.update(timber=200, stone=200, iron=100)
    for d in st.outer_edges(s, 1):
        st.wall(cfg, s, 1, d, "stone")
    for o in list(s.queue):  # finish them now
        s.walls[f"{o.hex}:{o.edge}"] = {"material": o.what, "hp": cfg.settlement("walls.stone.hp")}
    s.queue = []
    events = st.end_turn(cfg, s)
    raid = next(e for e in events if e["kind"] == "raid")
    assert raid["held"] and raid["defence"] >= raid["strength"]
    assert all(w["hp"] < cfg.settlement("walls.stone.hp") for w in s.walls.values())
    # a bare hex with a building: broken, the building wrecked, stores burned
    s2 = st.new(cfg, 3)
    farm = next(i for i, h in enumerate(s2.hexes) if "farm" in h.buildings)
    s2.raid_hex, s2.next_raid, s2.raids = farm, 0, 5
    grain = s2.goods["grain"]
    events = st.end_turn(cfg, s2)
    raid = next(e for e in events if e["kind"] == "raid")
    assert not raid["held"] and raid["wrecked"] == "farm" and "farm" not in s2.hexes[farm].buildings
    assert raid["burned"] and s2.goods["grain"] < grain + 20


def test_raids_are_seen_two_turns_ahead(cfg):
    s = st.new(cfg, 3)
    r = cfg.settlement("raids")
    seen = []
    for _ in range(r["first"]):
        events = st.end_turn(cfg, s)
        seen += [e for e in events if e["kind"] == "raid_coming"]
    assert len(seen) == r["warning"]


def test_hardening_a_wall_and_the_upgrade_rule(cfg):
    s = st.new(cfg, 3)
    s.goods.update(timber=100, stone=100, iron=50)
    edge = st.outer_edges(s, 1)[0]
    s.walls = {f"1:{edge}": {"material": "stone", "hp": cfg.settlement("walls.stone.hp")}}
    assert st.wall_problem(cfg, s, 1, edge, "wood") == "this wall is already as strong"
    assert st.wall_problem(cfg, s, 1, edge, "iron") is None
    assert st.wall_problem(cfg, s, 0, 0, "wood") == "walls stand on the territory's outer edges"


def test_the_exchange_buys_low_sells_high_and_drifts(cfg):
    s = st.new(cfg, 3)
    q = st.quotes(cfg, s)["timber"]
    assert q["sell"] < q["buy"]
    gold = s.gold
    st.trade(cfg, s, "timber", 20, "sell")
    assert s.gold == gold + 20 * q["sell"] and s.prices["timber"] < 100
    with pytest.raises(SettlementError, match="gold"):
        st.trade(cfg, s, "iron", 50, "buy")
    st.trade(cfg, s, "grain", 10, "buy")
    seen = set()
    for _ in range(5):
        st.end_turn(cfg, s)
        seen.add(tuple(sorted(s.prices.items())))
    assert len(seen) > 1  # prices drift (seeded), within bounds
    ex = cfg.settlement("exchange")
    assert all(ex["min_pct"] <= v <= ex["max_pct"] for v in s.prices.values())


def test_cancel_returns_materials(cfg):
    s = st.new(cfg, 3)
    timber = s.goods["timber"]
    st.build(cfg, s, hex_with(s, "stone"), "quarry")
    st.cancel(cfg, s, 0)
    assert s.goods["timber"] == timber and not s.queue


def test_sandbox_session(cfg):
    from web.sandbox import Sandbox

    box = Sandbox(cfg, 5)
    v = box.view()
    assert v["turn"] == 0 and len(v["hexes"]) == 7 and "farm" in v["buildings"]
    bad = box.command({"kind": "build", "hex": 0, "what": "farm"})
    assert bad["ok"] is False and "grain" in bad["error"]
    assert box.command({"kind": "end_turn"})["ok"] and box.view()["turn"] == 1
