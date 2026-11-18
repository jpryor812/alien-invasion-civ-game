"""Months, the galactic winter and better farms (docs/SPEC_M19.md, designer 2026-11-18)."""

from __future__ import annotations

from beacon import economy, winter
from beacon.game import new_game
from beacon.state import state_from_json, state_to_json
from beacon.turn import date

EU = "europe"


def _city_with_farm(cfg):
    s = new_game(cfg, seed=2, start="classic")
    city = next(c for c in s.cities if c.owner == EU and c.is_capital)
    tile = economy.city_yields(s, cfg, city).worked
    return s, city, tile


def test_a_turn_is_a_month(cfg):
    assert date(cfg, 0) == "Jan 2025"
    assert date(cfg, 2) == "Mar 2025"
    assert date(cfg, 13) == "Feb 2026"


def test_a_winter_is_warned_lasts_a_year_and_ends(cfg):
    s = new_game(cfg, seed=2, start="classic")
    s.turn = cfg.t("winter.min_turn")
    found = None
    for _ in range(400):  # seeded: some turn draws one
        events = winter.start_turn(s, cfg)
        if events:
            found = events[0]
            break
        s.turn += 1
    assert found and found["kind"] == "winter_coming" and found["in"] == 3
    start = s.winter["from"]
    assert s.winter["to"] - start == 12 and not winter.active(s)
    assert winter.coming_in(s) == 3
    s.turn = start
    assert winter.start_turn(s, cfg)[0]["kind"] == "winter_began" and winter.active(s)
    assert winter.turns_left(s) == 12
    s.turn = start + 12
    assert winter.start_turn(s, cfg)[0]["kind"] == "winter_ended"
    assert not winter.active(s) and s.last_winter == start + 12
    s.turn += 1
    assert winter.start_turn(s, cfg) == []  # cooldown
    assert state_to_json(state_from_json(state_to_json(s))) == state_to_json(s)


def test_the_same_seed_draws_the_same_winter(cfg):
    def first(seed):
        s = new_game(cfg, seed=seed, start="classic")
        for t in range(cfg.t("winter.min_turn"), 500):
            s.turn = t
            if winter.start_turn(s, cfg):
                return dict(s.winter)
        return None

    assert first(5) == first(5)


def test_winter_halves_crops_and_techs_help(cfg):
    s, city, _ = _city_with_farm(cfg)
    a, b = [t for t in range(len(s.tiles)) if s.tiles[t].city == city.id and t != city.tile][:2]
    s.tiles[a].improvement, s.tiles[b].improvement = "farm", "pasture"
    player = s.players[EU]
    player.techs = [t for t in player.techs if t not in ("urban_planning", "vertical_farming")]
    assert winter.food_lines(s, cfg, city, [a, b], player) == []  # no winter, no techs
    s.winter = {"from": s.turn, "to": s.turn + 12}
    # a farm keeps 10 of 20, a pasture 9 of 12
    assert winter.food_lines(s, cfg, city, [a, b], player) == [("galactic winter", "food", -13)]
    player.techs.append("urban_planning")  # farms +5: keeps 12 of 25
    assert winter.food_lines(s, cfg, city, [a, b], player) == [
        ("better farming", "food", 5),
        ("galactic winter", "food", -15),
    ]
    player.techs.append("vertical_farming")  # crops keep 75%
    assert winter.keep_pct(cfg, player, "farm") == 75
    assert winter.keep_pct(cfg, player, "pasture") == 100
    assert winter.keep_pct(cfg, player, "mine") == 100
    s.tiles[a].improvement = None
    s.tiles[a].feature = None
    worked = economy.city_yields(s, cfg, city)  # wired into the city's yields
    assert all(src != "galactic winter" or v < 0 for src, _, v in worked.lines)


def test_pastures_are_hardier(cfg):
    assert cfg.improvements["pasture"]["yields"]["food"] == 12
    assert "hills" in cfg.improvements["pasture"]["elevations"]
    assert winter.keep_pct(cfg, None, "pasture") == 75
    assert winter.keep_pct(cfg, None, "farm") == 50
