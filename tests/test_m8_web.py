"""M8: the web session and HTTP API (the client itself is play-tested in a browser)."""

from __future__ import annotations

import json
import threading
import urllib.request

import pytest

from beacon import fog
from beacon.state import ALIENS
from beacon.units import create_unit, free_tile_near
from web import profile
from web import session as session_mod
from web.server import serve
from web.session import Session

HUMAN = "europe"


@pytest.fixture(autouse=True)
def temp_saves(tmp_path, monkeypatch):
    """Keep test saves (including autosaves) out of runs/saves."""
    monkeypatch.setattr(session_mod, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(profile, "PROFILE", tmp_path / "profile.json")  # the career (M11)


@pytest.fixture
def sess(cfg):
    return Session(cfg, seed=3, human=HUMAN, start="classic")  # cities from turn 1


def test_view_is_fog_safe(sess, cfg):
    v = sess.view()
    seen = fog.visible_tiles(sess.state, cfg, HUMAN)
    city_tiles = {c["tile"] for c in v["cities"].values()}
    assert {int(k) for k in v["tiles"]} <= seen | city_tiles
    for u in v["units"]:
        assert u["owner"] == HUMAN or u["tile"] in seen
    hidden_aliens = [
        u for u in sess.state.units.values() if u.owner == ALIENS and u.tile not in seen
    ]
    assert hidden_aliens and not {u.id for u in hidden_aliens} & {u["id"] for u in v["units"]}
    assert v["me"] == HUMAN and v["pending"]


def test_unit_options_move_and_attack_preview(sess, cfg):
    s = sess.state
    inf = next(u for u in s.sorted_units() if u.owner == HUMAN and u.type == "infantry")
    opts = sess.unit_options(inf.id)
    assert opts["reachable"]
    target = opts["reachable"][0]
    res = sess.command({"kind": "move_unit", "unit": inf.id, "target": target})
    assert res["ok"] and s.unit(inf.id).tile == target
    spot = free_tile_near(s, cfg, "alien_warrior", ALIENS, target, 1)
    alien = create_unit(s, cfg, "alien_warrior", ALIENS, spot)
    s.unit(inf.id).moves_left = 60
    attacks = sess.unit_options(inf.id)["attacks"]
    assert [a["tile"] for a in attacks] == [alien.tile]
    preview = attacks[0]["preview"]
    assert preview["legal"] and preview["damage_to_defender"]["expected"] > 0
    with pytest.raises(ValueError):
        sess.unit_options(alien.id)  # not yours


def test_city_detail_and_production(sess):
    city_id = sess.view()["my_cities"][0]["id"]
    d = sess.city_detail(city_id)
    assert d["options"] and d["totals"]["food"] == sum(v for _, y, v in d["lines"] if y == "food")
    item = next(o["item"] for o in d["options"] if o["kind"] == "unit")
    assert sess.command({"kind": "set_production", "city": city_id, "items": [item]})["ok"]
    assert sess.state.cities[city_id].queue == [item]


def test_techs_and_research(sess):
    techs = sess.techs()["techs"]
    available = [t["id"] for t in techs if t["status"] == "available"]
    assert available and all(t["tree"] != "alien" for t in techs if t["status"] == "available")
    assert sess.command({"kind": "set_research", "tech": available[0]})["ok"]
    assert sess.techs()["research"] == available[0]


def test_illegal_commands_are_rejected_with_a_message(sess):
    res = sess.command({"kind": "set_research", "tech": "stellar_chorus"})
    assert res == {"ok": False, "error": "stellar_chorus is not available to research"}
    assert not sess.command({"kind": "teleport"})["ok"]


def test_end_turn_runs_the_ai(sess):
    turn = sess.state.turn
    assert sess.end_turn()["ok"]
    assert sess.state.turn == turn + 1
    ai = [p for pid, p in sess.state.players.items() if pid != HUMAN]
    assert all(p.research for p in ai)  # every AI chose research
    assert sess.state.players[HUMAN].research is None  # the human seat was left alone


def test_save_and_load(sess):
    sess.end_turn()
    sess.save("slot_1")
    saves = Session.saves()
    assert [m["name"] for m in saves] == ["autosave", "slot_1"] or [m["name"] for m in saves] == [
        "slot_1",
        "autosave",
    ]
    meta = next(m for m in saves if m["name"] == "slot_1")
    assert meta["turn"] == sess.state.turn and meta["player"] == HUMAN
    turn = sess.state.turn
    sess.end_turn()
    sess.load("slot_1")
    assert sess.state.turn == turn and sess.human == HUMAN
    with pytest.raises(ValueError):
        sess.save("../escape")


def test_status_and_continents(sess):
    st = sess.status()
    assert st["player"] == HUMAN and st["turn"] == 0
    names = [c["name"] for c in sess.continents()]
    assert len(names) == 6 and "Europe" in names


def test_screens_build(sess):
    assert "recruits" in sess.council()
    assert len(sess.diplomacy()["players"]) == 5
    assert sess.projects()["barrage"] is None
    assert len(sess.scores()["ranking"]) == 6


def test_http_api_round_trip():
    server = serve(port=0, seed=2, human=HUMAN)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"

    def get(path):
        with urllib.request.urlopen(base + path) as r:
            return r.status, r.read()

    def post(path, body):
        req = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    try:
        status, page = get("/")
        assert status == 200 and b'<canvas id="map">' in page
        status, body = get("/api/view")
        assert status == 200 and json.loads(body)["turn"] == 0
        assert post("/api/end_turn", {})["ok"]
        assert json.loads(get("/api/view")[1])["turn"] == 1
        assert json.loads(get("/api/status")[1])["turn"] == 1
        assert len(json.loads(get("/api/continents")[1])) == 6
        assert post("/api/command", {"kind": "set_research", "tech": "nope"})["ok"] is False
        with pytest.raises(urllib.error.HTTPError):
            get("/../pyproject.toml")
    finally:
        server.shutdown()
