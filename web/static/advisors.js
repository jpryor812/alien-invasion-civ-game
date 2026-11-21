// Advisors: short pop-ups that explain a rule the first time it matters (Civ V style).
// A few at the start of a game, then one whenever something noteworthy happens for the first
// time. Each tip shows once per game; "Don't show advice again" turns them all off.
// Remembered in localStorage (a per-viewer convenience: if storage is unavailable, tips simply
// show again).
"use strict";

(function () {
  // Four original advisors, drawn as emblems (no portraits of real people).
  const ADVISORS = {
    military: { name: "Military Advisor", color: "#d1503f", glyph: '<path d="M22 14l20 20M42 14L22 34M18 30l6 6M46 30l-6 6" stroke="#fff4d6" stroke-width="4" stroke-linecap="round"/>' },
    economic: { name: "Economic Advisor", color: "#e0b03a", glyph: '<circle cx="32" cy="26" r="12" fill="none" stroke="#fff4d6" stroke-width="4"/><path d="M32 18v16M27 22h8M27 30h8" stroke="#fff4d6" stroke-width="3"/>' },
    science: { name: "Science Advisor", color: "#3b8fd0", glyph: '<path d="M27 12h10M29 12v10l-9 16h24l-9-16V12" fill="none" stroke="#fff4d6" stroke-width="4" stroke-linejoin="round"/>' },
    beacon: { name: "Beacon Advisor", color: "#9b4fd0", glyph: '<circle cx="32" cy="32" r="4" fill="#fff4d6"/><path d="M22 24a14 14 0 0 1 20 0M16 18a22 22 0 0 1 32 0" fill="none" stroke="#fff4d6" stroke-width="4" stroke-linecap="round"/>' },
  };

  // Every tip: who says it, a title, a short body, and an optional "tell me more".
  const TIPS = {
    welcome: { who: "economic", title: "Welcome, Leader",
      body: "Aliens have taken much of Earth and a fog covers everything. Six continents fight them together; nobody fights anybody else. The world wins only when the mothership is destroyed <b>and</b> every alien city is free.",
      more: "Your MVP score ranks how much you did for the world: kills, cities freed, aid given, troops sent abroad, recruits and the barrage all count. You can see the standings under Scores." },
    first_moves: { who: "military", title: "Your first moves",
      body: "Click a unit, then a highlighted hex to move it. Your scouts see furthest: send them into the fog to find the cities the aliens hold. The big button at the bottom right always names the next thing that needs you (choose research, unit needs orders...) and takes you there; once nothing is left it says <b>Next turn</b>.",
      more: "Enter does the same as the button; Shift+Enter or Shift-click ends the turn anyway. Space jumps to the next unit that needs orders. F fortifies, S skips. Right-click clears the selection; drag or use the arrow keys to pan, and the mouse wheel to zoom." },
    production: { who: "economic", title: "Building your cities",
      body: "Your engineers have nothing to build. Develop city (or click the town) opens the town view: buildings, walls and land works cost materials up front; then the engineers build them, and more engineers build faster. Production trains units and new engineers.",
      more: "Every number has a breakdown: hover a yield to see where it comes from. A city works the best tiles for its focus; change the focus to favor food, production, science or gold." },
    survivors: { who: "military", title: "Survivors",
      body: "You have no city yet: just your leader and four survivors with makeshift weapons. Scout the land around you: abandoned crates may hold rifles, armor, alien weapons, or more people. You have no home: the first alien-held town you find becomes your first city.",
      more: "Wounded units heal when they rest (fortify). Alien hunters do not chase a band at a distance, and cover (forest, hills) hides you better. Free the town and your survivors become its first citizens; then research and building begin." },
    resistance: { who: "military", title: "A friend inside",
      body: "You have found a town the aliens hold, and it will be your first city. Its people are ready to rise if someone pays for their weapons. You <b>must</b> send them your 100 gold before you can take it: the town's defense falls by half and its gates open.",
      ok: "Fund the resistance", then: () => { const p = S.view.pending.find((x) => x.kind === "fund_resistance"); if (p && window.showFundCard) showFundCard(p.city); },
      more: "Later you can fund the resistance in any alien city you have found (click it on the map). Stronger cities need more gold: perhaps 500 gold for a quarter of their defense." },
    first_city: { who: "economic", title: "Your first town",
      body: "The town is yours, and it is your capital. The three people you rescued and your survivors without gear now live here as citizens. Let's meet them: each citizen can work a tile, sit on the council, or (once you have a barracks) train as a soldier.",
      ok: "Meet your people", then: () => { if (typeof openScreen === "function") openScreen("population"); },
      more: "Survivors carrying gear stay in the field as soldiers. Scrap you salvaged went into the town's production, and a scout has joined you." },
    farm: { who: "economic", title: "Repair the farm",
      body: "The aliens wrecked the town's farm. <b>This is how your citizens will earn food</b>: a farm feeds ten people, and spare food brings new citizens. Your engineers can repair it in one turn, free of materials. It is marked in red.",
      ok: "Repair the farm", then: () => { const p = S.view.pending.find((x) => x.kind === "repair_farm"); if (p) resolvePending(p); },
      more: "You cannot end the turn until the repair is ordered. Later, build more farms on flat land, mines on hills (stone and iron) and lumber camps in forests (timber) from the Land tab." },
    next_builds: { who: "economic", title: "What to build next",
      body: "With the farm under way, two buildings are worth it soon. The <b>radio tower</b> is free to repair and lets you talk to the other continents. A <b>barracks</b> lets your citizens train as soldiers; your first one is cheap and quick.",
      ok: "Open Develop city", then: () => { const t = S.view && Object.values(S.view.cities).find((c) => c.owner === S.view.me && c.is_capital); if (t && window.Builder) Builder.open(t.id, "build"); },
      more: "Neither is required. Click your town any time to open Develop city." },
    barracks_done: { who: "military", title: "Your barracks is ready",
      body: "Your citizens can now <b>train as soldiers</b>. A citizen trains for a few turns (stronger units take longer), then leaves the town as the unit. Pick someone with a good military stat.",
      ok: "Train soldiers", then: () => { const e = (S.view.events || []).find((x) => x.kind === "building_completed" && x.building === "military_base" && x.player === S.view.me); if (typeof openPopulation === "function") openPopulation(e ? e.city : null); },
      more: "Training costs no production: the citizen is the soldier. A town always keeps one citizen at home." },
    research: { who: "science", title: "Research",
      body: "Choose what your scientists work on. The tree starts with two branches, Urban Planning and Advanced Manufacturing, and every tech opens two more. Each card shows how many turns it takes and what it unlocks.",
      more: "Urban Planning leads to International Accords (alliances) and Beacon Theory (recruits); Radio Beacons, Deep Space Radar and Orbital Barrage end the war. Advanced Manufacturing leads to science, industry and the army." },
    lost_cities: { who: "military", title: "Lost cities",
      body: "Twelve of your continent's cities are held by the aliens. Find them in the fog, shell them with artillery and take them with a melee unit: a freed city is yours again, with its farms and some of its people.",
      more: "Freed cities always belong to their continent, but you get the credit. Damage counts for everyone who helped, so shared sieges share the credit." },
    roads: { who: "economic", title: "Roads come first",
      body: "Roads join your cities. Train a road crew in a city and move it onto the gap to build a road.",
      more: "Farms, mines and extractors are built by each city's engineers from Develop city (the Land tab). Strategic resources like oil only count once improved, in a connected city." },
    aliens_seen: { who: "military", title: "The enemy",
      body: "Aliens roam the fog. They raid roads, attack weak cities and land reinforcements from the mothership. Keep a soldier in every city near them.",
      more: "Fortified units, hills and forests all defend better. A unit that neither moves nor attacks heals 20 HP a turn in your territory and 10 outside. Two units of the same type can merge into one stack with double strength." },
    combat: { who: "military", title: "Reading the odds",
      body: "Before you attack, hover the red hex: the preview shows both sides' strength, every modifier, and the damage each side should take. Ranged units take no damage when they fire.",
      more: "Wounded units fight weaker. Flanking (other friendly units next to the target) adds strength. Only melee units can take a city; artillery can soften it first." },
    alien_city: { who: "military", title: "Alien strongholds",
      body: "Alien cities hit hard and harden as the aliens lose ground. Shell them with artillery, then finish them with melee units. A city that took damage this turn does not heal.",
      more: "Freeing a city kills its garrison and returns it to its continent. Damage counts toward everyone who helped, so shared sieges share the credit." },
    citizens: { who: "economic", title: "Your citizens",
      body: "Food brings new citizens. Each is born with 6 points of stats and maybe a trait, and must grow up before working; more spare food means faster births and faster growing up.",
      more: "A grown citizen works one <b>improved</b> tile (farm, mine...), adding half its stats there, or sits on the council and gives its full stats to its city. Bare tiles cannot be worked, so keep your engineers building. Pick each citizen's job in the city panel, or leave it on Auto." },
    city_attack: { who: "military", title: "Enemy at the gates",
      body: "An enemy is within two hexes of one of your cities. Your city can fire on it once a turn: the big button takes you there. Click a red hex to fire, or Hold fire.",
      more: "City guns (artillery) also fire on their own at the end of every turn." },
    explore_sea: { who: "economic", title: "Other continents",
      body: "You do not know where the other continents are: the world is laid out differently every game. Build a <b>scout boat</b> in a coastal city and sail into the fog to find them.",
      more: "Once one of your units sights another continent's land or units you have met: you can trade, form alliances, send aid and ship troops. A continent that falls becomes known to everyone." },
    contact: { who: "economic", title: "First contact",
      body: "You have met another continent. Open Diplomacy any time to propose trades, send aid or, once you both know International Accords, an alliance.",
      more: "You also learn where its cities are, so you can ship troops to help it." },
    beacon: { who: "beacon", title: "Beacons",
      body: "Beacons call aliens from other worlds to your side. Build a Beacon in a city to earn beacon points; when you have enough, a recruit arrives.",
      more: "Two levers: more and bigger Beacon buildings bring recruits faster; beacon-tree research brings rarer, stronger ones, even legends." },
    recruit: { who: "beacon", title: "Your first recruit",
      body: "A recruit has arrived. Seat it on a council in the Council screen: on a domain seat it boosts that domain; on a general seat it boosts everything.",
      more: "Recruits age and some may betray you: a traitor slips away to an alien city, and freeing that city brings it back. You can also gift recruits to other continents." },
    diplomacy: { who: "economic", title: "Deals and aid",
      body: "Another continent has proposed a deal. Open Diplomacy to accept or decline. Trade, gifts and alliances all help the world, and gifts raise your MVP score.",
      more: "Alliances need International Accords on both sides; allies share what they see. Techs and recruits travel by sea from your ports." },
    city_lost: { who: "military", title: "A city has fallen",
      body: "The aliens have taken one of your cities. You can win it back in battle. If a continent loses every city it falls, but others can still rescue it.",
      more: "If your capital falls, your largest city becomes the new capital. A city's garrison and walls are its best defense." },
    mothership: { who: "science", title: "The mothership",
      body: "The mothership strikes cities from orbit and keeps landing reinforcements. Researching <b>Orbital Barrage</b> stops the reinforcements; firing the world barrage destroys the ship.",
      more: "The barrage is a shared project: anyone can send production or gold. It takes at least twenty turns, and the aliens will target its host city." },
    barrage_ready: { who: "science", title: "The world barrage",
      body: "Orbital Barrage is known. Start the barrage in a strong city from the Projects screen, and have cities build the Barrage project to finish it.",
      more: "Once it fires, the mothership is gone: no more strikes or reinforcements. Then free every remaining alien city to win." },
    espionage: { who: "science", title: "Alien espionage",
      body: "An espionage operation has finished. As its largest backer, choose one of the alien technologies on offer in the Projects screen.",
      more: "Alien techs cannot be researched. Shared operations give the tech to every continent; solo ones only to you." },
  };
  const ORDER = Object.keys(TIPS);

  const queue = [];
  let showing = null;

  function key() { return S.view ? `beacon.advice.${S.view.seed}.${S.view.me}` : null; }
  function seen() {
    try { return new Set(JSON.parse(localStorage.getItem(key()) || "[]")); } catch (e) { return new Set(); }
  }
  function markSeen(id) {
    try { const s = seen(); s.add(id); localStorage.setItem(key(), JSON.stringify([...s])); } catch (e) { /* storage off: fine */ }
  }
  function off() { try { return localStorage.getItem("beacon.advice.off") === "1"; } catch (e) { return false; } }
  function setOff(v) { try { localStorage.setItem("beacon.advice.off", v ? "1" : "0"); } catch (e) { /* ignore */ } }

  function trigger(id) {
    if (!S.view || off() || !TIPS[id] || seen().has(id) || queue.includes(id) || showing === id) return;
    queue.push(id);
    queue.sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
    if (!showing) setTimeout(next, 350);
  }

  function portrait(a) {
    return `<svg viewBox="0 0 64 64" class="advisor-emblem"><defs><radialGradient id="ag-${a.name.length}" cx="35%" cy="30%"><stop offset="0" stop-color="${a.color}"/><stop offset="1" stop-color="#0d141b"/></radialGradient></defs>
      <circle cx="32" cy="32" r="30" fill="url(#ag-${a.name.length})" stroke="#d9ae55" stroke-width="2"/>${a.glyph}</svg>`;
  }

  function next() {
    if (showing || !queue.length || !S.inGame) return;
    if (!document.getElementById("modal").classList.contains("hidden")) { setTimeout(next, 800); return; }
    const id = queue.shift();
    const tip = TIPS[id], a = ADVISORS[tip.who];
    showing = id;
    const box = document.getElementById("advisor");
    box.innerHTML = `<div class="advisor-card">
        <div class="advisor-text">
          <h2>${tip.title}</h2>
          <p>${tip.body}</p>
          ${tip.more ? `<p class="advisor-more hidden">${tip.more}</p><button class="link" id="adv-more">Tell me more</button>` : ""}
        </div>
        <div class="advisor-side">${portrait(a)}<div class="advisor-name">${a.name}</div></div>
        <div class="advisor-foot">
          <label><input type="checkbox" id="adv-off"> Don't show advice again</label>
          <button class="primary" id="adv-ok">${tip.ok || "Thank you"}</button>
        </div></div>`;
    box.classList.remove("hidden");
    const more = document.getElementById("adv-more");
    if (more) more.onclick = () => { box.querySelector(".advisor-more").classList.remove("hidden"); more.remove(); };
    document.getElementById("adv-ok").onclick = close;
  }

  function close() {
    if (!showing) return;
    if (document.getElementById("adv-off").checked) { setOff(true); queue.length = 0; }
    markSeen(showing);
    const then = TIPS[showing].then;
    showing = null;
    document.getElementById("advisor").classList.add("hidden");
    if (then) { then(); return; }  // e.g. straight on to the funding offer
    setTimeout(next, 250);
  }

  // Called after every refresh: look at the view and the turn's events for first-time moments.
  function check() {
    const v = S.view;
    if (!v || off()) return;
    if (v.turn <= 1) { trigger("welcome"); trigger("first_moves"); }
    if (v.founded === false) trigger("survivors");
    if ((v.pending || []).some((p) => p.kind === "fund_resistance")) trigger("resistance");
    if (v.events.some((e) => e.kind === "first_city" && e.player === v.me)) trigger("first_city");
    if ((v.pending || []).some((p) => p.kind === "repair_farm")) trigger("farm");
    else if (v.founded && seen().has("farm")) trigger("next_builds");
    if (v.events.some((e) => e.kind === "building_completed" && e.building === "military_base" && e.player === v.me)) trigger("barracks_done");
    if (v.pending.some((p) => p.kind === "choose_research")) trigger("research");
    if (v.pending.some((p) => p.kind === "choose_production") && v.turn >= 1 && !v.pending.some((p) => p.kind === "repair_farm")) trigger("production");
    const known = Object.values(v.cities);
    if (known.some((c) => c.continent === v.me && c.status === "overrun")) trigger("lost_cities");
    if (known.some((c) => c.owner === v.me && c.connected === false)) trigger("roads");
    if (v.units.some((u) => u.owner === "aliens")) trigger("aliens_seen");
    if (known.some((c) => c.status === "overrun" && c.hp_now != null)) trigger("alien_city");
    if (v.economy.rarity >= 1) trigger("beacon");
    if (v.pending.some((p) => p.kind === "deal_received")) trigger("diplomacy");
    if (v.pending.some((p) => p.kind === "choose_espionage_tech")) trigger("espionage");
    if (v.pending.some((p) => p.kind === "city_can_attack")) trigger("city_attack");
    if (v.turn >= 1) trigger("citizens");
    if (v.turn >= 3) trigger("explore_sea");
    for (const e of v.events) {
      if (e.kind === "recruit_arrived") trigger("recruit");
      if (e.kind === "contact_made") trigger("contact");
      if (e.kind === "city_overrun") trigger("city_lost");
      if (e.kind === "mothership_strike" || e.kind === "reinforcements_stopped") trigger("mothership");
    }
    if (v.research && v.research.tech === "orbital_barrage") trigger("mothership");
    if (v.economy && (v.has_barrage_tech || false)) trigger("barrage_ready");
  }

  window.addEventListener("keydown", (e) => {
    if (showing && (e.key === "Enter" || e.key === "Escape")) { e.stopImmediatePropagation(); e.preventDefault(); close(); }
  }, true);

  window.Advisors = {
    check, trigger,
    reset() { try { localStorage.removeItem(key()); setOff(false); } catch (e) { /* ignore */ } },
    isOff: off, setOff,
  };
})();
