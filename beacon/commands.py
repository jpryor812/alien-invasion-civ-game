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
    """Buy an item outright with gold: `item` if given (any allowed item, SPEC_M10), else the
    head of the queue. The queue is otherwise left alone."""

    kind: ClassVar[str] = "purchase"
    city: int
    item: str = ""


@register
@dataclass(frozen=True)
class SetConvoy(Command):
    """Send a share of a city's production or spare food each turn to a friendly city joined to
    it by road (SPEC_M10). target -1 stops the convoy."""

    kind: ClassVar[str] = "set_convoy"
    city: int
    target: int
    goods: str = "production"
    pct: int = 25


@register
@dataclass(frozen=True)
class EquipGear(Command):
    """Take gear from the armoury of the town the unit stands in (SPEC_M20)."""

    kind: ClassVar[str] = "equip_gear"
    unit: int
    item: str


@register
@dataclass(frozen=True)
class JoinCity(Command):
    """The unit settles in the town whose land it stands in, as a grown citizen (SPEC_M20)."""

    kind: ClassVar[str] = "join_city"
    unit: int


@register
@dataclass(frozen=True)
class SetGrowth(Command):
    """Allow or pause births in a city; paused, its spare food banks for the army (SPEC_M18)."""

    kind: ClassVar[str] = "set_growth"
    city: int
    grow: bool = True


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
class SetCitizenJob(Command):
    """job: "auto", "council", "tile:<index>" (an improved tile of the citizen's city) or
    "train:<unit>" (train as a soldier at the barracks, designer 2026-11-17)."""

    kind: ClassVar[str] = "set_citizen_job"
    citizen: int
    job: str


@register
@dataclass(frozen=True)
class UpgradeDefence(Command):
    """Spend gold to raise a city gun one level."""

    kind: ClassVar[str] = "upgrade_defence"
    unit: int


@register
@dataclass(frozen=True)
class UpgradeTurret(Command):
    """Spend gold to raise a turret one level (and repair it)."""

    kind: ClassVar[str] = "upgrade_turret"
    tile: int


@register
@dataclass(frozen=True)
class CancelJob(Command):
    """Engineers stop building (the work done is lost) and can move again."""

    kind: ClassVar[str] = "cancel_job"
    unit: int


@register
@dataclass(frozen=True)
class PromoteUnit(Command):
    """Spend a due promotion on one option (e.g. attack_10 or defence_10)."""

    kind: ClassVar[str] = "promote_unit"
    unit: int
    promotion: str


@register
@dataclass(frozen=True)
class AssignBestCitizen(Command):
    """Put the city's best grown citizen for this improved tile on it."""

    kind: ClassVar[str] = "assign_best_citizen"
    city: int
    tile: int


@register
@dataclass(frozen=True)
class ChooseStory(Command):
    """Answer an event waiting for your choice."""

    kind: ClassVar[str] = "choose_story"
    story: int
    choice: int


@register
@dataclass(frozen=True)
class HoldFire(Command):
    """The city will not fire this turn (answers the 'city can attack' alert)."""

    kind: ClassVar[str] = "city_hold_fire"
    city: int


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
    target: int = -1  # a sea bridge goes on a shallow water hex next to the unit (SPEC_M11)


@register
@dataclass(frozen=True)
class RefoundCity(Command):
    kind: ClassVar[str] = "refound_city"
    unit: int


@register
@dataclass(frozen=True)
class SeatRecruit(Command):
    """Seat a recruit: seats is ("general",) or a tuple of domains where it scores."""

    kind: ClassVar[str] = "seat_recruit"
    recruit: int
    seats: tuple[str, ...]


@register
@dataclass(frozen=True)
class UnseatRecruit(Command):
    kind: ClassVar[str] = "unseat_recruit"
    recruit: int


@register
@dataclass(frozen=True)
class OfferRecruit(Command):
    """Offer a recruit to another player; price 0 is a gift. Lapses at the end of the turn."""

    kind: ClassVar[str] = "offer_recruit"
    recruit: int
    to_player: str
    price: int


@register
@dataclass(frozen=True)
class AcceptOffer(Command):
    kind: ClassVar[str] = "accept_offer"
    offer: int


@register
@dataclass(frozen=True)
class DeclineOffer(Command):
    kind: ClassVar[str] = "decline_offer"
    offer: int


@register
@dataclass(frozen=True)
class ProposeDeal(Command):
    """Propose a deal. give/take are term dicts (gold, gold_per_turn, resources, techs,
    recruits, units, alliance); a deal with nothing to take is aid."""

    kind: ClassVar[str] = "propose_deal"
    to_player: str
    give: dict[str, Any]
    take: dict[str, Any]
    duration: int


@register
@dataclass(frozen=True)
class AcceptDeal(Command):
    kind: ClassVar[str] = "accept_deal"
    deal: int


@register
@dataclass(frozen=True)
class DeclineDeal(Command):
    kind: ClassVar[str] = "decline_deal"
    deal: int


@register
@dataclass(frozen=True)
class ShipUnit(Command):
    """Ship a unit from its owner's port to a known coastal city on another continent."""

    kind: ClassVar[str] = "ship_unit"
    unit: int
    city: int


