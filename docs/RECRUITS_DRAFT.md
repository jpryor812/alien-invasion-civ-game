# Alien recruits: draft roster (M5 proposal)

Status: draft for designer review. Nothing here is in `data/` yet. All numbers are placeholders.
The roster has 50 recruits.

## Council seats

- **Specialist seats: 2 per domain, 12 in total.** Domains: food, production, science, gold,
  beacon, military.
- **General seats: 3.** A general recruit applies its bonus to every city.

A recruit in a specialist seat applies its bonus to that domain. Military is not a yield, so it
needs a `military_pct` key (unit strength and unit production). That is a new key and needs a
decision before promotion.

## Tiers

| Tier | Size | Points or percent | Number in roster |
|---|---|---|---|
| Basic | flat | 10 yield points | 19 |
| Rare | flat | 20 yield points | 15 |
| Epic | flat | 30 yield points | 11 |
| Legendary | percent | +25 to +30% per domain, plus up to +10% general | 5 |

Legendary bonuses are percentages because they stack. A percent bonus grows with the city's
output, so flat points would make a legend swamp the basic and rare tiers. Percentages also stack
with building percents (factory and fusion plant), so legendary values are kept at 25 to 30%.

**Generalists.** Each tier has one low-yield recruit spread across every domain (5 yields plus
military). Their yields are shared evenly, and their military bonus is a small `military_pct`
(outside the point budget). The legendary generalist uses +5% on each domain.

## Traits

The trait list from `data/aliens.yaml` (additional) carries over unchanged: loyal, ambitious,
traitor, immortal, short_lived, berserker, scholar, engineer, charismatic, cautious, greedy. Traits
change yield percentages, lifespan and betrayal chance. They do not change the point budget.

## Roster

Yields are flat points unless the tier is legendary. Seat is the specialist domain or `general`.
Generalists are marked **(gen)**.

### Basic (10 points each): 19 recruits

| # | Name | Yields | Seat | Traits (typical) | Lifespan |
|---|---|---|---|---|---|
| 1 | Tesk Orrin | food 5, production 5 | production | loyal, cautious | 40–70 |
| 2 | Vael Quintor | science 5, beacon 5 | science | scholar, loyal | 50–80 |
| 3 | Irra Summs | gold 6, food 4 | gold | greedy, loyal | 40–70 |
| 4 | Mott Halvar | production 6, gold 4 | military | berserker, loyal | 40–70 |
| 5 | Sel Ambrit | science 4, food 6 | food | scholar, cautious | 50–80 |
| 6 | Dorn Veyl | beacon 5, gold 5 | beacon | charismatic, loyal | 40–70 |
| 7 | Hask Bellow | production 10 | production | berserker, short_lived | 30–60 |
| 8 | Lumen Ysse | food 10 | food | loyal, cautious | 50–80 |
| 9 | Pell Tarragon | science 10 | science | scholar, loyal | 50–80 |
| 10 | Kessa Orr | gold 10 | gold | greedy, traitor | 30–60 |
| 11 | Yoss Marrow | food 3, production 3, beacon 4 | general | loyal | 40–70 |
| 12 | Tibb Sorel | production 5, gold 5 | general | ambitious, loyal | 40–70 |
| 31 | Pim Anders **(gen)** | food 2, production 2, science 2, gold 2, beacon 2; military +5% | general | loyal, cautious | 40–70 |
| 35 | Ob Tennet | food 6, gold 4 | food | loyal, cautious | 40–70 |
| 36 | Sarr Vidic | production 5, science 5 | production | scholar, loyal | 50–80 |
| 37 | Uma Greave | beacon 6, food 4 | beacon | charismatic, loyal | 40–70 |
| 38 | Ferro Dane | gold 5, production 5 | gold | greedy, engineer | 45–75 |
| 39 | Ixa Pell | science 6, gold 4 | science | scholar, cautious | 50–80 |
| 40 | Hollis Cray | food 3, production 3, gold 2, science 2 | general | loyal, cautious | 40–70 |

### Rare (20 points each): 15 recruits

