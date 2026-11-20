"""Food, rations and the rescued town (docs/SPEC_M18.md, designer 2026-11-18)."""

from __future__ import annotations

from beacon import citizens, economy, food, hexgrid, survivors, works
from beacon.actions import apply_command
from beacon.commands import Attack, SetGrowth
from beacon.game import new_game
from beacon.state import ACTIVE, OVERRUN, state_from_json, state_to_json
from beacon.turn import advance_turn
from beacon.units import create_unit, remove_unit

EU = "europe"


def _city(cfg, seed=2):
    s = new_game(cfg, seed=seed, start="classic")
    return s, next(c for c in s.cities if c.owner == EU and c.is_capital)


def test_children_eat_double_and_farms_feed_ten(cfg):
    s, city = _city(cfg)
    people = citizens.of_city(s, city.id)
    adults = sum(1 for c in people if c.adult)
    kids = len(people) - adults
    assert citizens.food_eaten(s, cfg, city) >= 2 * adults + 4 * kids
    assert cfg.improvements["farm"]["yields"]["food"] == 20
    assert economy.growth_threshold(cfg, 1) == 20
    assert economy.growth_threshold(cfg, 5) == 40


def test_the_store_is_capped_by_the_granary_and_births_can_pause(cfg):
    s, city = _city(cfg)
    granary = food.F(cfg, "granary")
    city.buildings = [b for b in city.buildings if b != granary]
    assert food.store_cap(cfg, city) == 60
    city.buildings.append(granary)
    assert food.store_cap(cfg, city) == 180
    city.buildings.remove(granary)
    apply_command(s, cfg, SetGrowth(player=EU, city=city.id, grow=False))
    assert not city.grow
    city.food_store, pop = 59, city.pop
    economy.process_city(s, cfg, city, s.players[EU])
    assert city.pop == pop and city.food_store <= 60  # banked, capped, nobody born
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_a_town_feeds_its_army_and_units_outside_eat_rations(cfg):
    s, city = _city(cfg)
    for u in [u for u in s.units.values() if u.owner == EU]:
        remove_unit(s, u)
    near = create_unit(s, cfg, "infantry", EU, city.tile)
    far_tile = next(
        i
        for i in range(len(s.tiles))
        if hexgrid.distance(i, city.tile, s.width) > 6
        and all(hexgrid.distance(i, c.tile, s.width) > 4 for c in s.cities)
    )
    away = create_unit(s, cfg, "infantry", EU, far_tile)
    assert food.feeder(s, cfg, near) is city and food.feeder(s, cfg, away) is None
    assert food.army_food(s, cfg, city) == 2
    city.food_store = 50
    near.rations = 3
    economy.player_turn(s, cfg, EU)
    food.field(s, cfg, EU)
    assert near.rations == 10 and near.fed == s.turn
    assert away.rations == 9
    away.rations, hp = 0, away.hp
    food.field(s, cfg, EU)
    assert away.hp == hp - 10  # starving
    away.hp = 5
    events = food.field(s, cfg, EU)
    assert str(away.id) not in s.units and events[-1]["kind"] == "unit_starved"


def test_a_town_that_cannot_feed_its_army_leaves_it_on_rations(cfg):
    s, city = _city(cfg)
    army = [create_unit(s, cfg, "infantry", EU, city.tile) for _ in range(3)]
    city.food_store = 0
    left = food.feed(s, cfg, city, army, 2)  # spare food for one soldier only
    assert left == 0
    assert [u.fed == s.turn for u in army] == [True, False, False]


