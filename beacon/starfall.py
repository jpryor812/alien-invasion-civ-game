"""Starfall: deep-space shards fall through the aliens' wormhole (docs/SPEC_M9.md).

About every 20 turns everyone is warned that a shard will land in a marked area. When it lands
its hex is known to all. A player's engineer or scout (or any alien unit) standing on it at the
end of a turn mines it for one turn; the first side to reach `mine_turns` claims it. The claimer
gets a permanent bonus (larger later in the game); if the aliens claim it, their tech jumps.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid, rng
from beacon.config import Config
from beacon.state import ALIENS, GameState, Shard
from beacon.tiles import is_passable_land

Events = list[dict[str, Any]]


def settings(cfg: Config) -> dict[str, Any]:
    return cfg.story("starfall")


def active(state: GameState) -> list[Shard]:
    """Shards warned or landed and not yet claimed."""
    return sorted((s for s in state.shards.values() if s.claimed_by is None), key=lambda s: s.id)


def landed(state: GameState, shard: Shard) -> bool:
    return state.turn >= shard.impact_turn


def can_mine(cfg: Config, owner: str, unit_type: str) -> bool:
    spec = cfg.units[unit_type]
    if owner == ALIENS:
        return spec["domain"] == "land"
    return bool(spec.get("can_build")) or (spec["role"] == "recon" and spec["domain"] == "land")


def scale(cfg: Config, turn: int) -> int:
    """Percent multiplier for rewards: a later shard is worth more."""
    return 100 + settings(cfg)["growth_pct"] * turn // 100


def _scaled(value: Any, pct: int) -> Any:
    if isinstance(value, dict):
        return {k: _scaled(v, pct) for k, v in value.items()}
    if isinstance(value, list):
        return list(value)
    return value * pct // 100


def reward(cfg: Config, kind: str, turn: int) -> dict[str, Any]:
    return _scaled(settings(cfg)["kinds"][kind]["effects"], scale(cfg, turn))


def _drop(state: GameState, cfg: Config) -> Events:
    s = settings(cfg)
    r = rng.stream(state.seed, "events", state.turn, "starfall")
    conts = sorted({c.continent for c in state.cities})
    taken = {x.tile for x in state.sites.values()} | {c.tile for c in state.cities}
    for _ in range(len(conts)):
        cont = r.choice(conts)
        options = [
            i
            for i, t in enumerate(state.tiles)
            if t.continent == cont
            and is_passable_land(cfg, t)
            and i not in taken
            and all(
                hexgrid.distance(i, c.tile, state.width) >= s["min_city_distance"]
                for c in state.cities
            )
        ]
        if options:
            break
    else:
        return []
    tile = r.choice(options)
    kinds = sorted(s["kinds"])
    kind = rng.weighted_choice(r, kinds, [s["kinds"][k]["weight"] for k in kinds])
    near = hexgrid.within(tile, s["cone_radius"] // 2, state.width, state.height)
    center = r.choice(sorted(near))
    sid = state.new_id()
    state.shards[str(sid)] = Shard(
        id=sid,
        kind=kind,
        tile=tile,
        warn_turn=state.turn,
        impact_turn=state.turn + s["warning_turns"],
        cone_center=center,
        cone_radius=s["cone_radius"],
    )
    return [
        {
            "turn": state.turn,
            "kind": "shard_warning",
            "shard": sid,
            "center": center,
            "radius": s["cone_radius"],
            "impact_turn": state.turn + s["warning_turns"],
        }
    ]


def _claim(state: GameState, cfg: Config, shard: Shard, who: str) -> Events:
    shard.claimed_by, shard.claimed_turn = who, state.turn
    spec = settings(cfg)["kinds"][shard.kind]
    if who == ALIENS:
        gain = settings(cfg)["alien_progress"] * scale(cfg, state.turn) // 100
        state.aliens.progress += gain
        effects: dict[str, Any] = {}
    else:
        effects = reward(cfg, shard.kind, state.turn)
        player = state.players[who]
        player.boons = [*player.boons, {"shard": shard.kind, **effects}]
        from beacon.liberation import credit  # liberation imports nothing from here

        credit(state, who, "shards_claimed")
    return [
        {
            "turn": state.turn,
            "kind": "shard_claimed",
            "shard": shard.id,
            "by": who,
            "find": shard.kind,
            "name": spec["name"],
            "tile": shard.tile,
            "effects": effects,
        }
    ]


def end_of_turn(state: GameState, cfg: Config) -> Events:
    """Warnings, impacts, a turn of mining, claims, and the next shard."""
    s = settings(cfg)
    events: Events = []
    if state.next_shard_turn < 0:
        state.next_shard_turn = s["first_turn"]
    for shard in active(state):
        if state.turn == shard.impact_turn:
            events.append(
                {
                    "turn": state.turn,
                    "kind": "shard_landed",
                    "shard": shard.id,
                    "tile": shard.tile,
                    "find": shard.kind,
                    "name": s["kinds"][shard.kind]["name"],
                }
            )
        if not landed(state, shard):
            continue
        if state.turn - shard.impact_turn >= s["fade_turns"]:
            shard.claimed_by, shard.claimed_turn = "nobody", state.turn  # burnt out
            events.append(
                {"turn": state.turn, "kind": "shard_faded", "shard": shard.id, "tile": shard.tile}
            )
            continue
        for u in state.units_at(shard.tile):
            if can_mine(cfg, u.owner, u.type):
                shard.progress[u.owner] = shard.progress.get(u.owner, 0) + 1
                if shard.progress[u.owner] >= s["mine_turns"]:
                    events.extend(_claim(state, cfg, shard, u.owner))
                    break
    if state.turn >= state.next_shard_turn and not active(state):
        events.extend(_drop(state, cfg))
        r = rng.stream(state.seed, "events", state.turn, "starfall-next")
        state.next_shard_turn = state.turn + s["interval"] + r.randint(0, s["jitter"])
    return events
