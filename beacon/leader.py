"""The leader (docs/SPEC_M11.md, designer 2026-11-15; SPEC_M9 section 5 and its answers).

- Every player has a leader, the head of its council (not a unit on the map). The AI's leaders
  are generated from the seed; a human may remake theirs on the creation screen before turn 1.
- Six skills, one per domain, start at +1. Each adds its value to that yield in every city, as a
  council member does; military adds city strength.
- XP comes from the player's achievements (its MVP credit ledger). Each level gives a skill
  point; reaching a milestone threshold offers a choice of bonuses for this game; at level 5 the
  leader picks a third trait. Traits and bonuses are effects in the tech-effect format.
- Age: the start age plus a year every four turns. The leader never dies (designer).
- Family: a child with a grown citizen or a seated alien recruit, born in the capital a few turns
  later. Hybrids (alien parent) are stronger; some cities refuse them; on the council they risk
  being voted out.
"""

from __future__ import annotations

from typing import Any

from beacon import hexgrid, rng
from beacon.config import DOMAINS, YIELDS, Config
from beacon.state import ACTIVE, Citizen, City, GameState, Leader, Player

Events = list[dict[str, Any]]


# -- making a leader ---------------------------------------------------------------------------


def looks(cfg: Config) -> dict[str, str]:
    """look id -> sex."""
    return {entry["id"]: entry["sex"] for entry in cfg.leader("looks.list")}


def generate(cfg: Config, seed: int, pid: str, taken: tuple[str, ...] = ()) -> Leader:
    """A leader dealt from the seed (every AI's, and a human's until remade); `taken` names are
    not reused."""
    r = rng.stream(seed, "leader", "make", pid)
    look = r.choice(sorted(looks(cfg)))
    sex = looks(cfg)[look]
    start = cfg.leader("start")
    traits = sorted(cfg.leader("traits.list"))
    r.shuffle(traits)
    skills = dict.fromkeys(DOMAINS, 0)
    for _ in range(start["skill_points"]):  # spread by seed, at most skill_max in any one
        open_ = [d for d in DOMAINS if skills[d] < start["skill_max"]]
        skills[r.choice(open_)] += 1
    return Leader(
        name=r.choice([n for n in cfg.leader(f"names.{sex}") if n not in taken]),
        sex=sex,
        look=look,
        start_age=r.randint(start["age_min"], start["age_max"]),
        skills=skills,
        traits=sorted(traits[: start["traits"]]),
    )


def skills_problem(cfg: Config, skills: dict[str, int]) -> str | None:
    start = cfg.leader("start")
    if set(skills) - set(DOMAINS) or any(not isinstance(v, int) for v in skills.values()):
        return "skills are the six domains, in whole points"
    if any(v < 0 or v > start["skill_max"] for v in skills.values()):
        return f"each skill takes 0 to {start['skill_max']} points"
    if sum(skills.values()) != start["skill_points"]:
        return f"spend all {start['skill_points']} skill points"
    return None


def create_problem(
    cfg: Config,
    name: str,
    sex: str,
    look: str,
    age: int,
    traits: tuple[str, ...],
    skills: dict[str, int] | None = None,
) -> str | None:
    start = cfg.leader("start")
    if skills is not None:
        why = skills_problem(cfg, skills)
        if why:
            return why
    if not name.strip() or len(name) > 40:
        return "a leader needs a name of 1-40 characters"
    if look not in looks(cfg):
        return f"unknown look {look!r}"
    if looks(cfg)[look] != sex:
        return f"look {look} is a {looks(cfg)[look]}"
    if not start["age_min"] <= age <= start["age_max"]:
        return f"age must be {start['age_min']}-{start['age_max']}"
    if len(set(traits)) != start["traits"] or any(
        t not in cfg.leader("traits.list") for t in traits
    ):
        return f"choose {start['traits']} different traits"
    return None


def age(cfg: Config, state: GameState, leader: Leader) -> int:
    return leader.start_age + state.turn // cfg.leader("start.turns_per_year")