| # | Name | Yields | Seat | Traits (typical) | Lifespan |
|---|---|---|---|---|---|
| 13 | Ghant Wirran | production 12, food 8 | military | berserker, loyal | 40–70 |
| 14 | Ilse Varro | science 12, beacon 8 | science | scholar, ambitious | 50–80 |
| 15 | Moth Caldera | gold 12, food 8 | gold | greedy, loyal | 40–70 |
| 16 | Sirrin Dusk | beacon 10, science 10 | beacon | charismatic, ambitious | 40–70 |
| 17 | Brakka Tull | production 10, gold 10 | production | engineer, greedy | 45–75 |
| 18 | Nyx Halden | science 8, production 6, food 6 | general | scholar, cautious | 50–80 |
| 19 | Oru Fennick | food 10, beacon 10 | food | charismatic, loyal | 40–70 |
| 20 | Quill Anara | gold 8, science 6, beacon 6 | general | ambitious, short_lived | 30–60 |
| 32 | Lerra Quade **(gen)** | food 4, production 4, science 4, gold 4, beacon 4; military +5% | general | loyal, ambitious | 40–70 |
| 41 | Vessa Morrow | science 10, production 10 | science | scholar, ambitious | 50–80 |
| 42 | Dahl Okonn | gold 10, beacon 10 | gold | greedy, charismatic | 40–70 |
| 43 | Tarn Esk | food 12, gold 8 | food | loyal, cautious | 40–70 |
| 44 | Rhea Quill | production 12, beacon 8 | production | engineer, ambitious | 45–75 |
| 45 | Mavek Lore | science 8, food 8, gold 4 | general | scholar, loyal | 50–80 |
| 46 | Oriel Thane | beacon 14, production 6 | beacon | charismatic, short_lived | 30–60 |

### Epic (30 points each): 11 recruits

| # | Name | Yields | Seat | Traits (typical) | Lifespan |
|---|---|---|---|---|---|
| 21 | Teshra Vant | production 15, science 15 | production | engineer, scholar | 45–75 |
| 22 | Corvin Ahl | gold 12, food 10, beacon 8 | general | greedy, ambitious | 40–70 |
| 23 | Ymir Solace | science 16, beacon 14 | science | scholar, cautious | 50–80 |
| 24 | Gerrod Mavis | production 18, gold 12 | military | berserker, ambitious | 40–70 |
| 25 | Lira Quen | food 14, science 8, beacon 8 | food | charismatic, cautious | 50–80 |
| 26 | Surrenne Baas | production 10, science 10, gold 10 | general | ambitious, loyal | 40–70 |
| 33 | Orvik Sten **(gen)** | food 6, production 6, science 6, gold 6, beacon 6; military +5% | general | loyal, ambitious | 40–70 |
| 47 | Dovic Anwe | gold 12, production 9, science 9 | general | greedy, ambitious | 40–70 |
| 48 | Velu Haskar | science 14, beacon 10, gold 6 | science | scholar, cautious | 50–80 |
| 49 | Pyrrha Ness | food 15, beacon 15 | food | charismatic, loyal | 40–70 |
| 50 | Sable Ondrin | production 12, food 10, gold 8 | military | berserker, loyal | 40–70 |

### Legendary (percent bonuses, fixed): 5 recruits

Each legend also has a flat lifespan or is immortal, as shown.

| # | Name | Percent bonus | Seat | Traits | Lifespan |
|---|---|---|---|---|---|
| 27 | Ilyrath the Unbroken | production +25%, military +10% | military | immortal, loyal | immortal |
| 28 | Oss-Vanthe the Archivist | science +30%, beacon +10% | science | scholar, immortal | immortal |
| 29 | Quen Morrow the Forgemaster | production +25%, gold +10% | production | engineer, ambitious | 200 |
| 30 | Mireth Calla the Echo | beacon +30%, food +10%, all cities +5% | beacon | charismatic, traitor | 90 |
| 34 | Ember Kestrel the Quiet Hand **(gen)** | food, production, science, gold, beacon +5% each; military +5% | general | loyal, cautious | 150 |

## Open questions

- Confirm the military percent key (`military_pct`) and what it affects. Generalists use it.
- Confirm the point budgets: basic 10, rare 20, epic 30.
- Confirm legendary percent values (25 to 30 per domain) against the factory and fusion percents.
- Decide the archetype rolls for basic and rare recruits, and whether the roster is fixed or random.
- Decide whether a legendary recruit can hold a specialist seat and a general seat at once.
- Check that each specialist seat has enough recruits to fill it at every tier. Military currently
  has fewer epic and legendary options than the others.
