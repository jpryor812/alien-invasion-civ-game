# M9 spec: story, events, starfall and the leader (draft for the designer)

Status: approved for steps 1-3 (designer, 2026-11-14); answers to Q1-Q6 are folded in below
and summarised in section 9. Review point after step 3.

## 1. The event system (foundation)

Everything below runs on one data-driven system, so new events can be written in a data file
without code.

- An **event** has: an id, a trigger (conditions plus a chance per turn or per occasion), a
  title, a picture key, a body text, and 0-3 **choices**. Each choice has a label and outcomes.
  An event with no choice is pure luck (good or bad).
- **Triggers** read the game: turn, a unit just fought or died, a city just liberated, a tech
  known, a citizen's or recruit's traits, a flag set by an earlier choice, and so on.
- **Outcomes** change the game: gold, science, citizens, a unit, a recruit, a city's HP, an
  alien unit spawning, a temporary modifier ("for 10 turns"), or a **flag** that later events read.
  Flags are how the story branches.
- **Pace**: about one notable event every 20 turns per player, mixing good, bad and in-between.
  Starfall has its own pace (section 3).
- **Presentation**: small events are a pop-up card (picture, text, choices); big ones (a shard
  claimed, a hybrid child born, a leader level) get the full wonder-style screen: a large
  illustration, a flavour quote and the effect. Placeholder art until the graphics push.

## 2. Exploration rewards (early game, like Civ's ruins)

Hidden sites in the fog of every continent, a handful each, placed by the seed. The first land
unit to step on one collects it:

| Find | Reward |
|---|---|
| Survivor camp | +1 citizen in the nearest city of yours (a grown citizen with stats) |
| Banished alien | an alien recruit, ready for a council seat |
| Ship wreckage | science (see **Q1**) |
| Supply cache | gold |
| Abandoned armoury | a free infantry unit |
| Ambush (rare) | an alien unit appears next to yours |

**Q1** Wreckage: you wrote "one-time, just +20". Is that +20 science once (a small nudge, about
one turn of early research), or +20 science a turn for a while (say 10 turns)? I lean to +20 a
turn for 10 turns, still modest.

## 3. Starfall (the wonder race, against the aliens)

When the aliens came they left a wormhole open; deep-space shards fall through it.

