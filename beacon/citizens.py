"""Citizens (designer, 2026-11-14).

- A city's population is its citizens. A newborn is a child: it eats but does nothing until it
  grows up, faster when the city has more food to spare.
- Each citizen has 6 stat points over the six domains (+1 everywhere, +3 in two or +2 in three)
  and maybe one trait.
- A grown citizen either works one improved tile of its city (bare tiles yield nothing), adding
  half its stats to that tile, or sits on the continent council (the same seats as alien
  recruits), adding its full stats to its home city. Military counts only on the council, as
  city strength.
- Each citizen's job is "auto" (the game places it), "council" or a chosen tile. Auto citizens
  take the best free improved tile for the city's focus; with none left they take a free council
  seat. Recruits always come first: auto citizens give up their seats to them.
"""

from __future__ import annotations

from typing import Any

from beacon import rng
from beacon.cities import work_tiles
from beacon.config import DOMAINS, YIELDS, Config
from beacon.state import ACTIVE, Citizen, City, GameState
from beacon.tiles import tile_yields
from beacon.units import hostile, occupancy

Events = list[dict[str, Any]]
GENERAL = "general"


def of_city(state: GameState, city_id: int) -> list[Citizen]:
    return sorted((c for c in state.citizens.values() if c.city == city_id), key=lambda c: c.id)


def of_player(state: GameState, pid: str) -> list[Citizen]:
    return sorted(
        (c for c in state.citizens.values() if state.cities[c.city].owner == pid),
        key=lambda c: c.id,
    )


def trait(cfg: Config, c: Citizen, key: str, default: int) -> int:
    traits = cfg.t("citizens.traits")
    for t in c.traits:
        if key in traits.get(t, {}):
            return traits[t][key]
    return default


# -- birth, growing up, death ------------------------------------------------------------------


def make(state: GameState, cfg: Config, city: City, adult: bool) -> Citizen:
    cid = state.new_id()
    r = rng.stream(state.seed, "citizen", cid)
    stats_cfg = cfg.t("citizens.stats")
    patterns = stats_cfg["patterns"]
    pat = rng.weighted_choice(r, patterns, [p["weight"] for p in patterns])
    chosen = r.sample(list(DOMAINS), pat["picks"])
    stats = {d: pat["each"] for d in DOMAINS if d in chosen}
    traits = []
    if rng.percent_roll(r, cfg.t("citizens.trait_pct")):
        traits = [r.choice(sorted(cfg.t("citizens.traits")))]
    name = r.choice(cfg.t("citizens.names.list"))
    needed = cfg.t("citizens.growing_up.needed")
    citizen = Citizen(
        id=cid,
        city=city.id,
        name=name,
        stats=stats,
        traits=traits,
        born=state.turn,
        growth=needed if adult else 0,
        adult=adult,
    )
    state.citizens[str(cid)] = citizen
    return citizen


def remove_youngest(state: GameState, city: City) -> None:
    mine = of_city(state, city.id)
    if mine:
        del state.citizens[str(mine[-1].id)]


def sync(state: GameState, cfg: Config, city: City) -> None:
    """Keep a player city's citizens equal to its population (new ones are grown up: they come
    from liberation or the start). Cities not held by a player have no citizens."""
    mine = of_city(state, city.id)
    if city.status != ACTIVE or city.owner not in state.players:
        for c in mine:
            del state.citizens[str(c.id)]
        return
    for _ in range(city.pop - len(mine)):
        make(state, cfg, city, adult=True)
    for _ in range(len(mine) - city.pop):
        remove_youngest(state, city)


def born(state: GameState, cfg: Config, city: City) -> dict[str, Any]:
    c = make(state, cfg, city, adult=False)
    return {
        "kind": "citizen_born",
        "city": city.id,
        "citizen": c.id,
        "name": c.name,
        "stats": dict(c.stats),
        "traits": list(c.traits),
    }


def grow(state: GameState, cfg: Config, city: City, surplus_food: int) -> Events:
    g = cfg.t("citizens.growing_up")
    events: Events = []
    for c in of_city(state, city.id):
        if c.adult:
            continue
        gain = (g["base"] + g["per_food"] * max(0, surplus_food)) * trait(cfg, c, "grow_pct", 100)
        c.growth += gain // 100
        if c.growth >= g["needed"]:
            c.growth = g["needed"]
            c.adult = True
            events.append(
                {"kind": "citizen_grew_up", "city": city.id, "citizen": c.id, "name": c.name}
            )
    return events


