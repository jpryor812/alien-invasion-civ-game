"""The survivor start (docs/SPEC_M14.md, designer 2026-11-15).

Each player begins as a band - the leader (30 attack) and four survivors (20 each), homeless.
The first alien-held town of its continent the band finds becomes its first town (designer
2026-11-17): lightly held, and 100 gold to its resistance halves it. The old capital, a few hexes
away, is lightly held from the start; any other town is weakened the same way when found.
Caches nearby hold weapons, armor, alien weapons, more survivors and scrap. Taking the town
makes it the capital and starts the normal game: survivors become citizens (those carrying gear
stay as units), the leader leaves the map to lead from the capital, scrap becomes production. If
the leader falls first, it escapes to the band's starting hex with two new survivors.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid, rng
from beacon.config import Config
from beacon.state import ACTIVE, ALIENS, OVERRUN, City, GameState, Unit
from beacon.tiles import is_passable_land

Events = list[dict[str, Any]]
WEAPONS = ("weapon", "alien_weapon")
ARMOUR = ("armour",)


def settings(cfg: Config) -> dict[str, Any]:
    return cfg.t("survivor")


def is_band(cfg: Config, unit: Unit) -> bool:
    return bool(cfg.units[unit.type].get("survivor"))


def gear_bonus(cfg: Config, unit: Unit, defending: bool) -> int:
    loot = settings(cfg)["loot"]
    key = "defence" if defending else "attack"
    return sum(loot[g].get(key, 0) for g in unit.gear if g in loot)


# -- setting up ----------------------------------------------------------------------------------


def _free(state: GameState, cfg: Config, tile: int, taken: set[int]) -> bool:
    t = state.tiles[tile]
    return (
        tile not in taken
        and is_passable_land(cfg, t)
        and state.city_at(tile) is None
        and not state.units_at(tile)
        and t.nest is None
        and all(s.tile != tile for s in state.sites.values())
    )


def setup(state: GameState, cfg: Config) -> None:
    """Turn a classic start into a survivor start (called by new_game)."""
    from beacon.units import create_unit, place_unit, remove_unit

    sv = settings(cfg)
    loot = sv["loot"]
    kinds = sorted(loot)
    gear_kinds = [k for k in kinds if loot[k].get("attack") or loot[k].get("defence")]
    for unit in [u for u in state.sorted_units() if u.owner in state.players]:
        remove_unit(state, unit)
    taken: set[int] = set()
    for pid in state.player_ids():
        player = state.players[pid]
        mine = [c for c in state.cities if c.owner == pid]
        capital = next(c for c in mine if c.is_capital)
        for city in mine:  # every city the player held is now alien-held
            city.status, city.owner = OVERRUN, ALIENS
            city.queue, city.progress, city.border = [], {}, []
        from beacon.cities import max_hp

        capital.is_capital = False  # a small, lightly held town; it becomes the capital when freed
        capital.pop = min(capital.pop, sv["town_pop"])
        capital.hp = max_hp(cfg, capital) * sv["town_hp_pct"] // 100
        for t in sv["town_garrison"]:
            place_unit(state, cfg, t, ALIENS, capital.tile, 0)
        for city in mine:
            if city is not capital and not state.units_at(city.tile):
                place_unit(state, cfg, cfg.t("aliens.garrison.list")[0], ALIENS, city.tile, 0)
        player.founded, player.band_town = False, capital.id
        for city in mine:  # the band must find its old towns again (designer 2026-11-16)
            player.known_cities.pop(str(city.id), None)
            # the aliens wrecked the radio and the barracks: rebuilding them comes first
            # (SPEC_M14 revision; the barracks since SPEC_M16)
            wrecked = {cfg.t("contact.radio_building"), cfg.materials("barracks.building")}
            city.wrecked = sorted(set(city.buildings) & wrecked)  # free to repair (SPEC_M20)
            city.buildings = [b for b in city.buildings if b not in wrecked]
            city.layout = []
        r = rng.stream(state.seed, "map", "band", pid)
        ring = [
            i
            for i in hexgrid.within(capital.tile, sv["band_distance"], state.width, state.height)
            if hexgrid.distance(i, capital.tile, state.width) == sv["band_distance"]
            and state.tiles[i].continent == pid
            and _free(state, cfg, i, taken)
        ]
        home = r.choice(sorted(ring)) if ring else capital.tile
        player.band_home = home
        band: list[Unit] = []
        for entry in sv["band"]:
            for _ in range(entry["count"]):
                unit = place_unit(state, cfg, entry["type"], pid, home, 1)
                if unit is None:
                    unit = place_unit(state, cfg, entry["type"], pid, home, 2)
                if unit is None:
                    unit = create_unit(state, cfg, entry["type"], pid, home)
                band.append(unit)
                taken.add(unit.tile)
        # caches lie just out of the band's sight (none beside it), nearer than the town, so the
        # band finds gear before it finds the town (designer 2026-11-16); the rest by weight
        from beacon.fog import visible_tiles

        sight = visible_tiles(state, cfg, pid)
        to_town = hexgrid.distance(home, capital.tile, state.width)
        area = [
            i
            for i in hexgrid.within(home, sv["radius"], state.width, state.height)
            if state.tiles[i].continent == pid
            and i not in sight
            and hexgrid.distance(i, capital.tile, state.width) >= 3
            and all(hexgrid.distance(i, u.tile, state.width) >= 2 for u in band)
            and _free(state, cfg, i, taken)
        ]
        r.shuffle(area)
        edge = [
            i
            for i in area
            if hexgrid.distance(i, home, state.width) < to_town
            and any(n in sight for n in hexgrid.neighbours(i, state.width, state.height))
        ]
        if len(edge) < sv["near_caches"]:  # crowded by coast or cities: the nearest unseen hexes
            near = sorted(
                (i for i in area if i not in edge),
                key=lambda i: (hexgrid.distance(i, home, state.width), i),
            )
            edge += near[: sv["near_caches"] - len(edge)]
        chosen = edge[: sv["near_caches"]]
        rest = [i for i in area if i not in chosen]
        chosen += rest[: max(0, sv["caches"] - len(chosen))]
        for k, i in enumerate(chosen):
            if k < sv["near_caches"]:
                kind = r.choice(sorted(g for g in gear_kinds if g != "alien_weapon"))
            else:
                kind = rng.weighted_choice(r, kinds, [loot[x]["weight"] for x in kinds])
            state.caches[str(i)] = kind
            taken.add(i)
        # more crates across the rest of the continent (designer 2026-11-19, SPEC_M20)
        wide = sorted(
            i
            for i, t in enumerate(state.tiles)
            if t.continent == pid
            and i not in taken
            and hexgrid.distance(i, home, state.width) > sv["radius"]
            and all(hexgrid.distance(i, c.tile, state.width) >= 2 for c in state.cities)
            and _free(state, cfg, i, taken)
        )
        r.shuffle(wide)
        for i in wide[: sv["scatter"]]:
            if all(
                hexgrid.distance(i, j, state.width) >= 3 for j in taken if str(j) in state.caches
            ):
                state.caches[str(i)] = rng.weighted_choice(
                    r, kinds, [loot[x]["weight"] for x in kinds]
                )
                taken.add(i)


def _weaken(state: GameState, cfg: Config, city: City) -> None:
    """Make a found town as lightly held as the old capital: few people, worn walls, a small
    garrison, no radio or barracks, no nests feeding it."""
    from beacon.cities import max_hp
    from beacon.units import place_unit, remove_unit

    sv = settings(cfg)
    city.is_capital = False
    city.pop = min(city.pop, sv["town_pop"])
    city.hp = min(city.hp, max_hp(cfg, city) * sv["town_hp_pct"] // 100)
    for u in [u for u in state.units_at(city.tile) if u.owner == ALIENS]:
        remove_unit(state, u)
    for t in sv["town_garrison"]:
        place_unit(state, cfg, t, ALIENS, city.tile, 0)
    wrecked = {cfg.t("contact.radio_building"), cfg.materials("barracks.building")}
    city.wrecked = sorted(set(city.wrecked) | {cfg.t("contact.radio_building")})  # SPEC_M20
    city.buildings = [b for b in city.buildings if b not in wrecked]
    city.layout = []
    for t in state.tiles:
        if t.nest == city.id:
            t.nest = None


def claim_town(state: GameState, cfg: Config, pid: str) -> Events:
    """The first alien-held town of its own continent that a homeless band finds becomes its
    first town (designer 2026-11-17). The old capital if it is among those found, else the one
    nearest the band."""
    player = state.players.get(pid)
    if player is None or player.founded or player.band_claimed:
        return []
    found = [
        state.cities[int(k)]
        for k in sorted(player.known_cities, key=int)
        if state.cities[int(k)].status == OVERRUN and state.cities[int(k)].continent == pid
    ]
    if not found:
        return []
    band = [u for u in state.sorted_units() if u.owner == pid and is_band(cfg, u)]
    if any(c.id == player.band_town for c in found):
        town = state.cities[player.band_town]
    else:
        here = band[0].tile if band else found[0].tile
        town = min(found, key=lambda c: (hexgrid.distance(here, c.tile, state.width), c.id))
        _weaken(state, cfg, town)
    player.band_town, player.band_claimed = town.id, True
    return [{"turn": state.turn, "kind": "first_town_found", "player": pid, "city": town.id}]


def _memory(state: GameState, city: City):
    from beacon.state import CityMemory

    return CityMemory(status=city.status, owner=city.owner, pop=city.pop, turn_seen=state.turn)


# -- loot ----------------------------------------------------------------------------------------


def _give(cfg: Config, unit: Unit, item: str) -> bool:
    """Equip `item` if its slot is free or it is better; True if equipped."""
    loot = settings(cfg)["loot"]
    slot = WEAPONS if item in WEAPONS else ARMOUR
    have = [g for g in unit.gear if g in slot]
    if not have:
        unit.gear = [*unit.gear, item]
        return True
    key = "attack" if slot is WEAPONS else "defence"
    if loot[item].get(key, 0) > loot[have[0]].get(key, 0):
        unit.gear = [g for g in unit.gear if g != have[0]] + [item]
        return True
    return False


def pick_up(state: GameState, cfg: Config) -> Events:
    """Any player unit standing on a cache takes it."""
    from beacon.units import place_unit

    events: Events = []
    loot = settings(cfg)["loot"]
    for key in sorted(state.caches, key=int):
        tile = int(key)
        here = [u for u in state.units_at(tile) if u.owner in state.players]
        if not here:
            continue
        unit = here[0]
        kind = state.caches.pop(key)
        got = kind.replace("_", " ")
        if kind not in ("scrap", "food"):
            state.players[unit.owner].band_finds += 1  # opens the town's barricades
        if kind in WEAPONS or kind in ARMOUR:
            from beacon.armoury import carries_only, pack_size

            band = [u for u in state.sorted_units() if u.owner == unit.owner and is_band(cfg, u)]
            band = sorted(band, key=lambda u: (hexgrid.distance(u.tile, tile, state.width), u.id))
            takers = band if carries_only(cfg, unit) and not is_band(cfg, unit) else [unit, *band]
            if state.players[unit.owner].founded:  # the band is gone: the finder decides
                takers = [] if carries_only(cfg, unit) else [unit]
            if not any(_give(cfg, u, kind) for u in takers if u.owner == unit.owner):
                if len(unit.pack) < pack_size(cfg):  # carried to a town's armoury (SPEC_M20)
                    unit.pack = [*unit.pack, kind]
                    got += " (carried home for the armory)"
                else:
                    got += " (nobody could use or carry it)"
        elif kind == "survivor":
            new = place_unit(state, cfg, "survivor", unit.owner, tile, 4)
            got = "a survivor joins" if new is not None else "a survivor (no room to stand)"
        elif kind == "food":  # rations for everyone near (SPEC_M18)
            from beacon.food import refill_near

            n = refill_near(state, cfg, unit.owner, tile, loot["food"]["radius"])
            got = f"food - rations refilled for {n} unit{'s' if n != 1 else ''}"
        elif kind == "scrap":
            state.players[unit.owner].scrap += loot["scrap"]["scrap"]
            got = f"{loot['scrap']['scrap']} scrap"
        events.append(
            {
                "turn": state.turn,
                "kind": "loot_found",
                "player": unit.owner,
                "tile": tile,
                "loot": kind,
                "result": [got],
                "unit": unit.id,
            }
        )
    return events


# -- the first town ------------------------------------------------------------------------------


def found(state: GameState, cfg: Config, city: City, pid: str) -> Events:
    """The band takes its first town: the normal game begins."""
    from beacon import citizens
    from beacon.units import place_unit, remove_unit

    sv = settings(cfg)
    player = state.players[pid]
    player.founded, player.band_town, player.band_claimed = True, city.id, True
    band = [u for u in state.sorted_units() if u.owner == pid and is_band(cfg, u)]
    joined = 0  # survivors stay in the field as survivors (designer 2026-11-22, SPEC_M22)
    for u in band:
        if u.type == "band_leader":
            remove_unit(state, u)  # the leader joins the town and leads from it
    city.pop = max(city.pop, sv["town_rescued"])  # the rescued (SPEC_M18)
    citizens.sync(state, cfg, city)
    city.production_store += player.scrap
    from beacon import layout, materials  # SPEC_M16

    materials.start_stores(cfg, city)
    layout.ensure(state, cfg, city)
    from beacon import works  # the town's first crew (SPEC_M17)

    city.engineers = -1
    works.ensure_crew(cfg, city, cfg.materials("labour.town_start"))
    scrap, player.scrap = player.scrap, 0
    for t in sv["founding_units"]:
        place_unit(state, cfg, t, pid, city.tile, cfg.t("cities.work_radius"))
    for t in cfg.t("start.city_units.list"):
        place_unit(state, cfg, t, pid, city.tile, 0)
    return [
        {
            "turn": state.turn,
            "kind": "first_city",
            "player": pid,
            "city": city.id,
            "citizens": joined,
            "scrap": scrap,
        }
    ]


def escape(state: GameState, cfg: Config) -> Events:
    """A band that lost its leader before its first town: the leader escapes with survivors."""
    from beacon.units import place_unit

    sv = settings(cfg)
    events: Events = []
    for pid in state.player_ids():
        player = state.players[pid]
        if player.founded or player.band_home is None:
            continue
        if any(u.owner == pid and u.type == "band_leader" for u in state.units.values()):
            continue
        place_unit(state, cfg, "band_leader", pid, player.band_home, 4)
        for _ in range(sv["escape_survivors"]):
            place_unit(state, cfg, "survivor", pid, player.band_home, 4)
        events.append({"turn": state.turn, "kind": "leader_escaped", "player": pid})
    return events


def barricades_hold(state: GameState, cfg: Config, city: City, pid: str) -> bool:
    """A band's first town holds (cannot fall below 1 HP) until the band has found a weapon,
    armor or another survivor (designer: not without an upgrade or an extra citizen)."""
    player = state.players.get(pid)
    if player is None or player.founded or player.band_town != city.id or not player.band_claimed:
        return False
    # designer 2026-11-17: funding its resistance is required - the people open the gates
    return city.funded_pct == 0


def town_of(state: GameState, pid: str) -> City | None:
    player = state.players[pid]
    if player.founded or player.band_town is None:
        return None
    town = state.cities[player.band_town]
    if town.status == ACTIVE:
        return None
    return town
