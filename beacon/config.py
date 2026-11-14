"""Load and validate the YAML data files in `data/`.

Rules enforced at load time:

- Every number must be *tagged*: it sits inside a mapping that carries
  `status: placeholder | calibrated`, either on the value itself (`{value, status, note}`) or on an
  enclosing entry. A bare, untagged number is an error, so magic numbers cannot slip in.
- Numbers are integers. Percentages are integer percent. Floats are rejected.
- Content tables (units, buildings, ...) have required fields and cross-references that must
  resolve to known ids.

Strings, booleans and nulls are structural and may appear bare.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from beacon import canonical

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

STATUSES = frozenset({"placeholder", "calibrated"})
META_KEYS = frozenset({"status", "note", "source", "unit"})


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TableSpec:
    """One content table: `file` holds a top-level mapping `key` of id -> entry."""

    file: str
    key: str
    required: tuple[str, ...]
    # field -> table it refers to. The field may hold an id, a list of ids, or a mapping keyed by
    # ids. Dotted fields reach into nested mappings.
    refs: dict[str, str] = field(default_factory=dict)


TABLES: dict[str, TableSpec] = {
    "terrains": TableSpec(
        "terrain", "terrains", ("water", "yields", "move_cost", "defense_pct"), {}
    ),
    "elevations": TableSpec(
        "terrain", "elevations", ("passable", "yields", "move_cost", "defense_pct", "vision_bonus")
    ),
    "features": TableSpec(
        "terrain",
        "features",
        ("yields", "move_cost", "defense_pct", "allowed_terrains"),
        {"allowed_terrains": "terrains"},
    ),
    "biomes": TableSpec(
        "terrain",
        "biomes",
        ("terrain", "features"),
        {"terrain": "terrains", "features": "features"},
    ),
    "resources": TableSpec(
        "resources",
        "resources",
        ("category", "yields", "improvement", "terrains", "elevations", "quantity"),
        {"improvement": "improvements", "terrains": "terrains", "elevations": "elevations"},
    ),
    "improvements": TableSpec(
        "improvements",
        "improvements",
        ("kind", "turns", "tech", "yields", "terrains", "elevations"),
        {"tech": "techs", "terrains": "terrains", "elevations": "elevations"},
    ),
    "buildings": TableSpec(
        "buildings",
        "buildings",
        ("cost", "maintenance", "tech", "yields", "yield_pct"),
        {"tech": "techs", "requires_building": "buildings"},
    ),
    "units": TableSpec(
        "units",
        "units",
        (
            "faction",
            "domain",
            "role",
            "cost",
            "moves",
            "strength",
            "ranged_strength",
            "range",
            "vision",
            "tech",
        ),
        {"tech": "techs", "requires_resource": "resources", "alien_tech": "alien_techs"},
    ),
    "techs": TableSpec(
        "techs",
        "techs",
        ("tree", "tier", "cost", "prereqs", "known_at_start"),
        {"prereqs": "techs"},
    ),
    "alien_techs": TableSpec(
        "aliens",
        "techs",
        ("order", "cost", "effects"),
    ),
    "recruit_traits": TableSpec("aliens", "recruit_traits", ("effects",)),
    "recruit_types": TableSpec(
        "aliens",
        "recruit_types",
        ("weight", "focus", "lifespan", "traits"),
        {"traits": "recruit_traits"},
    ),
    "legendary_recruits": TableSpec(
        "aliens",
        "legendary_recruits",
        ("name", "scores", "lifespan", "traits"),
        {"traits": "recruit_traits"},
    ),
    "continents": TableSpec(
        "continents",
        "continents",
        ("name", "order", "land_pct", "biomes", "resources", "cities"),
        {"biomes": "biomes", "resources": "resources"},
    ),
}

FILES = (
    "aliens",
    "tuning",
    "terrain",
    "resources",
    "improvements",
    "buildings",
    "units",
    "techs",
    "continents",
    "bots",
)

YIELDS = ("food", "production", "science", "gold", "beacon")
TREES = frozenset({"economic", "production", "military", "beacon"})
DOMAINS = ("food", "production", "military", "science", "gold", "beacon")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_tagged(node: Any, path: str, tagged: bool) -> None:
    if isinstance(node, dict):
        here = tagged
        if "status" in node:
            if node["status"] not in STATUSES:
                raise ConfigError(f"{path}: status must be one of {sorted(STATUSES)}")
            here = True
        for key, value in node.items():
            if key in META_KEYS:
                continue
            _check_tagged(value, f"{path}.{key}", here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _check_tagged(value, f"{path}[{i}]", tagged)
    elif isinstance(node, float):
        raise ConfigError(f"{path}: floats are not allowed; use integers (percent, sub-points)")
    elif _is_number(node) and not tagged:
        raise ConfigError(f"{path}: untagged number {node}; wrap it with status and note")


def strip_meta(node: Any) -> Any:
    """Remove tagging metadata, unwrapping `{value: x, status: ...}` to `x`."""
    if isinstance(node, dict):
        if "value" in node and set(node) <= META_KEYS | {"value"}:
            return strip_meta(node["value"])
        return {k: strip_meta(v) for k, v in node.items() if k not in META_KEYS}
    if isinstance(node, list):
        return [strip_meta(v) for v in node]
    return node


def _ref_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    if isinstance(value, dict):
        return list(value)
    return []


def _get_dotted(entry: dict, dotted: str) -> Any:
    node: Any = entry
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    tables: dict[str, dict[str, dict[str, Any]]]
    digest: str
    _cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def t(self, path: str) -> Any:
        """A tuning value by dotted path, with tagging metadata stripped. Treat the result as
        read-only: it is cached and shared."""
        if path in self._cache:
            return self._cache[path]
        node: Any = self.raw["tuning"]
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise KeyError(f"tuning value '{path}' is missing from data/tuning.yaml")
            node = node[part]
        value = strip_meta(node)
        self._cache[path] = value
        return value

    def _section(self, file: str, path: str) -> Any:
        key = f"{file}:{path}"
        if key in self._cache:
            return self._cache[key]
        node: Any = self.raw[file]
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise KeyError(f"value '{path}' is missing from data/{file}.yaml")
            node = node[part]
        value = strip_meta(node)
        self._cache[key] = value
        return value

    def bot(self, path: str) -> Any:
        return self._section("bots", path)

    def alien(self, path: str) -> Any:
        """A value from data/aliens.yaml. Treat as read-only (cached)."""
        return self._section("aliens", path)

    @property
    def alien_techs(self) -> dict[str, dict[str, Any]]:
        return self.tables["alien_techs"]

    def alien_tech_order(self) -> list[str]:
        return sorted(self.alien_techs, key=lambda t: self.alien_techs[t]["order"])

    @property
    def terrains(self) -> dict[str, dict[str, Any]]:
        return self.tables["terrains"]

    @property
    def elevations(self) -> dict[str, dict[str, Any]]:
        return self.tables["elevations"]

    @property
    def features(self) -> dict[str, dict[str, Any]]:
        return self.tables["features"]

    @property
    def biomes(self) -> dict[str, dict[str, Any]]:
        return self.tables["biomes"]

    @property
    def resources(self) -> dict[str, dict[str, Any]]:
        return self.tables["resources"]

    @property
    def improvements(self) -> dict[str, dict[str, Any]]:
        return self.tables["improvements"]

    @property
    def buildings(self) -> dict[str, dict[str, Any]]:
        return self.tables["buildings"]

    @property
    def units(self) -> dict[str, dict[str, Any]]:
        return self.tables["units"]

    @property
    def techs(self) -> dict[str, dict[str, Any]]:
        return self.tables["techs"]

    @property
    def continents(self) -> dict[str, dict[str, Any]]:
        return self.tables["continents"]

    def continent_ids(self) -> list[str]:
        """Continent ids in their configured order."""
        return sorted(self.continents, key=lambda c: self.continents[c]["order"])


def _validate_tables(tables: dict[str, dict[str, dict[str, Any]]]) -> None:
    for name, spec in TABLES.items():
        for entry_id, entry in tables[name].items():
            if not isinstance(entry, dict):
                raise ConfigError(f"{name}.{entry_id}: entry must be a mapping")
            for req in spec.required:
                if req not in entry:
                    raise ConfigError(f"{name}.{entry_id}: missing required field '{req}'")
            for dotted, target in spec.refs.items():
                for ref in _ref_values(_get_dotted(entry, dotted)):
                    if ref not in tables[target]:
                        raise ConfigError(
                            f"{name}.{entry_id}.{dotted}: unknown {target} id '{ref}'"
                        )
    _validate_semantics(tables)


def _check_yields(where: str, yields: Any) -> None:
    if not isinstance(yields, dict):
        raise ConfigError(f"{where}: yields must be a mapping")
    for key in yields:
        if key not in YIELDS:
            raise ConfigError(f"{where}: unknown yield '{key}'")


def _validate_semantics(tables: dict[str, dict[str, dict[str, Any]]]) -> None:
    for table in ("terrains", "elevations", "features", "resources", "improvements"):
        for entry_id, entry in tables[table].items():
            _check_yields(f"{table}.{entry_id}.yields", entry["yields"])
    for entry_id, entry in tables["buildings"].items():
        _check_yields(f"buildings.{entry_id}.yields", entry["yields"])
        _check_yields(f"buildings.{entry_id}.yield_pct", entry["yield_pct"])
    for entry_id, entry in tables["techs"].items():
        if entry["tree"] not in TREES:
            raise ConfigError(f"techs.{entry_id}: tree must be one of {sorted(TREES)}")
    for entry_id, entry in tables["units"].items():
        if entry["faction"] not in ("player", "alien"):
            raise ConfigError(f"units.{entry_id}: faction must be player or alien")
        if entry["domain"] not in ("land", "sea"):
            raise ConfigError(f"units.{entry_id}: domain must be land or sea")
        if entry["role"] not in ("melee", "ranged", "recon", "civilian"):
            raise ConfigError(f"units.{entry_id}: unknown role '{entry['role']}'")
    for entry_id, entry in tables["resources"].items():
        if entry["category"] not in ("bonus", "strategic"):
            raise ConfigError(f"resources.{entry_id}: category must be bonus or strategic")
    for entry_id, entry in tables["improvements"].items():
        if entry["kind"] not in ("tile", "route"):
            raise ConfigError(f"improvements.{entry_id}: kind must be tile or route")
    effect_keys = {"city_strength", "city_hp", "production", "growth", "max_pop", "heal"}
    for entry_id, entry in tables["alien_techs"].items():
        unknown = set(entry["effects"]) - effect_keys
        if unknown:
            raise ConfigError(f"alien_techs.{entry_id}: unknown effects {sorted(unknown)}")
    trait_keys = {"yield_pct", "lifespan_delta", "betrayal_permille", "immortal", "sale_pct"}
    for entry_id, entry in tables["recruit_traits"].items():
        unknown = set(entry["effects"]) - trait_keys
        if unknown:
            raise ConfigError(f"recruit_traits.{entry_id}: unknown effects {sorted(unknown)}")
        bad = set(entry["effects"].get("yield_pct", {})) - set(DOMAINS)
        if bad:
            raise ConfigError(f"recruit_traits.{entry_id}: yield_pct keys must be domains: {bad}")
    for entry_id, entry in tables["recruit_types"].items():
        if not entry["focus"] or set(entry["focus"]) - set(DOMAINS):
            raise ConfigError(f"recruit_types.{entry_id}: focus must be non-empty domains")
        lo, hi = entry["lifespan"]
        if not 0 < lo <= hi:
            raise ConfigError(f"recruit_types.{entry_id}: bad lifespan range")
    for entry_id, entry in tables["legendary_recruits"].items():
        if set(entry["scores"]) - set(DOMAINS):
            raise ConfigError(f"legendary_recruits.{entry_id}: scores must be domains")
    orders = [c["order"] for c in tables["continents"].values()]
    if len(set(orders)) != len(orders):
        raise ConfigError("continents: order values must be unique")


def load(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    overrides: Callable[[dict[str, Any]], None] | None = None,
) -> Config:
    """Load every data file, validate it and return a Config.

    `overrides`, if given, may edit the raw parsed data in place before validation (tests use it
    to change a value without writing new files).
    """
    data_dir = Path(data_dir)
    raw: dict[str, Any] = {}
    for name in FILES:
        path = data_dir / f"{name}.yaml"
        if not path.exists():
            raise ConfigError(f"missing data file {path}")
        with path.open(encoding="utf-8") as fh:
            parsed = yaml.safe_load(fh) or {}
        if not isinstance(parsed, dict):
            raise ConfigError(f"{path}: top level must be a mapping")
        raw[name] = parsed
    if overrides is not None:
        overrides(raw)
    for name, parsed in raw.items():
        _check_tagged(parsed, name, tagged=False)

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    for table, spec in TABLES.items():
        section = raw[spec.file].get(spec.key)
        if not isinstance(section, dict) or not section:
            raise ConfigError(f"{spec.file}.yaml: missing or empty '{spec.key}' section")
        tables[table] = {eid: strip_meta(entry) for eid, entry in section.items()}
    _validate_tables(tables)
    for tech in strip_meta(raw["aliens"].get("recruits", {})).get("rarity_techs", []):
        if tech not in tables["techs"]:
            raise ConfigError(f"aliens.recruits.rarity_techs: unknown tech '{tech}'")
    return Config(raw=raw, tables=tables, digest=canonical.digest(raw))