# -- XP, levels and points ---------------------------------------------------------------------


def xp(cfg: Config, player: Player) -> int:
    weights = cfg.leader("xp.sources")
    return sum(player.credits.get(k, 0) * w for k, w in sorted(weights.items()))


def xp_for_level(cfg: Config, level: int) -> int:
    """Total XP a leader needs to reach `level` (level 1 needs none)."""
    x = cfg.leader("xp")
    n = level - 1
    return x["first"] * n + x["step"] * n * (n - 1) // 2


def level_for(cfg: Config, total: int) -> int:
    level = 1
    while xp_for_level(cfg, level + 1) <= total:
        level += 1
    return level


def points(cfg: Config, leader: Leader) -> int:
    """Skill points to spend."""
    return (leader.level - 1) * cfg.leader("xp.points_per_level") - leader.spent


# -- what the leader gives ----------------------------------------------------------------------


def effects(cfg: Config, leader: Leader | None) -> list[tuple[str, dict[str, Any]]]:
    """(source, effects) for each trait and chosen bonus, in the tech-effect format."""
    if leader is None:
        return []
    traits = cfg.leader("traits.list")
    out = [(f"trait {traits[t]['name']}", traits[t]["effects"]) for t in leader.traits]
    stones = cfg.leader("milestones.list")
    for b in leader.bonuses:
        stone, option = b.split(":")
        spec = stones[stone]["options"][option]
        out.append((f"bonus {spec['name']}", spec["effects"]))
    return out


def skill_lines(state: GameState, cfg: Config, city: City) -> list[tuple[str, str, int]]:
    """The leader's skills as yield lines in each of the owner's cities (not military)."""
    player = state.players.get(city.owner or "")
    if player is None or player.leader is None or city.status != ACTIVE:
        return []
    lead = player.leader
    return [(f"leader:{lead.name}", y, lead.skills[y]) for y in YIELDS if lead.skills.get(y)]


def city_strength(state: GameState, cfg: Config, city: City) -> int:
    """Strength the leader's military skill adds to each of the owner's cities."""
    player = state.players.get(city.owner or "")
    if player is None or player.leader is None:
        return 0
    return player.leader.skills.get("military", 0) * cfg.t("citizens.military_strength")


# -- milestones and choices ----------------------------------------------------------------------


def tally(state: GameState, pid: str, key: str) -> int:
    return state.players[pid].credits.get(key, 0)


def options(cfg: Config, leader: Leader, choice: str) -> list[str]:
    """What a waiting choice offers: bonus ids for a milestone, trait ids for "trait"."""
    if choice == "trait":
        return [t for t in sorted(cfg.leader("traits.list")) if t not in leader.traits]
    stone = choice.split(":")[0]
    return list(cfg.leader(f"milestones.list.{stone}.options"))


def choose_problem(cfg: Config, leader: Leader, choice: str, option: str) -> str | None:
    if choice not in leader.choices:
        return f"no choice {choice!r} waiting"
    if option not in options(cfg, leader, choice):
        return f"{option!r} is not offered for {choice}"
    return None


def choose(cfg: Config, leader: Leader, choice: str, option: str) -> None:
    leader.choices.remove(choice)
    if choice == "trait":
        leader.traits = [*leader.traits, option]
    else:
        leader.bonuses = [*leader.bonuses, f"{choice.split(':')[0]}:{option}"]


def raise_problem(cfg: Config, leader: Leader, domain: str) -> str | None:
    if domain not in DOMAINS:
        return f"unknown skill {domain!r}"
    if points(cfg, leader) <= 0:
        return "no skill points to spend"
    return None


def raise_skill(leader: Leader, domain: str) -> None:
    leader.skills = {**leader.skills, domain: leader.skills[domain] + 1}
    leader.spent += 1


