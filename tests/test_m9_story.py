"""M9 steps 1-3: events, exploration finds and Starfall (docs/SPEC_M9.md)."""

from __future__ import annotations

import pytest
from test_m3_units_combat import EU, add_city, arena, at, east

from beacon import starfall, story
from beacon.actions import apply_command, pending_decisions
from beacon.commands import ChooseStory, CommandError, MoveUnit
from beacon.game import new_game
from beacon.runner import play
from beacon.state import ACTIVE, ALIENS, Shard, Site
from beacon.units import create_unit


def test_every_continent_gets_finds_away_from_cities(cfg):
    s = new_game(cfg, seed=3)
    per = cfg.story("sites.per_continent")
    for cid in cfg.continent_ids():
        mine = [x for x in s.sites.values() if s.tiles[x.tile].continent == cid]
        assert len(mine) == per
    gap = cfg.story("sites.min_city_distance")
    from beacon import hexgrid

    for x in s.sites.values():
        assert all(hexgrid.distance(x.tile, c.tile, s.width) >= gap for c in s.cities)


def test_a_find_fires_when_a_unit_walks_onto_it(cfg):
    s = arena(cfg)
    add_city(s, cfg, at(2, 2), ACTIVE, EU, pop=2)
    find = at(6, 4)
    s.sites["900"] = Site(id=900, tile=find, kind="supply_cache")
    inf = create_unit(s, cfg, "infantry", EU, east(find, -1))
    gold = s.players[EU].gold
    events = apply_command(s, cfg, MoveUnit(player=EU, unit=inf.id, target=find))
    assert {"site_found", "story_event"} <= {e["kind"] for e in events}
    assert s.players[EU].gold == gold + 60 and s.sites["900"].found_by == EU


def test_a_choice_event_waits_and_applies_the_choice(cfg):
    s = arena(cfg)
    city = add_city(s, cfg, at(2, 2), ACTIVE, EU, pop=2)
    events = story.fire(s, cfg, EU, "survivor_camp", at(5, 5))
    sid = events[0]["story"]
    assert {"kind": "story_choice", "story": sid, "event": "survivor_camp"} in pending_decisions(
        s, cfg, EU
    )
    with pytest.raises(CommandError):
        apply_command(s, cfg, ChooseStory(player=EU, story=sid, choice=7))
    apply_command(s, cfg, ChooseStory(player=EU, story=sid, choice=0))  # take them home
    assert city.pop == 3 and not story.pending(s, EU)


def test_wreckage_gives_100_science_once(cfg):
    s = arena(cfg)
    add_city(s, cfg, at(2, 2), ACTIVE, EU, pop=2)
    before = s.players[EU].research_progress
    story.fire(s, cfg, EU, "ship_wreckage", at(5, 5))
    assert s.players[EU].research_progress == before + 100


def test_shard_is_mined_and_claimed_by_engineers_not_soldiers(cfg):
    s = arena(cfg)
    add_city(s, cfg, at(1, 1), ACTIVE, EU, pop=2)
    tile = at(8, 5)
    s.shards["1"] = Shard(
        id=1,
        kind="starmetal",
        tile=tile,
        warn_turn=0,
        impact_turn=0,
        cone_center=tile,
        cone_radius=5,
    )
    s.next_shard_turn = 10_000
    create_unit(s, cfg, "infantry", EU, tile)  # soldiers guard but cannot mine
    starfall.end_of_turn(s, cfg)
    assert s.shards["1"].progress == {}
    create_unit(s, cfg, "engineers", EU, tile)
    events = []
    for _ in range(cfg.story("starfall.mine_turns")):
        events += starfall.end_of_turn(s, cfg)
    claimed = [e for e in events if e["kind"] == "shard_claimed"]
    assert claimed and claimed[0]["by"] == EU
    assert s.players[EU].boons and s.players[EU].boons[0]["shard"] == "starmetal"


def test_aliens_can_claim_a_shard_and_get_tech_progress(cfg):
    s = arena(cfg)
    tile = at(8, 5)
    s.shards["1"] = Shard(
        id=1,
        kind="new_elements",
        tile=tile,
        warn_turn=0,
        impact_turn=0,
        cone_center=tile,
        cone_radius=5,
    )
    s.next_shard_turn = 10_000
    create_unit(s, cfg, "alien_drone", ALIENS, tile)
    before = s.aliens.progress
    for _ in range(cfg.story("starfall.mine_turns")):
        starfall.end_of_turn(s, cfg)
    assert s.shards["1"].claimed_by == ALIENS and s.aliens.progress > before


def test_later_shards_are_worth_more(cfg):
    early = starfall.reward(cfg, "starmetal", 20)["yield_pct"]["production"]
    late = starfall.reward(cfg, "starmetal", 200)["yield_pct"]["production"]
    assert late > early


def test_shards_fall_and_get_raced_in_an_ai_game(cfg):
    s, events, _ = play(cfg, seed=1, turns=100, driver="ai")
    kinds = [e["kind"] for e in events]
    assert "shard_warning" in kinds and "shard_landed" in kinds
    assert any(e["kind"] == "shard_claimed" for e in events)
    assert any(e["kind"] == "site_found" for e in events)
