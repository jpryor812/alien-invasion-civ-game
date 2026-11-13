# Kickoff prompt for the first chat in this repo

Paste this into a new Claude Code session opened in this repository.

---

I am building an original turn-based 4X strategy game about an alien invasion of modern Earth, in
the spirit of Civilization V's hex map, cities and tech, with Crusader Kings III style characters.
Read CLAUDE.md and docs/DESIGN.md first; they record every decision so far.

In short: six players lead six continents (North America, South America, Europe, Asia, Africa,
Oceania). Nobody fights each other; all fight the aliens, who keep Earth under permanent fog.
The world wins or loses together, but each player is ranked by an MVP score. A fourth tech tree,
beacon, lets you recruit random alien characters (military, science, production and beacon
scores, traits, councils) who can be kept, sold or gifted. Fallen continents can be revived. The
endgame is a shared missile-barrage project against the mothership, and humanity can still lose
after it falls.

We build the headless Python simulation first, as in my earlier game (an energy-diplomacy sim in
../energy-game-main, which you may look at for structure and testing style but not copy
content from). Start with milestone M0 and M1 from the design doc:

1. Propose a short plan for M0 (tooling, config, seeded RNG, state) and M1 (one continent: hex
   map, terrain, resources, known and lost cities, fog).
2. Wait for my approval before coding.
3. Then build them with tests, a summary of what you assumed, and a commit.

Ask me about anything in the design doc that is marked OPEN and that blocks the work. Do not push
to GitHub without asking me.
