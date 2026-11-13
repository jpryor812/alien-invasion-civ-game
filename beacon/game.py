"""Creating a new game."""

from __future__ import annotations

from beacon.config import Config
from beacon.state import GameState, Player, Tile


def new_players(cfg: Config, continents: list[str]) -> dict[str, Player]:
    start_techs = sorted(t for t, spec in cfg.techs.items() if spec["known_at_start"])
    return {
        cid: Player(
            id=cid,
            name=cfg.continents[cid]["name"],
            gold=cfg.t("economy.start_gold"),
            techs=list(start_techs),
        )
        for cid in continents
    }


def new_game(cfg: Config, seed: int, continents: list[str] | None = None) -> GameState:
    """An empty world: all ocean, one player per continent. Map generation arrives in M1."""
    continents = continents or cfg.continent_ids()
    width, height = cfg.t("map.width"), cfg.t("map.height")
    return GameState(
        seed=seed,
        config_digest=cfg.digest,
        width=width,
        height=height,
        tiles=[Tile(terrain="ocean") for _ in range(width * height)],
        players=new_players(cfg, continents),
    )
