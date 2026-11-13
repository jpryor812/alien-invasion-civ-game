"""Player commands: every action a player (human, bot or AI) can take is one of these.

Commands are frozen dataclasses with a registered `kind`, serialisable to plain dicts so a game can
be replayed from seed + config + command log. Validation and effects live in `beacon.actions`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, ClassVar


class CommandError(ValueError):
    """An illegal command. The state is left unchanged."""


COMMANDS: dict[str, type[Command]] = {}


def register(cls: type[Command]) -> type[Command]:
    if cls.kind in COMMANDS:
        raise ValueError(f"duplicate command kind {cls.kind}")
    COMMANDS[cls.kind] = cls
    return cls


@dataclass(frozen=True)
class Command:
    kind: ClassVar[str] = ""
    player: str


@register
@dataclass(frozen=True)
class SetResearch(Command):
    kind: ClassVar[str] = "set_research"
    tech: str


@register
@dataclass(frozen=True)
class SetProduction(Command):
    """Replace the city's queue with `items` ("building:x", "unit:x", "project:x")."""

    kind: ClassVar[str] = "set_production"
    city: int
    items: tuple[str, ...]


@register
@dataclass(frozen=True)
class Purchase(Command):
    """Buy the item at the head of the queue outright with gold."""

    kind: ClassVar[str] = "purchase"
    city: int


@register
@dataclass(frozen=True)
class SetFocus(Command):
    kind: ClassVar[str] = "set_focus"
    city: int
    focus: str


@register
@dataclass(frozen=True)
class MoveUnit(Command):
    """Move toward `target` along the cheapest path, as far as moves allow this turn."""

    kind: ClassVar[str] = "move_unit"
    unit: int
    target: int


@register
@dataclass(frozen=True)
class Attack(Command):
    kind: ClassVar[str] = "attack"
    unit: int
    target: int


@register
@dataclass(frozen=True)
class CityAttack(Command):
    kind: ClassVar[str] = "city_attack"
    city: int
    target: int


@register
@dataclass(frozen=True)
class MergeUnits(Command):
    """Move `unit` onto `into` (same type and owner) and merge them into one stack."""

    kind: ClassVar[str] = "merge_units"
    unit: int
    into: int


@register
@dataclass(frozen=True)
class SplitUnit(Command):
    """Split a stack: a full-HP unit moves to adjacent `target`; the rest stays."""

    kind: ClassVar[str] = "split_unit"
    unit: int
    target: int


@register
@dataclass(frozen=True)
class Fortify(Command):
    kind: ClassVar[str] = "fortify"
    unit: int


@register
@dataclass(frozen=True)
class SkipUnit(Command):
    """Do nothing with this unit this turn (clears it from pending decisions)."""

    kind: ClassVar[str] = "skip_unit"
    unit: int


@register
@dataclass(frozen=True)
class BuildImprovement(Command):
    kind: ClassVar[str] = "build_improvement"
    unit: int
    improvement: str


@register
@dataclass(frozen=True)
class RefoundCity(Command):
    kind: ClassVar[str] = "refound_city"
    unit: int


def command_to_dict(cmd: Command) -> dict[str, Any]:
    data = asdict(cmd)
    for key, value in data.items():
        if isinstance(value, tuple):
            data[key] = list(value)
    return {"kind": cmd.kind, **data}


def command_from_dict(data: dict[str, Any]) -> Command:
    kind = data.get("kind")
    if kind not in COMMANDS:
        raise CommandError(f"unknown command kind {kind!r}")
    cls = COMMANDS[kind]
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            raise CommandError(f"{kind}: missing field {f.name}")
        value = data[f.name]
        kwargs[f.name] = tuple(value) if isinstance(value, list) else value
    return cls(**kwargs)
