"""M1: map generation, cities, starting roads, fog and views."""

from __future__ import annotations

import pytest

from beacon import canonical, fog, hexgrid
from beacon.game import new_game
from beacon.paths import reachable
from beacon.state import ACTIVE, ALIENS, DORMANT, EMPTY, OVERRUN, bits_get, to_dict
from beacon.tiles import is_passable_land, is_water
from beacon.view import PlayerView, observe

# Update deliberately (and say why in the commit) when map generation or the data changes.
GOLDEN_MAP_SEED_1 = "1ebdb2b5797d0320aaf6d23b4d06466e5424ba971feb37b4d5c5ccdda024e205"


MAP_CITY_FIELDS = ("id", "name", "continent", "tile", "status", "owner", "pop", "is_capital")


def map_digest(state) -> str:
    """Digest of what map generation decides (not of later economy fields)."""
    cities = [{k: to_dict(c)[k] for k in MAP_CITY_FIELDS} for c in state.cities]
    return canonical.digest({"tiles": to_dict(state)["tiles"], "cities": cities})


@pytest.fixture(scope="module")
def world(cfg):
    return new_game(cfg, seed=1)


def test_same_seed_same_map_different_seed_different_map(cfg, world):
    assert map_digest(new_game(cfg, seed=1)) == map_digest(world)
    assert map_digest(new_game(cfg, seed=2)) != map_digest(world)


def test_golden_map_digest(world):
    assert map_digest(world) == GOLDEN_MAP_SEED_1


def test_continents_are_single_landmasses_near_target(cfg, world):
    w, h = world.width, world.height
    for cid in cfg.continent_ids():
        land = [i for i, t in enumerate(world.tiles) if t.continent == cid and not is_water(cfg, t)]
        target = cfg.t("map.land_tiles") * cfg.continents[cid]["land_pct"] // 100
        assert abs(len(land) - target) * 10 <= target, cid
        land_set = set(land)
        assert (
            reachable(land[0], lambda i: hexgrid.neighbours(i, w, h), land_set.__contains__)
            == land_set
        )
        passable = {i for i in land if is_passable_land(cfg, world.tiles[i])}
        first = min(passable)
        assert (
            reachable(first, lambda i: hexgrid.neighbours(i, w, h), passable.__contains__)
            == passable
        )


def test_cities_placed_spaced_and_known(cfg, world):
    min_d = cfg.t("cities.min_distance")
    for cid in cfg.continent_ids():
        mine = [c for c in world.cities if c.continent == cid]
        assert len(mine) >= 18
        active = [c for c in mine if c.status == ACTIVE]
        assert len(active) == cfg.t("cities.known_count")
        assert sum(c.is_capital for c in mine) == 1
        assert all(c.owner == cid for c in active)
    for a in world.cities:
        assert world.tiles[a.tile].city == a.id
        assert is_passable_land(cfg, world.tiles[a.tile])
        for b in world.cities:
            if a.id < b.id:
                assert hexgrid.distance(a.tile, b.tile, world.width) >= min_d


def test_capital_joined_to_known_cities_by_road(cfg, world):
    w, h = world.width, world.height
    city_tiles = {c.tile for c in world.cities}
    for pid in world.player_ids():
        capital = next(c for c in world.cities if c.owner == pid and c.is_capital)
        net = reachable(
            capital.tile,
            lambda i: hexgrid.neighbours(i, w, h),
            lambda i: world.tiles[i].route is not None or i in city_tiles,
        )
        for city in world.cities:
            if city.owner == pid:
                assert city.tile in net, city.name


def test_all_lost_states_occur_and_overrun_cities_are_garrisoned(cfg):
    for seed in (1, 2, 3):
        state = new_game(cfg, seed=seed)
        statuses = {c.status for c in state.cities}
        assert {ACTIVE, DORMANT, EMPTY, OVERRUN} <= statuses
        for city in state.cities:
            here = state.units_at(city.tile)
            if city.status == OVERRUN:
                assert city.owner == ALIENS
                assert here and here[0].owner == ALIENS
            elif city.status in (DORMANT, EMPTY):
                assert city.owner is None


def test_starting_units_near_capital(cfg, world):
    radius = cfg.t("cities.work_radius")
    expected = sum(e["count"] for e in cfg.t("start.units.list"))
    for pid in world.player_ids():
        capital = next(c for c in world.cities if c.owner == pid and c.is_capital)
        mine = [u for u in world.units.values() if u.owner == pid]
        assert len(mine) == expected
        assert all(hexgrid.distance(u.tile, capital.tile, world.width) <= radius for u in mine)


def test_view_hides_unexplored_tiles_and_unseen_units(cfg, world):
    pid = "europe"
    view = PlayerView(world, cfg, pid)
    explored = view.explored_tiles()
    assert 0 < len(explored) < len(world.tiles) // 6
    assert all(view.is_explored(t) for t in view.visible)
    hidden = next(i for i in range(len(world.tiles)) if not view.is_explored(i))
    assert view.tile(hidden) is None
    for unit in view.visible_units():
        assert unit.owner == pid or unit.tile in view.visible
    far_aliens = [
        u for u in world.units.values() if u.owner == ALIENS and u.tile not in view.visible
    ]
    assert far_aliens
    seen_ids = {u["id"] for u in observe(world, cfg, pid)["units"]}
    assert not seen_ids & {u.id for u in far_aliens}


def test_lost_cities_unknown_until_seen(cfg, world):
    pid = "asia"
    player = world.players[pid]
    for city in world.cities:
        known = str(city.id) in player.known_cities
        if city.owner == pid:
            assert known
        elif city.continent != pid:
            assert not known


def test_exploring_grows_memory_and_fog_returns(cfg):
    state = new_game(cfg, seed=4)
    pid = "africa"
    recon = next(u for u in state.units.values() if u.owner == pid and u.type == "recon_team")
    before = bin(bits_get(state.players[pid].explored)).count("1")
    target = next(
        c
        for c in state.cities
        if c.continent == pid and str(c.id) not in state.players[pid].known_cities
    )
    start = recon.tile
    recon.tile = target.tile
    fog.refresh(state, cfg, pid)
    assert str(target.id) in state.players[pid].known_cities
    after = bin(bits_get(state.players[pid].explored)).count("1")
    assert after > before
    recon.tile = start
    view = PlayerView(state, cfg, pid)
    assert view.is_explored(target.tile) and not view.is_visible(target.tile)
    assert target.id in view.known_cities()