def test_food_crates_refill_rations(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    band = [u for u in s.units.values() if u.owner == EU]
    for u in band:
        u.rations = 1
    s.caches = {str(band[0].tile): "food"}
    events = survivors.pick_up(s, cfg)
    assert events[0]["loot"] == "food"
    assert all(
        u.rations == 10 for u in band if hexgrid.distance(u.tile, band[0].tile, s.width) <= 3
    )


def test_the_band_lives_on_rations(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    band = [u for u in s.units.values() if u.owner == EU]
    s.caches = {}
    advance_turn(s, cfg)
    assert all(food.rations(cfg, u) == 9 for u in band if str(u.id) in s.units)


def test_the_first_town_rescues_three_and_asks_for_the_farm(cfg):
    s = new_game(cfg, seed=2, start="survivor")
    s.caches = {}
    p = s.players[EU]
    town = s.cities[p.band_town]
    p.band_claimed = True
    band = [u for u in s.units.values() if u.owner == EU]
    lead = next(u for u in band if u.type == "band_leader")
    lead.tile = next(
        n for n in hexgrid.neighbours(town.tile, s.width, s.height) if not s.units_at(n)
    )
    for g in list(s.units_at(town.tile)):
        remove_unit(s, g)
    town.hp, town.funded_pct = 1, 50
    lead.hp = 100
    apply_command(s, cfg, Attack(player=EU, unit=lead.id, target=town.tile))
    assert town.status == ACTIVE and town.owner == EU
    survivors_in = sum(1 for u in band if u.type == "survivor" and not u.gear)
    assert town.pop == 3 + survivors_in  # three rescued, then the band
    assert town.food_store >= food.F(cfg, "freed_store")
    radio = cfg.t("contact.radio_building")
    assert town.works == []  # nothing is built for you (designer 2026-11-19)
    assert radio in town.wrecked and radio not in town.buildings
    from beacon.actions import pending_decisions
    from beacon.commands import ImproveTile, SetProduction

    first = pending_decisions(s, cfg, EU)[0]
    assert first["kind"] == "repair_farm" and first["city"] == town.id
    farm_tile = first["tile"]
    assert s.tiles[farm_tile].pillaged == "farm"
    apply_command(s, cfg, ImproveTile(player=EU, city=town.id, tile=farm_tile, improvement="farm"))
    assert not any(p["kind"] == "repair_farm" for p in pending_decisions(s, cfg, EU))
    stores = dict(town.stores)
    assert works.building_cost(s, cfg, town, radio) == {}  # a repair is free
    apply_command(s, cfg, SetProduction(player=EU, city=town.id, items=(f"building:{radio}",)))
    assert town.stores == stores
    assert all(w["left"] == food.F(cfg, "repair_labour") for w in town.works[:2])
    events = works.progress(s, cfg, town)  # two engineers: both repairs in one turn
    assert radio in town.buildings and s.tiles[farm_tile].improvement == "farm"
    assert radio not in town.wrecked
    assert sum(1 for e in events if e["kind"] in ("building_completed", "improvement_built")) == 2


def test_every_freed_town_has_a_damaged_farm(cfg):
    from beacon import liberation

    s = new_game(cfg, seed=2, start="classic")
    city = next(c for c in s.cities if c.status == OVERRUN and c.continent == EU)
    liberation.liberate(s, cfg, city, EU)
    assert city.owner == EU and city.works == []
    assert any(s.tiles[t].pillaged == "farm" for t in city.border)
    assert len(city.border) <= 7  # its land starts at one ring (SPEC_M20)
    assert city.food_store >= food.F(cfg, "freed_store")


def test_the_ai_brings_hungry_units_home_and_spares_its_food(cfg):
    from beacon.ai import AIPlayer

    s, city = _city(cfg)
    for u in [u for u in s.units.values() if u.owner == EU]:
        remove_unit(s, u)
    seen = set()
    start = next(
        i
        for i in hexgrid.within(city.tile, 7, s.width, s.height)
        if hexgrid.distance(i, city.tile, s.width) == 7
        and s.tiles[i].continent == EU
        and s.tiles[i].terrain in ("grassland", "plains")
        and not s.units_at(i)
    )
    unit = create_unit(s, cfg, "infantry", EU, start)
    unit.rations = 1
    seen.add(unit.tile)

    def submit(cmd):
        apply_command(s, cfg, cmd)
        return True

    bot = AIPlayer(s, cfg, EU, submit)
    assert bot.go_home(unit)
    assert hexgrid.distance(unit.tile, city.tile, s.width) < 7
    unit.rations = 10
    assert not bot.go_home(unit)  # plenty left: carry on
    room = bot.food_room(city)
    assert room == economy.city_yields(s, cfg, city).surplus_food - food.army_food(s, cfg, city)