- **Pace**: about every 20 turns. A shard can land on any continent.
- **Warning**: 3 turns before impact everyone sees a streak and a landing cone on the map ("A
  shard is falling: impact in 3 turns, somewhere in the marked region"). Aliens see it too.
- **Impact**: the site glows through the fog. To claim it, an engineer or a scout must stand on
  it and **mine** for 5 turns (other soldiers cannot mine, but they guard it). Leaving or dying
  pauses the work.
- **Aliens race too**: they send a miner with an escort. Whoever finishes mining gets the reward.
  Target: humans win about 60-70% of shards overall (tuned with the AI batches).
- **Rewards grow with the game**: a shard claimed late is worth more than an early one.
  - Preserving compound: cities grow faster.
  - Starmetal: +production in every city.
  - New elements: +science in every city.
  - Exotic matter (rare): +beacon.
  - Living alloy (rare): your units' strength up.
  - If the aliens claim it: an alien tech jump or stronger alien forms.
- **The moment**: claiming a shard opens the full wonder-style screen for the claimer; everyone
  else gets a notice ("Europe claimed the Starmetal shard at the Danube").
- Whoever mines it gets it, ally or not; if your unit is closer to a shard on another continent,
  you may go for it.

## 4. Events chosen so far

- **Refugee column** (after you liberate a city): the city is in shock: its yields are reduced
  until it recovers, 2 turns per citizen. You may move citizens to a productive city of yours to
  speed recovery (each one moved shortens it by 2 turns).
- **Captured soldier** (a unit of yours dies): sometimes one of its crew lived, joined the aliens
  to save himself, and gave away your base: for 10 turns your nearest city is likelier to be
  attacked.
- **Infection** (a non-mechanised unit survives an alien melee attack): rarely, about 2-3 times a
  game, something hatches inside it. A full-screen moment, then the unit becomes an alien unit
  of similar strength. Never tanks, walkers, ships or other machines.
- **Council defection**: sometimes a council member, human or alien, leaves to join the aliens
  (recruits already can; this extends it to citizens).
- **Resistance** (needs beacon rarity 2 or 3, **Q2**): citizens held in an alien city signal for
  help: the fog flashes purple over the city. Within 5 turns a resistance rises and starts
  fighting from inside:
  - every 3 turns after that, one citizen dies and the city takes 30 damage;
  - between those, the city heals 10 a turn, so the resistance never takes the city alone;
  - free the city quickly to save its people, or time your assault for just after a strike
    (cheaper, at the cost of a citizen).
- **Mothership strikes**: already in the game.

**Q2** Resistance: rarity 2 (Signal Amplification) or 3 (Harmonic Lattice)? I lean to 2, so it
appears mid-game.

## 5. The leader

You play a leader, a character of your own.

- **Who**: name, look and sex chosen at the start (look from a small set now; custom looks with
  Meshy later). The leader is not a unit on the map.
- **Parent of your people**: every citizen born in your cities counts as a child of the leader's
  line: a newborn's stats lean toward the leader's strengths (**Q3**).
- **Hybrid children**: the leader can start a family with an alien recruit of the opposite sex.
  Hybrid children:
  - are stronger than citizens (**Q4**: say 9 stat points instead of 6) but weaker than recruits;
  - may carry one alien trait;
  - grow up like other children.
- **Cities that refuse hybrids**: each city has an attitude, seeded at the start, and events and
  buildings can change it. In a refusing city a hybrid cannot work a tile, but can still sit on
  the council.
- **Voted out**: a hybrid on the council has a small chance each turn of being voted out. It
  then has to work in a city that accepts hybrids.
- **Leader levels** (in-game achievements): each milestone lets you choose one of 2-3 bonuses.
  Bonuses last this game only.

  | Milestone | Example choices |
  |---|---|
  | Liberate 1 / 5 / 10 cities | +5% attack for all soldiers; or half production for your next unit; or +1 citizen in a freed city |
  | Have 1 / 3 / 5 children | faster growing up; or +1 stat point for newborns |
  | Have 1 / 2 / 3 hybrid children | a hybrid-accepting city; or +1 council seat |
  | Defeat 10 / 20 / 30 alien units | +10 healing; or a free veteran unit |
  | Save a resistance (free the city before all citizens are lost) | +1 citizen in that city; or the city heals fully |
  | Claim 1 / 3 shards | the next shard's warning comes 2 turns earlier; or miners work faster |

- **Career and wardrobe** (across games): career totals carry from game to game (cities freed,
  shards claimed, children...). Career milestones unlock **cosmetic** rewards only: uniforms,
  insignia, banners, a wardrobe for your leader. For example, 25 cities freed in your career
  unlocks a military uniform. Gameplay bonuses never carry over. Stored in a local profile file
  for now; with accounts once multiplayer exists.

**Q3** Should births always lean toward the leader, or only children the leader is named
parent of (e.g. one child every N births)? I read "the leader is the parent of new citizens" as
all births leaning toward the leader.

**Q4** Hybrid strength: 9 stat points (citizens have 6), or a recruit-style percent score at
half a recruit's strength? Hybrids also count as citizens (they can work tiles), right?

**Q5** Families: a choice the player makes (a button on the council screen, with a cooldown), or
an event that happens to a leader with an opposite-sex recruit seated near them?

**Q6** AI leaders: do the AI continents get leaders, children, hybrids and levels too (fair, and
the AIs would play the same game), or only the human?

## 6. Example texts (tone to build from)

Short, plain, a little grim, never gory. Second person.

**Refugee column**
> *Titled: The Long Road Back*
> They came out of Montreal on foot, carrying what the hive left them: nothing, mostly. The city
> is yours again, but the people are not ready to work. Some ask to be sent south to Chicago,
> where the lights still come on at night.
> - **Let them stay.** *Montreal recovers in 6 turns.*
> - **Send some to Chicago.** *Choose citizens to move; each one shortens the recovery by 2 turns.*

**Captured soldier**
> *Titled: One Came Back Wrong*
> Your patrol near the Rhine was overrun. The scouts found every body but one. Days later a
> voice on the alien channel spoke our grid codes in a calm, tired voice.
> *For 10 turns, aliens are likelier to strike Berlin.*

**Infection**
> *Titled: Something in the Ranks*
> The medics said the wound was clean. Then the fever, then the stillness, then the sound, a wet
> click from inside the chest of a soldier who had stopped breathing an hour before.
> *Your infantry in the Andes is lost. Where it stood, an alien drone unfolds.*

**Resistance**
> *Titled: Purple on the Horizon*
> At night the cloud over Kyiv glowed violet: our old emergency frequency, bounced off the
> hive's own spires. Someone in there is still fighting. They will not last long alone.
> *A resistance will rise in Kyiv in 5 turns. Free the city before they are all gone.*

**Starfall claimed** (wonder-style screen)
> *Starmetal, mined at the Danube Shard*
> "It came down burning and it came down singing. When it cooled, nothing we owned could scratch
> it." *(field notes, 4th Engineer Corps)*
> *+15% production in every city.*

## 7. A first draft of the alien lore

A spine for the story events, revealed piece by piece through beacon research, espionage and
liberations:

1. **The Arrival**: the Hive came through a wound in space, a wormhole they tore open and could
   not close. They did not come to conquer; they came running.
2. **The Choir**: the aliens are not one mind but a chorus of bonded broods, held together by
   the mothership's song. Beacons work because they sing back. That is why some aliens answer
   us.
3. **What hunts the Hive**: whatever drove them here is still on the far side of the wormhole.
   The shards falling through are debris from that other war.
4. **The choice at the end**: destroying the mothership silences the Choir. Recruits and hybrids
   are the proof that the two peoples could live together. Late-game events ask what kind of
   victory you want, and your choices along the way (refugees sheltered, hybrids raised,
   recruits kept loyal) decide which endings are open.

The endings are an idea for later, not part of M9.

## 8. Build order (proposed)

1. The event system with pop-ups and the wonder-style screen (placeholder pictures).
2. Exploration rewards.
3. Starfall, with the AI and aliens racing for shards.
4. The chosen events: refugee column, captured soldier, infection, council defection,
   resistance.
5. The leader: creation screen, births leaning to the leader, hybrids, city attitudes, vote-out.
6. Leader levels with bonus choices; career totals and the cosmetic wardrobe (local profile).

Each step ends with tests, a balance batch and a commit, as before. The review point is after
step 3 (the event system, exploration rewards and Starfall), so you can play them before the
leader work.

## 9. Designer answers (2026-11-14)

- **Q1 Wreckage**: +100 science, once (toward the current research).
- **Q2 Resistance**: needs beacon rarity 2 (Signal Amplification).
- **Q3 Births**: newborns keep random strengths (the leader does not shape them).
- **Q4 Hybrids**: a hybrid's stat points are the average of the leader's 6 and the alien
  parent's total (e.g. 6 and 30 make 18).
- **Q5 Families**: a button with a cooldown. Choose a human or alien partner; the child is born a
  few turns later; once that child has grown up you may start another.
- **Q6 AI leaders**: yes, the AI continents have leaders, children, hybrids and levels too.
- **Leader XP and skills**: achievements also fill an XP bar; each level lets the leader raise a
  skill. Skills are the six domains (food, production, military, science, gold, beacon), starting
  at +1 each and growing over the game (e.g. +4/+3/+2/+7/+4/+2).
- **The council has 16 seats**: the leader at its head, 3 vice-presidents (the general seats) and
  2 specialists in each of the six domains.