@register
@dataclass(frozen=True)
class StartBarrage(Command):
    """Start the world barrage in one of your connected cities (needs the barrage tech)."""

    kind: ClassVar[str] = "start_barrage"
    city: int


@register
@dataclass(frozen=True)
class FundProject(Command):
    """Put gold into the barrage or an espionage operation."""

    kind: ClassVar[str] = "fund_project"
    project: int
    gold: int


@register
@dataclass(frozen=True)
class StartEspionage(Command):
    """Open an espionage operation: mode "solo" (only you fund and gain) or "shared"."""

    kind: ClassVar[str] = "start_espionage"
    mode: str


@register
@dataclass(frozen=True)
class ChooseEspionageTech(Command):
    kind: ClassVar[str] = "choose_espionage_tech"
    project: int
    tech: str


# -- freeing cities other than by siege (docs/SPEC_M12.md) -----------------------------------------


@register
@dataclass(frozen=True)
class Sabotage(Command):
    kind: ClassVar[str] = "sabotage"
    unit: int
    city: int


@register
@dataclass(frozen=True)
class ArmResistance(Command):
    kind: ClassVar[str] = "arm_resistance"
    unit: int
    city: int


@register
@dataclass(frozen=True)
class FundResistance(Command):
    """Send gold to the resistance in an alien city: its defence falls (designer 2026-11-16)."""

    kind: ClassVar[str] = "fund_resistance"
    city: int
    gold: int


# -- the city builder (docs/SPEC_M16.md) -----------------------------------------------------------


@register
@dataclass(frozen=True)
class PlaceBuilding(Command):
    """Order a building at a spot (top-left cell of its footprint); it joins the queue."""

    kind: ClassVar[str] = "place_building"
    city: int
    building: str
    x: int
    y: int


@register
@dataclass(frozen=True)
class MoveBuilding(Command):
    """Move a placed building (by its layout id) to another spot; free."""

    kind: ClassVar[str] = "move_building"
    city: int
    entry: int
    x: int
    y: int


@register
@dataclass(frozen=True)
class PlaceWalls(Command):
    """Lay wall pieces on cells (each [x, y]); a "walls" item joins the queue."""

    kind: ClassVar[str] = "place_walls"
    city: int
    cells: tuple[tuple[int, int], ...]
    material: str


@register
@dataclass(frozen=True)
class ImproveTile(Command):
    """Send a free engineer on the city's land to build a tile work (designer 2026-11-16)."""

    kind: ClassVar[str] = "improve_tile"
    city: int
    tile: int
    improvement: str


@register
@dataclass(frozen=True)
class CancelWork(Command):
    """Take a work off the city's list; its materials come back (SPEC_M17)."""

    kind: ClassVar[str] = "cancel_work"
    city: int
    work: int


@register
@dataclass(frozen=True)
class MoveWork(Command):
    """Move a work to position `to` in the city's list (the crew works top down, SPEC_M17)."""

    kind: ClassVar[str] = "move_work"
    city: int
    work: int
    to: int


@register
@dataclass(frozen=True)
class Trade(Command):
    """Buy or sell materials at the Galactic Exchange for a city's stores (SPEC_M17)."""

    kind: ClassVar[str] = "trade"
    city: int
    good: str
    amount: int
    side: str  # buy | sell


# -- the council of continents (docs/SPEC_M13.md) -------------------------------------------------


@register
@dataclass(frozen=True)
class ProposeMeasure(Command):
    kind: ClassVar[str] = "propose_measure"
    measure: str


@register
@dataclass(frozen=True)
class CastVote(Command):
    """`choice`: yes, no or abstain; for a chair election, a player id (or abstain)."""

    kind: ClassVar[str] = "cast_vote"
    measure: int
    choice: str
    extra: int = 0


@register
@dataclass(frozen=True)
class SetAgenda(Command):
    """The leader's public agenda, chosen on the creation screen (turn 0)."""

    kind: ClassVar[str] = "set_agenda"
    agenda: str


# -- the leader (docs/SPEC_M11.md) ---------------------------------------------------------------


@register
@dataclass(frozen=True)
class CreateLeader(Command):
    """Remake the player's leader on the creation screen (before the first turn ends)."""

    kind: ClassVar[str] = "create_leader"
    name: str
    sex: str
    look: str
    age: int
    traits: tuple[str, ...]
    skills: dict[str, int]  # the 15 starting points (designer 2026-11-16)


@register
@dataclass(frozen=True)
class RaiseSkill(Command):
    kind: ClassVar[str] = "raise_skill"
    skill: str


@register
@dataclass(frozen=True)
class ChooseLeaderBonus(Command):
    """Answer a waiting leader choice: a milestone's bonus, or the third trait ("trait")."""

    kind: ClassVar[str] = "choose_leader_bonus"
    choice: str
    option: str


@register
@dataclass(frozen=True)
class StartFamily(Command):
    """`partner` is "citizen:<id>" (a grown citizen) or "recruit:<id>" (a seated recruit)."""

    kind: ClassVar[str] = "start_family"
    partner: str


@register
@dataclass(frozen=True)
class SetWardrobe(Command):
    """Cosmetic only. The client checks career unlocks (runs/profile.json)."""

    kind: ClassVar[str] = "set_wardrobe"
    outfit: str
    accessories: tuple[str, ...]


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
