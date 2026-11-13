"""M0: config validation, RNG streams, state round-trip, commands, runner."""

from __future__ import annotations

import json

import pytest

from beacon import canonical, config, hexgrid, rng
from beacon.commands import (
    COMMANDS,
    CommandError,
    MoveUnit,
    SetProduction,
    command_from_dict,
    command_to_dict,
)
from beacon.game import new_game
from beacon.runner import main
from beacon.state import find_floats, state_digest, state_from_json, state_to_json, to_dict

# -- config ----------------------------------------------------------------------------------


def test_real_data_loads(cfg):
    assert len(cfg.continents) == 6
    assert cfg.t("combat.stack_size") == 2
    assert cfg.continent_ids()[0] == "north_america"
    assert all(len(c["cities"]) == 20 for c in cfg.continents.values())


def _override(fn):
    return lambda: config.load(overrides=fn)


def test_untagged_number_rejected():
    def bad(raw):
        raw["tuning"]["combat"]["base_damage"] = 30

    with pytest.raises(config.ConfigError, match="untagged number"):
        _override(bad)()


def test_float_rejected():
    def bad(raw):
        raw["tuning"]["combat"]["base_damage"]["value"] = 30.5

    with pytest.raises(config.ConfigError, match="floats"):
        _override(bad)()


def test_bad_status_rejected():
    def bad(raw):
        raw["tuning"]["combat"]["base_damage"]["status"] = "guess"

    with pytest.raises(config.ConfigError, match="status"):
        _override(bad)()


def test_unknown_reference_rejected():
    def bad(raw):
        raw["buildings"]["buildings"]["workshop"]["tech"] = "no_such_tech"

    with pytest.raises(config.ConfigError, match="unknown techs id"):
        _override(bad)()


def test_missing_required_field_rejected():
    def bad(raw):
        del raw["units"]["units"]["infantry"]["strength"]

    with pytest.raises(config.ConfigError, match="missing required field 'strength'"):
        _override(bad)()


def test_missing_tuning_value_is_a_clear_error(cfg):
    with pytest.raises(KeyError, match="no.such"):
        cfg.t("no.such")


# -- rng -------------------------------------------------------------------------------------


def test_streams_are_reproducible_and_independent():
    a = [rng.stream(7, "combat", 3, 1).randrange(1000) for _ in range(3)]
    b = [rng.stream(7, "combat", 3, 1).randrange(1000) for _ in range(3)]
    assert a == b
    seq = rng.stream(7, "map", "europe")
    first = [seq.randrange(10**9) for _ in range(5)]
    other = rng.stream(7, "map", "asia")
    assert first != [other.randrange(10**9) for _ in range(5)]
    assert rng.derive_seed(7, "map", "x") != rng.derive_seed(8, "map", "x")


def test_unknown_stream_rejected():
    with pytest.raises(ValueError, match="unknown RNG stream"):
        rng.stream(1, "ai")


def test_weighted_choice_respects_zero_weights():
    r = rng.stream(1, "events")
    picks = {rng.weighted_choice(r, ["a", "b", "c"], [0, 5, 0]) for _ in range(50)}
    assert picks == {"b"}


# -- hex grid ---------------------------------------------------------------------------------


def test_hex_neighbours_are_symmetric_and_at_distance_one():
    w, h = 12, 9
    for i in range(w * h):
        ns = hexgrid.neighbours(i, w, h)
        assert len(ns) <= 6
        for n in ns:
            assert i in hexgrid.neighbours(n, w, h)
            assert hexgrid.distance(i, n, w) == 1


def test_hex_within_radius_counts():
    w, h = 20, 20
    centre = hexgrid.index(10, 10, w)
    assert len(hexgrid.within(centre, 1, w, h)) == 7
    assert len(hexgrid.within(centre, 2, w, h)) == 19
    assert all(hexgrid.distance(centre, t, w) <= 2 for t in hexgrid.within(centre, 2, w, h))


# -- state ------------------------------------------------------------------------------------


def test_state_round_trips_to_identical_bytes(cfg):
    state = new_game(cfg, seed=3)
    text = state_to_json(state)
    again = state_from_json(text)
    assert state_to_json(again) == text
    assert state_digest(again) == state_digest(state)
    assert find_floats(to_dict(state)) == []
    assert json.loads(text)["config_digest"] == cfg.digest


def test_canonical_rejects_nan():
    with pytest.raises(ValueError):
        canonical.dumps({"x": float("nan")})


# -- commands ---------------------------------------------------------------------------------


def test_commands_round_trip():
    for cmd in (
        MoveUnit(player="europe", unit=4, target=99),
        SetProduction(player="asia", city=2, items=("building:workshop", "unit:infantry")),
    ):
        data = command_to_dict(cmd)
        assert json.loads(canonical.dumps(data)) == data
        assert command_from_dict(data) == cmd
    assert "attack" in COMMANDS and "merge_units" in COMMANDS


def test_bad_command_dict_rejected():
    with pytest.raises(CommandError):
        command_from_dict({"kind": "teleport", "player": "europe"})
    with pytest.raises(CommandError, match="missing field"):
        command_from_dict({"kind": "move_unit", "player": "europe", "unit": 1})


# -- runner -----------------------------------------------------------------------------------


def test_runner_writes_a_run_folder(tmp_path):
    out = tmp_path / "run"
    assert main(["run", "--seed", "1", "--turns", "5", "--out", str(out)]) == 0
    for name in ("final_state.json", "events.jsonl", "commands.jsonl", "summary.json"):
        assert (out / name).exists()
    info = json.loads((out / "summary.json").read_text())
    assert info["turn"] == 5
