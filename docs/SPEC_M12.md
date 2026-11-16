# M12 — A readable alien that reacts to you (designer, 2026-11-15)

Approved by the designer ("all sounds good ... let's do all of those"). Every number is a tunable
in data/aliens.yaml or data/tuning.yaml.

Why: the aliens were scenery, not an opponent. Buildings answered no felt need, and freeing a
city was the only verb. Models: Into the Breach and Spirit Island (telegraphed enemy intent),
Factorio (the threat grows because you grow), Civ V (choosing where to found a city).

## 1. Announced alien plans
- The director no longer starts a siege of a player city at once. It forms a **strike plan**:
  source alien city, target player city, the units committed, and a launch turn 3 turns ahead
  (`plans.strike_turns`). The committed units gather at the source; on the launch turn they get
  siege orders, as before.
- **Raids** on roads and improvements stay unannounced (they are small).
- Plans against a player's cities are always known to that player (radio intercepts). The
  source city and the committed strength show if the player has explored the source.
- Client: a red arrow from source to target with the countdown, and a **Threats** list in the
  "Needs attention" panel (turns left, strength committed against your city's defence).

## 2. Attention (heat)
- Each player has **heat** each turn: population, plus `heat` on buildings (beacons, factories,
  labs, ports), plus active convoys. Shown in the top bar with a tooltip.
- Strike targets score heat: hotter players draw more and bigger plans. Growing versus lying
  low becomes a choice, as pollution is in Factorio.

## 3. What each alien city holds
- Each alien-held city has seeded **contents** (data/aliens.yaml `contents`): survivors (+2
  population), a working lab (+science), a captive specialist (a citizen with 9 stat points), a
  weapons cache (free units), a hive heart (stronger garrison; frees an alien tech), a fuel
  depot (gold).
- Seeing the city gives a **rumour** (the category: people, knowledge, arms, wealth, danger).
  A recon unit next to it, or espionage, gives the exact contents.
- Freeing the city gives its contents (beacon/liberation.py). Choosing which city to free first
  is our version of choosing where to found a city.

## 4. More ways to free a city
- **Sabotage**: engineers or recon next to an alien city may sabotage it once per turn: it
  loses a share of its hit points; the saboteur takes damage from a seeded roll.
- **Arm the resistance**: a unit next to an alien city may smuggle weapons in (gold); each level
  of resistance gives a chance each turn of an uprising that damages the city and its garrison.
- **Nests**: each alien city has 1-2 nests within 3 hexes. Each nest speeds the city's healing
  and spawning; a player military unit ending its turn on a nest destroys it.

## 5. Pressure audit
- docs/PRESSURE_AUDIT.md lists every building and unit and the threat or need it answers; those
  without one are tied to a plan, a rumour or heat, or flagged for later.

## Acceptance
- Tests: plans form with a countdown and launch on time, are fog-safe, heat raises the chance of
  being targeted, contents are seeded and given on liberation, rumours and full intel, sabotage,
  resistance, uprisings, nests, save round-trips.
- pytest and ruff pass; the 10-seed batch finishes; the client shows arrows, threats, heat,
  rumours and the new actions, checked in the browser.
