"""Citizens train as soldiers at the barracks (designer 2026-11-17)."""

from __future__ import annotations

import pytest

from beacon import citizens, economy
from beacon.actions import apply_command
from beacon.commands import CommandError, SetCitizenJob
from beacon.game import new_game

EU = "europe"


@pytest.fixture
def world(cfg):
    s = new_game(cfg, seed=2, start="classic")
    capital = next(c for c in s.cities if c.owner == EU and c.is_capital)
    return s, capital


def test_a_citizen_trains_and_leaves_as_a_unit(cfg, world):
    s, c = world
    person = next(p for p in citizens.of_city(s, c.id) if p.adult)
    with pytest.raises(CommandError, match="foot"):
        apply_command(s, cfg, SetCitizenJob(player=EU, citizen=person.id, job="train:tank"))
    c.buildings = [b for b in c.buildings if b != cfg.materials("barracks.building")]
    with pytest.raises(CommandError, match="barracks"):
        apply_command(s, cfg, SetCitizenJob(player=EU, citizen=person.id, job="train:infantry"))
    c.buildings.append(cfg.materials("barracks.building"))
    apply_command(s, cfg, SetCitizenJob(player=EU, citizen=person.id, job="train:infantry"))
    citizens.assign(s, cfg, EU)
    assert person.tile is None and not person.seats  # it trains instead of working
    turns = citizens.train_turns(cfg, "infantry")
    assert turns == cfg.units["infantry"]["strength"] // 10
    assert citizens.train_turns(cfg, "militia") < turns  # stronger units take longer
    pop = c.pop
    before = {u.id for u in s.units.values() if u.owner == EU and u.type == "infantry"}
    events = []
    for _ in range(turns):
        events += citizens.train(s, cfg, EU)
    done = next(e for e in events if e["kind"] == "citizen_enlisted")
    assert done["type"] == "infantry" and c.pop == pop - 1
    assert str(person.id) not in s.citizens
    now = {u.id for u in s.units.values() if u.owner == EU and u.type == "infantry"}
    assert len(now - before) == 1
    economy.city_yields(s, cfg, c)  # the city still adds up


def test_the_last_citizen_stays_home(cfg, world):
    s, c = world
    people = [p for p in citizens.of_city(s, c.id) if p.adult]
    for p in people[:-1]:
        p.job = "train:militia"
    c.pop = len(citizens.of_city(s, c.id))
    assert citizens.train_problem(s, cfg, people[-1], "militia") == citizens.HOME