def _progress(state: GameState, cfg: Config, pid: str) -> Events:
    """New levels and milestones for one player's leader."""
    lead = state.players[pid].leader
    assert lead is not None
    events: Events = []
    level = level_for(cfg, xp(cfg, state.players[pid]))
    third = cfg.leader("traits.third_trait_level")
    while lead.level < level:
        lead.level += 1
        events.append({"kind": "leader_level", "player": pid, "level": lead.level})
        if lead.level == third and "trait" not in lead.choices:
            lead.choices = [*lead.choices, "trait"]
    for stone, spec in sorted(cfg.leader("milestones.list").items()):
        have = tally(state, pid, spec["key"])
        for at in spec["at"]:
            tag = f"{stone}:{at}"
            if have >= at and tag not in lead.milestones:
                lead.milestones = [*lead.milestones, tag]
                lead.choices = [*lead.choices, tag]
                events.append(
                    {"kind": "leader_milestone", "player": pid, "milestone": stone, "at": at}
                )
    return events


# -- family --------------------------------------------------------------------------------------


def capital(state: GameState, pid: str) -> City | None:
    return next(
        (c for c in state.cities if c.owner == pid and c.is_capital and c.status == ACTIVE), None
    )


def partner_of(state: GameState, partner: str) -> Citizen | Any | None:
    kind, _, ident = partner.partition(":")
    if kind == "citizen":
        return state.citizens.get(ident)
    if kind == "recruit":
        return state.recruits.get(ident)
    return None


def family_block(state: GameState, cfg: Config, pid: str) -> str | None:
    """Why no family can be started now (whoever the partner), or None."""
    lead = state.players[pid].leader
    if lead is None:
        return "no leader"
    if lead.expecting is not None:
        return "a child is already on the way"
    if state.turn < lead.rest_until:
        return f"the family can grow again on turn {lead.rest_until}"
    kids = [state.citizens.get(str(k)) for k in lead.children]
    if any(k is not None and not k.adult for k in kids):
        return "the youngest child has not grown up yet"
    if capital(state, pid) is None:
        return "a child is born in the capital, and there is none"
    return None


def family_problem(state: GameState, cfg: Config, pid: str, partner: str) -> str | None:
    block = family_block(state, cfg, pid)
    if block:
        return block
    who = partner_of(state, partner)
    if who is None:
        return f"unknown partner {partner!r}"
    if partner.startswith("citizen:"):
        if state.cities[who.city].owner != pid or not who.adult:
            return "the partner must be a grown citizen of yours"
        if who.kin:
            return "not with the leader's own child"
    elif who.patron != pid or not who.seats:
        return "an alien partner must be a recruit seated on your council"
    return None


def start_family(state: GameState, cfg: Config, pid: str, partner: str) -> None:
    lead = state.players[pid].leader
    assert lead is not None
    lead.expecting = partner
    lead.due = state.turn + cfg.leader("family.birth_turns")