def turns_to_grow(cfg: Config, c: Citizen, surplus_food: int) -> int:
    g = cfg.t("citizens.growing_up")
    gain = (g["base"] + g["per_food"] * max(0, surplus_food)) * trait(cfg, c, "grow_pct", 100)
    gain = max(1, gain // 100)
    return -(-max(0, g["needed"] - c.growth) // gain)


def food_eaten(state: GameState, cfg: Config, city: City) -> int:
    extra = sum(trait(cfg, c, "food_eaten", 0) for c in of_city(state, city.id))
    return max(0, city.pop * cfg.t("economy.food_per_pop") + extra)


# -- what a citizen gives ----------------------------------------------------------------------


def tile_bonus(cfg: Config, c: Citizen) -> dict[str, int]:
    """What a citizen adds on a tile, in hundredths (half of +3 is 150: +1.5, not rounded; the
    city carries the fraction from turn to turn)."""
    rate = trait(cfg, c, "tile_rate_pct", cfg.t("citizens.tile_rate_pct"))
    out = {y: c.stats.get(y, 0) * rate for y in YIELDS}
    out["beacon"] += trait(cfg, c, "beacon_flat", 0) * 100
    return out


def _counts_on_council(c: Citizen, domain: str) -> bool:
    """A general seat applies every stat; a domain seat only its own domain (as for recruits)."""
    return GENERAL in c.seats or domain in c.seats


def council_bonus(cfg: Config, c: Citizen) -> dict[str, int]:
    pct = trait(cfg, c, "council_pct", 100)
    out = {y: c.stats.get(y, 0) * pct // 100 if _counts_on_council(c, y) else 0 for y in YIELDS}
    out["beacon"] += trait(cfg, c, "beacon_flat", 0)
    return out


def council_military(cfg: Config, c: Citizen) -> int:
    if not _counts_on_council(c, "military"):
        return 0
    pct = trait(cfg, c, "council_pct", 100)
    return c.stats.get("military", 0) * pct // 100 * cfg.t("citizens.military_strength")


def base_food(state: GameState, cfg: Config, city: City) -> int:
    """Food a city makes without workers: its own hex, the centre bonus and buildings."""
    food = tile_yields(cfg, state.tiles[city.tile])["food"]
    food += cfg.t("economy.city_center_yields").get("food", 0)
    return food + sum(cfg.buildings[b]["yields"].get("food", 0) for b in city.buildings)


def workable(state: GameState, cfg: Config, city: City) -> list[int]:
    """Improved tiles of the city's work area (bare tiles cannot be worked)."""
    return [t for t in work_tiles(state, cfg, city) if state.tiles[t].improvement]


# -- placing citizens --------------------------------------------------------------------------


def _seat_counts(state: GameState, pid: str) -> dict[str, int]:
    from beacon.recruits import recruits_of  # recruits imports economy, which imports this

    used = {GENERAL: 0, **dict.fromkeys(DOMAINS, 0)}
    for rec in recruits_of(state, pid):
        for s in rec.seats:
            used[s] += 1
    return used


def pinned_seats(state: GameState, pid: str) -> dict[str, int]:
    """Seats held by citizens the player put on the council (recruits cannot take these)."""
    used = {GENERAL: 0, **dict.fromkeys(DOMAINS, 0)}
    for c in of_player(state, pid):
        if c.job.startswith("council"):
            for s in c.seats:
                used[s] += 1
    return used


def _seat_ok(cfg: Config, used: dict[str, int], c: Citizen, seat: str) -> bool:
    rs = cfg.alien("recruits")
    if seat == GENERAL:
        return used[GENERAL] < rs["general_seats"]
    return seat in DOMAINS and c.stats.get(seat, 0) > 0 and used[seat] < rs["seats_per_domain"]


def _free_seat(cfg: Config, used: dict[str, int], c: Citizen) -> str | None:
    """The seat a citizen takes: the one the player chose ("council:<seat>") if free, else a
    general seat, else the domain of its best stat."""
    if c.job.startswith("council:") and _seat_ok(cfg, used, c, c.job[8:]):
        return c.job[8:]
    rs = cfg.alien("recruits")
    if used[GENERAL] < rs["general_seats"]:
        return GENERAL
    for d in sorted(DOMAINS, key=lambda d: (-c.stats.get(d, 0), d)):
        if c.stats.get(d, 0) > 0 and used[d] < rs["seats_per_domain"]:
            return d
    return None


def tile_score(state: GameState, cfg: Config, city: City, c: Citizen, t: int) -> int:
    weights = cfg.t("economy.focus_weights")[city.focus]
    ty, bonus = tile_yields(cfg, state.tiles[t]), tile_bonus(cfg, c)
    return sum(weights[y] * (ty[y] * 100 + bonus[y]) for y in YIELDS)


def assign(state: GameState, cfg: Config, pid: str) -> None:
    """Place every grown citizen of a player: pinned council members first, then each city's
    pinned and auto workers on its improved tiles, then auto citizens with no tile on free seats."""
    mine_cities = [c for c in state.cities if c.owner == pid]
    for city in mine_cities:
        sync(state, cfg, city)
    people = of_player(state, pid)
    for c in people:
        c.tile, c.seats = None, []
    used = _seat_counts(state, pid)
    for c in people:
        if c.adult and c.job.startswith("council"):
            seat = _free_seat(cfg, used, c)
            if seat is not None:
                c.seats = [seat]
                used[seat] += 1
    occ = occupancy(state)
    spare: list[Citizen] = []
    for city in mine_cities:
        if city.status != ACTIVE:
            continue
        free = {
            t
            for t in workable(state, cfg, city)
            if not any(hostile(u.owner, pid) for u in occ.get(t, []))
        }
        workers = [c for c in people if c.city == city.id and c.adult and not c.seats]
        for c in workers:
            if c.job.startswith("tile:") and int(c.job[5:]) in free:
                c.tile = int(c.job[5:])
                free.discard(c.tile)
        # Auto workers keep the city fed first (like Civ's governor), then follow its focus.
        food = base_food(state, cfg, city) * 100 + sum(
            tile_yields(cfg, state.tiles[c.tile])["food"] * 100 + tile_bonus(cfg, c)["food"]
            for c in workers
            if c.tile is not None
        )  # hundredths
        eaten = food_eaten(state, cfg, city) * 100
        for c in workers:
            if c.job != "auto" or c.tile is not None:
                continue
            if not free:
                spare.append(c)
                continue
            if food < eaten:
                best = max(
                    free,
                    key=lambda t: (
                        tile_yields(cfg, state.tiles[t])["food"],
                        tile_score(state, cfg, city, c, t),
                        -t,
                    ),
                )
            else:
                best = max(free, key=lambda t: (tile_score(state, cfg, city, c, t), -t))
            c.tile = best
            free.discard(best)
            food += tile_yields(cfg, state.tiles[best])["food"] * 100 + tile_bonus(cfg, c)["food"]
    for c in sorted(spare, key=lambda x: x.id):
        seat = _free_seat(cfg, used, c)
        if seat is not None:
            c.seats = [seat]
            used[seat] += 1


def assign_all(state: GameState, cfg: Config) -> None:
    for pid in state.player_ids():
        assign(state, cfg, pid)
    for city in state.cities:
        if city.owner not in state.players:
            sync(state, cfg, city)


def job_problem(state: GameState, cfg: Config, pid: str, c: Citizen, job: str) -> str | None:
    city = state.cities[c.city]
    if city.owner != pid:
        return "not your citizen"
    if job == "auto":
        return None
    if job == "council" or job.startswith("council:"):
        if not c.adult:
            return f"{c.name} has not grown up yet"
        used = pinned_seats(state, pid)
        for s, n in _seat_counts(state, pid).items():
            used[s] += n
        for s in c.seats if c.job.startswith("council") else []:
            used[s] -= 1
        if job.startswith("council:"):
            seat = job[8:]
            if seat != GENERAL and seat not in DOMAINS:
                return f"unknown seat {seat!r}"
            if seat != GENERAL and c.stats.get(seat, 0) <= 0:
                return f"{c.name} has no {seat} stat for that seat"
            if not _seat_ok(cfg, used, c, seat):
                return f"the {seat} seats are full"
        elif _free_seat(cfg, used, c) is None:
            return "no free council seat for this citizen"
        return None
    if not job.startswith("tile:") or not job[5:].isdigit():
        return f"unknown job {job!r}"
    if not c.adult:
        return f"{c.name} has not grown up yet"
    t = int(job[5:])
    if t not in workable(state, cfg, city):
        return "that tile has no improvement in this city's area"
    return None


def best_for_tile(state: GameState, cfg: Config, city: City, t: int) -> Citizen | None:
    """The grown citizen of this city who would give the most on tile `t` (city focus weights),
    not counting one already working it."""
    people = [c for c in of_city(state, city.id) if c.adult and c.tile != t]
    if not people:
        return None
    return max(people, key=lambda c: (tile_score(state, cfg, city, c, t), -c.id))


def city_lines(
    state: GameState, cfg: Config, city: City
) -> tuple[list[int], list[tuple[str, str, int]], dict[str, int]]:
    """(worked tiles, yield lines, fractions) from this city's citizens. Citizens' half stats on
    tiles are summed in hundredths; the whole part is a line and the rest (0-99) is returned for
    the city to carry to the next turn."""
    occ = occupancy(state)
    lines: list[tuple[str, str, int]] = []
    worked: list[int] = []
    tiles_sum = dict.fromkeys(YIELDS, 0)
    halves = dict.fromkeys(YIELDS, 0)
    for c in of_city(state, city.id):
        if c.tile is not None:
            if any(hostile(u.owner, city.owner or "") for u in occ.get(c.tile, [])):
                continue
            worked.append(c.tile)
            for y, v in tile_yields(cfg, state.tiles[c.tile]).items():
                tiles_sum[y] += v
            for y, v in tile_bonus(cfg, c).items():
                halves[y] += v
        elif c.seats:
            for y, v in council_bonus(cfg, c).items():
                if v:
                    lines.append((f"citizen:{c.name} (council)", y, v))
    for y in YIELDS:
        if halves[y] >= 100:
            lines.insert(0, ("citizens_on_tiles", y, halves[y] // 100))
        if tiles_sum[y]:
            lines.insert(0, ("worked_tiles", y, tiles_sum[y]))
    return sorted(worked), lines, {y: halves[y] % 100 for y in YIELDS}
