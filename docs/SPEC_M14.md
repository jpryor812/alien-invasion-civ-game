# M14 — The survivor start (designer, 2026-11-15)

Approved by the designer: the survivor start is the normal start, with a Classic start option.
Models: Fallout 4 and State of Decay (scavenge, recruit, craft), The Banner Saga (a band on a
dying map), Spore (eras on one world, but with everything carried over).

## 1. The band
- A new game puts each player's **leader and four survivors** on their continent, a few hexes
  from the nearest lightly held alien town, instead of cities and an army.
- Designer's numbers: the leader is a unit with 20 attack; each survivor (civilian) has 10.
  The leader is on the map only in this era.
- AI players start the same way.

## 2. Scavenging
- Search sites (the "?" finds, plus more of them near the start) hold **gear** and **people**:
  - weapons (+5 attack), armour (+5 defence), alien weapons (+12 attack, rare);
  - a survivor who joins the band (a new 10-attack unit);
  - food or scrap (no economy yet: scrap is kept for the first city's production).
- A unit can carry one weapon and one armour. Gear moves with the unit and stays after the era.
- Seeded so that an upgrade is usually found within 5 turns.

## 3. The first town
- The nearest alien town to each band is held lightly. Rule of thumb (designer): the band cannot
  take it without at least one upgrade or one more survivor, and should take it by about turn 10.
- Taking it makes it the player's **capital**: the band's survivors become its first citizens
  (named, with stats), the leader leaves the map to lead from the capital, scrap becomes
  production, and the normal game begins (research, production, council).
- **Hiding**: alien patrols do not chase bands outside their sight; units in forest or hills are
  harder to spot (one hex less sight for aliens).

## 3b. Revisions before the first playtest (designer 2026-11-16)
- No crate beside the band: gear lies one hex past its sight; the town is found second.
- The barricade rule is not told to the player.
- Contact only by radio: a founded city must rebuild its radio tower (cheap, about 2 turns) to
  reach other continents and the council (replaces radio contact at turn 1 from SPEC_M13).
- The AI uses every new tool (radio, UAV, sabotage, resistance, nests, strike defence).

## 4. Losing the band
- If the leader's unit is destroyed before the first town is taken, the leader escapes to a
  safe hex with two new survivors (designer); a few turns are lost.

## 5. Classic start
- The New Game screen has a "Classic start" option: cities and an army from turn 1, as before.
  The batch runner and tests can choose either.

## Acceptance
- Tests: the band and its strengths, gear found and applied, recruiting, the first town cannot
  be taken by the bare band and can with one upgrade, capture makes a capital and citizens,
  escape on loss, AI survivors take their towns, classic start unchanged.
- A batch of 10 seeds: median first upgrade by turn 5, first town by about turn 10 for most
  players; pytest and ruff pass; browser check of the opening.