def _hybrid_stats(state: GameState, cfg: Config, lead: Leader, rec: Any, cid: int) -> dict:
    """Points: the average of both parents' totals, spread in proportion to their values."""
    alien = {d: max(0, rec.scores.get(d, 0)) for d in DOMAINS}
    total = (sum(lead.skills.values()) + sum(alien.values())) // 2
    weight = {d: lead.skills.get(d, 0) + alien[d] for d in DOMAINS}
    wsum = sum(weight.values()) or 1
    stats = {d: total * weight[d] // wsum for d in DOMAINS}
    left = total - sum(stats.values())
    order = sorted(DOMAINS, key=lambda d: (-(total * weight[d] % wsum), DOMAINS.index(d)))
    for d in order[:left]:
        stats[d] += 1
    return {d: v for d, v in stats.items() if v}


def _birth(state: GameState, cfg: Config, pid: str) -> Events:
    from beacon import citizens  # citizens imports economy-adjacent modules

    lead = state.players[pid].leader
    assert lead is not None and lead.expecting is not None
    home = capital(state, pid)
    partner, lead.expecting, lead.due = lead.expecting, None, -1
    lead.rest_until = state.turn + cfg.leader("family.cooldown_turns")
    if home is None:
        return []
    who = partner_of(state, partner)
    home.pop += 1
    child = citizens.make(state, cfg, home, adult=False)
    child.kin = True
    if partner.startswith("recruit:") and who is not None:
        child.hybrid = True
        child.stats = _hybrid_stats(state, cfg, lead, who, child.id)
        r = rng.stream(state.seed, "leader", "hybrid", child.id)
        traits = sorted(cfg.t("citizens.traits"))
        child.traits = (
            [r.choice(traits)] if rng.percent_roll(r, cfg.leader("family.trait_pct")) else []
        )
    lead.children = [*lead.children, child.id]
    return [
        {
            "kind": "leader_child_born",
            "player": pid,
            "citizen": child.id,
            "name": child.name,
            "hybrid": child.hybrid,
            "city": home.id,
            "stats": dict(child.stats),
        }
    ]


def child_grew_up(state: GameState, citizen: Citizen) -> None:
    """Count a grown child of a leader (XP and the parent milestone)."""
    if not citizen.kin:
        return
    from beacon.liberation import credit  # liberation imports nothing from here

    owner = state.cities[citizen.city].owner
    if owner in state.players:
        credit(state, owner, "leader_children")


# -- hybrids and the cities ----------------------------------------------------------------------


def seed_attitudes(state: GameState, cfg: Config) -> None:
    pct = cfg.leader("hybrids.refuse_pct")
    for city in state.cities:
        city.refuses_hybrids = rng.percent_roll(
            rng.stream(state.seed, "leader", "attitude", city.id), pct
        )


def can_work_here(state: GameState, c: Citizen) -> bool:
    return not (c.hybrid and state.cities[c.city].refuses_hybrids)


def may_sit(state: GameState, c: Citizen) -> bool:
    return c.banned_until <= state.turn


def _vote_out(state: GameState, cfg: Config, pid: str) -> Events:
    from beacon import citizens

    h = cfg.leader("hybrids")
    events: Events = []
    for c in citizens.council_of(state, pid):
        if not c.hybrid:
            continue
        roll = rng.stream(state.seed, "leader", "vote", state.turn, c.id)
        if not rng.percent_roll(roll, h["vote_out_pct"]):
            continue
        c.banned_until = state.turn + h["ban_turns"]
        if c.job.startswith("council"):
            c.job = "auto"
        moved = None
        if state.cities[c.city].refuses_hybrids:
            here = state.cities[c.city].tile
            ok = [
                x
                for x in state.cities
                if x.owner == pid and x.status == ACTIVE and not x.refuses_hybrids
            ]
            if ok:
                dest = min(ok, key=lambda x: (hexgrid.distance(x.tile, here, state.width), x.id))
                state.cities[c.city].pop -= 1
                dest.pop += 1
                c.city, moved = dest.id, dest.id
        events.append(
            {"kind": "hybrid_voted_out", "player": pid, "citizen": c.id, "name": c.name}
            | {"to": moved}
        )
    return events


# -- the turn ------------------------------------------------------------------------------------


def end_of_turn(state: GameState, cfg: Config) -> Events:
    events: Events = []
    for pid in state.player_ids():
        lead = state.players[pid].leader
        if lead is None:
            continue
        if lead.expecting is not None and state.turn >= lead.due:
            events.extend(_birth(state, cfg, pid))
        events.extend(_vote_out(state, cfg, pid))
        events.extend(_progress(state, cfg, pid))
    for e in events:
        e.setdefault("turn", state.turn)
    return events


def wardrobe_problem(cfg: Config, outfit: str, accessories: tuple[str, ...]) -> str | None:
    w = cfg.leader("wardrobe")
    if outfit not in w["outfits"]:
        return f"unknown outfit {outfit!r}"
    bad = [a for a in accessories if a not in w["accessories"]]
    if bad or len(set(accessories)) != len(accessories):
        return f"unknown or repeated accessories {bad}"
    return None
