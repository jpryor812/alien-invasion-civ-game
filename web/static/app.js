// Beacon web client (docs/SPEC_M8.md). Plain JavaScript, no build step.
// The server owns the game; this file draws the fog-safe view and sends commands.
"use strict";

// =============================================================================================
// palette, helpers

const OWNER = {
  north_america: "#3b78e0", south_america: "#38b072", europe: "#e0b03a", asia: "#c463c9",
  africa: "#e0843a", oceania: "#36bfcc", aliens: "#e0362c",
};
const GROUND = {
  grassland: ["#6b9c48", "#628f42", "#73a34e"], plains: ["#b3a55b", "#a99b51", "#bbac63"],
  desert: ["#dcc489", "#d4bb7d", "#e2cb92"], tundra: ["#8d9b88", "#849280", "#95a28f"],
  snow: ["#e8eef1", "#dfe7eb", "#eef3f5"], coast: ["#3f88b0", "#3c83aa", "#4390b6"],
  ocean: ["#24547f", "#225079", "#275985"],
};
const MINI = { grassland: "#6b9c48", plains: "#b3a55b", desert: "#dcc489", tundra: "#8d9b88", snow: "#e8eef1", coast: "#3f88b0", ocean: "#24547f" };
const FOG_THICK = "#aab4bd";    // unexplored: thick clouds
const FOG_MIST = "#8794a0";     // explored, not seen now: thin mist
const YIELD_KEYS = ["food", "production", "science", "gold", "beacon"];

const $ = (id) => document.getElementById(id);
const pretty = (id) => String(id).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const code = (type) => {
  const special = { infantry: "INF", artillery: "ART", recon_team: "RCN", engineers: "ENG", restoration_team: "RST",
    tank: "TNK", mech_infantry: "MEC", trade_convoy: "CVY", destroyer: "DD", scout_boat: "BOT", city_artillery: "GUN", home_guard: "GRD" };
  if (special[type]) return special[type];
  const words = type.replace(/^alien_/, "").split("_");
  return (words.length > 1 ? words.map((w) => w[0]).join("") : words[0].slice(0, 3)).toUpperCase().slice(0, 3);
};
// small inline SVG icons for the UI chrome
const ICON = {
  gold: '<svg class="icon" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" fill="#f2d15c" stroke="#8a6d1c"/><text x="8" y="11.5" font-size="9" text-anchor="middle" fill="#6b5212" font-weight="700">$</text></svg>',
  science: '<svg class="icon" viewBox="0 0 16 16"><path d="M6 1h4v1H9.5v4l4 7.5c.3.7-.1 1.5-.9 1.5H3.4c-.8 0-1.2-.8-.9-1.5l4-7.5V2H6z" fill="#6cbbec" stroke="#1d4a66" stroke-width=".8"/></svg>',
  beacon: '<svg class="icon" viewBox="0 0 16 16"><circle cx="8" cy="10" r="2" fill="#c88df2"/><path d="M4 6a5.5 5.5 0 0 1 8 0M2 3.5a9 9 0 0 1 12 0" fill="none" stroke="#c88df2" stroke-width="1.4"/></svg>',
  turn: '<svg class="icon" viewBox="0 0 16 16"><path d="M4 1.5h8M4 14.5h8M5 2c0 4 6 4 6 6s-6 2-6 6M11 2c0 4-6 4-6 6s6 2 6 6" fill="none" stroke="#d9ae55" stroke-width="1.3"/></svg>',
  ship: '<svg class="icon" viewBox="0 0 16 16"><path d="M8 1l3 6H5zM2 10h12l-2 4H4z" fill="#a347c9"/></svg>',
};

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
  return data;
}
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 3500);
}
function splash(text) {
  const el = $("splash");
  el.textContent = text;
  el.classList.remove("hidden");
  el.style.animation = "none"; void el.offsetWidth; el.style.animation = "";
  clearTimeout(splash.timer);
  splash.timer = setTimeout(() => el.classList.add("hidden"), 1700);
}
// deterministic per-tile randomness, so terrain looks the same every frame
function rng(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const hash = (i, salt = 0) => rng(i * 9973 + salt * 7919 + 13)();
function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  let r = n >> 16, g = (n >> 8) & 255, b = n & 255;
  if (f >= 0) { r += (255 - r) * f; g += (255 - g) * f; b += (255 - b) * f; } else { r *= 1 + f; g *= 1 + f; b *= 1 + f; }
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}

// =============================================================================================
// state

const S = {
  view: null, explored: new Set(), tilesByIndex: new Map(), unitsByTile: new Map(), citiesByTile: new Map(),
  myCityInfo: new Map(), selected: null, options: null, city: null, targetMode: null,
  cam: { x: 0, y: 0, zoom: 1.6 }, hover: null, busy: false, dirty: true, inGame: false,
};
const R0 = 22;
const SQ3 = Math.sqrt(3);

// =============================================================================================
// hex geometry (pointy-top, odd rows shifted right)

function colRow(i) { return [i % S.view.width, Math.floor(i / S.view.width)]; }
function center(i) {
  const [c, r] = colRow(i);
  return [c * SQ3 * R0 + (r & 1) * SQ3 * R0 / 2 + SQ3 * R0 / 2, r * 1.5 * R0 + R0];
}
function toScreen(wx, wy) { return [(wx - S.cam.x) * S.cam.zoom, (wy - S.cam.y) * S.cam.zoom]; }
function toWorld(sx, sy) { return [sx / S.cam.zoom + S.cam.x, sy / S.cam.zoom + S.cam.y]; }
function pick(sx, sy) {
  const [wx, wy] = toWorld(sx, sy);
  const x = wx - SQ3 * R0 / 2, y = wy - R0;
  const q = (SQ3 / 3 * x - y / 3) / R0, r = (2 / 3 * y) / R0, s = -q - r;
  let rq = Math.round(q), rr = Math.round(r); const rs = Math.round(s);
  const dq = Math.abs(rq - q), dr = Math.abs(rr - r), ds = Math.abs(rs - s);
  if (dq > dr && dq > ds) rq = -rr - rs; else if (dr > ds) rr = -rq - rs;
  const col = rq + (rr - (rr & 1)) / 2, row = rr;
  if (col < 0 || row < 0 || col >= S.view.width || row >= S.view.height) return null;
  return row * S.view.width + col;
}
// neighbours with the index of the shared edge (corner k to corner k+1, corners at 60k-30 degrees)
const DIRS_EVEN = [[1, 0, 0], [0, -1, 5], [-1, -1, 4], [-1, 0, 3], [-1, 1, 2], [0, 1, 1]];
const DIRS_ODD = [[1, 0, 0], [1, -1, 5], [0, -1, 4], [-1, 0, 3], [0, 1, 2], [1, 1, 1]];
function neighbourEdges(i) {
  const [c, r] = colRow(i);
  const out = [];
  for (const [dc, dr, edge] of (r & 1 ? DIRS_ODD : DIRS_EVEN)) {
    const cc = c + dc, rr = r + dr;
    if (cc >= 0 && rr >= 0 && cc < S.view.width && rr < S.view.height) out.push([rr * S.view.width + cc, edge]);
  }
  return out;
}
function corner(cx, cy, r, k) { const a = Math.PI / 180 * (60 * k - 30); return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
function hexPath(g, cx, cy, r) {
  g.beginPath();
  for (let k = 0; k < 6; k++) { const [x, y] = corner(cx, cy, r, k); if (k === 0) g.moveTo(x, y); else g.lineTo(x, y); }
  g.closePath();
}

// =============================================================================================
// terrain sprites: painted once per (terrain, elevation, feature, variant, size) and reused

const SPRITES = new Map();
function tileSprite(t, i, R) {
  const variant = Math.floor(hash(i) * 3);
  const key = `${t.terrain}|${t.elevation}|${t.feature || ""}|${variant}|${R}`;
  let sp = SPRITES.get(key);
  if (sp) return sp;
  if (SPRITES.size > 2500) SPRITES.clear();
  const w = Math.ceil(SQ3 * R) + 4, h = 2 * R + 4;
  sp = document.createElement("canvas");
  sp.width = w; sp.height = h;
  const g = sp.getContext("2d");
  paintTile(g, t, w / 2, h / 2, R, variant);
  SPRITES.set(key, sp);
  return sp;
}

function paintTile(g, t, cx, cy, R, variant) {
  const rnd = rng(variant * 101 + t.terrain.length * 7 + (t.feature || "").length * 13 + (t.elevation === "hills" ? 5 : 0));
  const base = GROUND[t.terrain][variant] || "#777";
  g.save();
  hexPath(g, cx, cy, R + 0.8);
  g.clip();
  const grad = g.createLinearGradient(0, cy - R, 0, cy + R);
  grad.addColorStop(0, shade(base, 0.1));
  grad.addColorStop(1, shade(base, -0.12));
  g.fillStyle = grad;
  g.fillRect(cx - R * 1.2, cy - R * 1.2, R * 2.4, R * 2.4);
  for (let k = 0; k < 26; k++) {
    g.fillStyle = rnd() < 0.5 ? "rgba(0,0,0,0.07)" : "rgba(255,255,255,0.07)";
    g.beginPath(); g.arc(cx + (rnd() - 0.5) * 1.8 * R, cy + (rnd() - 0.5) * 1.8 * R, R * (0.03 + rnd() * 0.06), 0, Math.PI * 2); g.fill();
  }
  const T = t.terrain;
  if (T === "grassland" || T === "plains") {
    g.strokeStyle = T === "grassland" ? "rgba(40,80,25,0.45)" : "rgba(120,100,40,0.45)"; g.lineWidth = Math.max(1, R * 0.04);
    for (let k = 0; k < 9; k++) {
      const x = cx + (rnd() - 0.5) * 1.5 * R, y = cy + (rnd() - 0.5) * 1.4 * R;
      g.beginPath(); g.moveTo(x - R * 0.05, y - R * 0.07); g.lineTo(x, y); g.lineTo(x + R * 0.05, y - R * 0.08); g.stroke();
    }
    if (T === "plains") {
      g.strokeStyle = "rgba(255,240,170,0.25)"; g.lineWidth = Math.max(1, R * 0.07);
      for (const dy of [-0.35, 0, 0.35]) { g.beginPath(); g.moveTo(cx - R, cy + dy * R + R * 0.1); g.lineTo(cx + R, cy + dy * R - R * 0.1); g.stroke(); }
    }
  } else if (T === "desert") {
    for (const [dx, dy] of [[-0.3, -0.25], [0.25, 0.1], [-0.15, 0.45]]) {
      g.strokeStyle = "rgba(255,245,210,0.6)"; g.lineWidth = Math.max(1, R * 0.06);
      g.beginPath(); g.arc(cx + dx * R, cy + dy * R + R * 0.35, R * 0.4, Math.PI * 1.2, Math.PI * 1.8); g.stroke();
      g.strokeStyle = "rgba(150,110,50,0.35)";
      g.beginPath(); g.arc(cx + dx * R, cy + dy * R + R * 0.42, R * 0.4, Math.PI * 1.25, Math.PI * 1.75); g.stroke();
    }
  } else if (T === "tundra") {
    for (let k = 0; k < 5; k++) {
      g.fillStyle = rnd() < 0.5 ? "rgba(70,80,70,0.25)" : "rgba(220,225,215,0.3)";
      g.beginPath(); g.ellipse(cx + (rnd() - 0.5) * 1.4 * R, cy + (rnd() - 0.5) * 1.3 * R, R * 0.22, R * 0.1, 0, 0, Math.PI * 2); g.fill();
    }
  } else if (T === "snow") {
    g.strokeStyle = "rgba(150,175,195,0.45)"; g.lineWidth = Math.max(1, R * 0.05);
    for (const dy of [-0.3, 0.15, 0.5]) { g.beginPath(); g.arc(cx + (rnd() - 0.5) * R, cy + dy * R + R * 0.3, R * 0.35, Math.PI * 1.2, Math.PI * 1.8); g.stroke(); }
  } else if (T === "coast" || T === "ocean") {
    const rg = g.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 1.1);
    rg.addColorStop(0, T === "coast" ? "rgba(140,210,230,0.25)" : "rgba(60,110,160,0.18)");
    rg.addColorStop(1, "rgba(0,20,40,0.15)");
    g.fillStyle = rg; g.fillRect(cx - R * 1.2, cy - R * 1.2, R * 2.4, R * 2.4);
    g.strokeStyle = T === "coast" ? "rgba(255,255,255,0.28)" : "rgba(190,220,255,0.14)"; g.lineWidth = Math.max(1, R * 0.045);
    for (let k = 0; k < 3; k++) {
      const x = cx + (rnd() - 0.5) * 1.2 * R, y = cy + (rnd() - 0.5) * 1.2 * R;
      g.beginPath(); g.moveTo(x - R * 0.2, y); g.quadraticCurveTo(x - R * 0.1, y - R * 0.08, x, y); g.quadraticCurveTo(x + R * 0.1, y + R * 0.08, x + R * 0.2, y); g.stroke();
    }
  }
  if (t.feature === "marsh") {
    for (let k = 0; k < 4; k++) {
      const x = cx + (rnd() - 0.5) * 1.2 * R, y = cy + (rnd() - 0.5) * 1.1 * R;
      g.fillStyle = "rgba(60,110,130,0.55)"; g.beginPath(); g.ellipse(x, y, R * 0.2, R * 0.08, 0, 0, Math.PI * 2); g.fill();
      g.strokeStyle = "rgba(40,70,30,0.8)"; g.lineWidth = Math.max(1, R * 0.03);
      for (const d of [-0.08, 0, 0.08]) { g.beginPath(); g.moveTo(x + d * R, y - R * 0.02); g.lineTo(x + d * R * 1.4, y - R * 0.22); g.stroke(); }
    }
  }
  if (t.elevation === "hills") {
    for (const [dx, dy, s] of [[-0.35, 0.18, 1], [0.3, 0.3, 0.85], [0.05, -0.2, 0.7]]) {
      const x = cx + dx * R, y = cy + dy * R, w = R * 0.42 * s, h = R * 0.32 * s;
      const hg = g.createLinearGradient(x - w, y - h, x + w, y);
      hg.addColorStop(0, "rgba(255,240,200,0.35)"); hg.addColorStop(1, "rgba(60,40,20,0.35)");
      g.fillStyle = hg; g.beginPath(); g.ellipse(x, y, w, h, 0, Math.PI, 0); g.fill();
      g.strokeStyle = "rgba(60,40,20,0.35)"; g.lineWidth = Math.max(1, R * 0.03); g.stroke();
    }
  }
  if (t.feature === "forest") drawTrees(g, cx, cy, R, rnd, "forest");
  if (t.feature === "jungle") drawTrees(g, cx, cy, R, rnd, "jungle");
  if (t.elevation === "mountain") {
    for (const [dx, h, w] of [[-0.25, 0.85, 0.5], [0.3, 0.6, 0.38]]) {
      const bx = cx + dx * R, by = cy + R * 0.5, px = bx + R * 0.05, py = by - h * R;
      g.fillStyle = "#857e74"; g.beginPath(); g.moveTo(bx - w * R, by); g.lineTo(px, py); g.lineTo(px, by); g.fill();
      g.fillStyle = "#5f5951"; g.beginPath(); g.moveTo(px, py); g.lineTo(bx + w * R, by); g.lineTo(px, by); g.fill();
      g.fillStyle = "#f2f5f7"; g.beginPath(); g.moveTo(px - w * R * 0.32, py + h * R * 0.32); g.lineTo(px, py); g.lineTo(px + w * R * 0.3, py + h * R * 0.3); g.lineTo(px + w * R * 0.05, py + h * R * 0.22); g.fill();
    }
  }
  g.restore();
  hexPath(g, cx, cy, R - 0.5);
  g.strokeStyle = "rgba(0,0,0,0.16)"; g.lineWidth = 1; g.stroke();
}

function drawTrees(g, cx, cy, R, rnd, kind) {
  const pts = [];
  for (let k = 0; k < 6; k++) pts.push([cx + (rnd() - 0.5) * 1.3 * R, cy + (rnd() - 0.5) * 1.15 * R]);
  pts.sort((a, b) => a[1] - b[1]);
  for (const [x, y] of pts) {
    if (kind === "forest") {
      g.fillStyle = "#4a3320"; g.fillRect(x - R * 0.025, y, R * 0.05, R * 0.1);
      for (const [dy, w] of [[0, 0.17], [-0.12, 0.13], [-0.22, 0.09]]) {
        g.fillStyle = "#2d5a2a"; g.beginPath(); g.moveTo(x, y + dy * R - R * 0.16); g.lineTo(x - w * R, y + dy * R + R * 0.03); g.lineTo(x + w * R, y + dy * R + R * 0.03); g.fill();
        g.fillStyle = "#3f7536"; g.beginPath(); g.moveTo(x, y + dy * R - R * 0.16); g.lineTo(x - w * R, y + dy * R + R * 0.03); g.lineTo(x, y + dy * R + R * 0.03); g.fill();
      }
    } else {
      g.fillStyle = "#4a3320"; g.fillRect(x - R * 0.02, y, R * 0.04, R * 0.12);
      g.fillStyle = "#1f5a2c"; g.beginPath(); g.arc(x, y - R * 0.02, R * 0.16, 0, Math.PI * 2); g.fill();
      g.fillStyle = "#2f7a38"; g.beginPath(); g.arc(x - R * 0.05, y - R * 0.07, R * 0.1, 0, Math.PI * 2); g.fill();
    }
  }
}

// =============================================================================================
// fog: drifting clouds instead of black

let PUFFS = null;
function makePuff(seed, tint, peak) {
  const c = document.createElement("canvas");
  c.width = c.height = 160;
  const g = c.getContext("2d");
  const rnd = rng(seed);
  // many soft overlapping blobs give an irregular cloud rather than a disc
  for (let k = 0; k < 11; k++) {
    const x = 80 + (rnd() - 0.5) * 80, y = 80 + (rnd() - 0.5) * 50, r = 18 + rnd() * 30;
    const rg = g.createRadialGradient(x, y, 0, x, y, r);
    rg.addColorStop(0, `rgba(${tint},${peak})`);
    rg.addColorStop(0.55, `rgba(${tint},${peak * 0.45})`);
    rg.addColorStop(1, `rgba(${tint},0)`);
    g.fillStyle = rg; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  }
  return c;
}
function puffSprites() {
  if (!PUFFS) {
    PUFFS = {
      light: [makePuff(42, "255,255,255", 0.5), makePuff(77, "246,248,251", 0.5), makePuff(131, "238,242,247", 0.5)],
      shadow: [makePuff(203, "88,102,118", 0.42), makePuff(257, "98,112,128", 0.42)],
    };
  }
  return PUFFS;
}
function puffSprite() { return puffSprites().light[0]; }

function drawFog(visible, R, t) {
  const P = puffSprites();
  // a flat base first, so the fog reads as one continuous bank
  for (const [i, sx, sy, shown] of visible) {
    if (shown) continue;
    hexPath(ctx, sx, sy, R + 1);
    ctx.fillStyle = S.explored.has(i) ? FOG_MIST : FOG_THICK;
    ctx.fill();
  }
  // slow cloud shadows give the bank depth
  for (const [i, sx, sy, shown] of visible) {
    if (shown || S.explored.has(i) || hash(i, 5) > 0.22) continue;
    const drift = t * 0.00025;
    const size = R * (3.6 + hash(i, 6) * 1.5);
    ctx.globalAlpha = 0.55;
    ctx.drawImage(P.shadow[i % 2], sx - size / 2 + Math.sin(drift + hash(i, 7) * 6.28) * R * 0.5, sy - size / 2, size, size);
  }
  // then varied, drifting puffs that spill over the edges of the seen world
  for (const [i, sx, sy, shown] of visible) {
    if (shown) continue;
    const thick = !S.explored.has(i);
    for (let layer = 0; layer < (thick ? 2 : 1); layer++) {
      const h1 = hash(i, 1 + layer * 3), h2 = hash(i, 2 + layer * 3);
      const drift = t * 0.0003 * (0.6 + h1);
      const ox = Math.sin(drift + h2 * 6.28) * R * 0.45 + (layer ? R * 0.35 : 0);
      const oy = Math.cos(drift * 0.7 + h1 * 6.28) * R * 0.25 - (layer ? R * 0.2 : 0);
      const size = R * (thick ? 3.1 : 2.5) * (0.75 + h2 * 0.6);
      ctx.globalAlpha = thick ? 0.7 : 0.4;
      const sprite = P.light[Math.floor(h1 * 3)];
      ctx.save();
      ctx.translate(sx + ox, sy + oy);
      ctx.rotate((h2 - 0.5) * 1.2);
      ctx.drawImage(sprite, -size / 2, -size / 2 * 0.8, size, size * 0.8);
      ctx.restore();
    }
  }
  ctx.globalAlpha = 1;
}

// =============================================================================================
// loading the view

async function refresh(keepSelection = true) {
  const v = await api("/api/view");
  const newTurn = S.view && v.turn !== S.view.turn;
  // keep a log of past turns' events in this browser session (the server sends the latest)
  S.history = S.history || [];
  if (newTurn || !S.history.length) S.history.push({ turn: v.turn, events: v.events });
  else S.history[S.history.length - 1].events = v.events;
  if (S.history.length > 40) S.history.shift();
  S.view = v;
  S.explored = new Set(v.explored);
  S.tilesByIndex = new Map(Object.entries(v.tiles).map(([k, t]) => [Number(k), t]));
  S.unitsByTile = new Map();
  S.defencesByTile = new Map();  // city defences are part of their city: not drawn or selected
  for (const u of v.units) {
    if (v.unit_types[u.type]?.fixed) {
      if (!S.defencesByTile.has(u.tile)) S.defencesByTile.set(u.tile, []);
      S.defencesByTile.get(u.tile).push(u);
      continue;
    }
    if (!S.unitsByTile.has(u.tile)) S.unitsByTile.set(u.tile, []);
    S.unitsByTile.get(u.tile).push(u);
  }
  S.citiesByTile = new Map();
  for (const [id, c] of Object.entries(v.cities)) S.citiesByTile.set(c.tile, { ...c, id: Number(id) });
  S.myCityInfo = new Map(v.my_cities.map((c) => [c.id, c]));
  if (keepSelection && S.selected) await reselect(); else clearSelection();
  renderChrome();
  if (newTurn) splash(`Turn ${v.turn} · ${v.year}`);
  S.dirty = true;
  if (window.Advisors) Advisors.check();
}
async function reselect() {
  const sel = S.selected;
  if (sel.kind === "unit" && S.view.units.find((u) => u.id === sel.id && u.owner === S.view.me)) return selectUnit(sel.id, false);
  if (sel.kind === "city" && S.view.cities[sel.id] && S.view.cities[sel.id].owner === S.view.me) return selectCity(sel.id, false);
  clearSelection();
}

// =============================================================================================
// drawing the map

const canvas = $("map");
const ctx = canvas.getContext("2d");
function resize() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  S.dirty = true;
}

let lastFrame = 0;
function frame(t) {
  requestAnimationFrame(frame);
  if (!S.inGame || !S.view) return;
  if (!S.dirty && t - lastFrame < 50) return;  // clouds drift at ~20 fps
  lastFrame = t; S.dirty = false;
  draw(t);
}

function draw(t = performance.now()) {
  const W = canvas.clientWidth, H = canvas.clientHeight;
  ctx.fillStyle = FOG_THICK; ctx.fillRect(0, 0, W, H);
  const z = S.cam.zoom, R = R0 * z, Ri = Math.max(4, Math.round(R));
  const reach = new Set(S.options ? [...S.options.reachable, ...mergeTiles()] : []);
  const attackable = new Set((S.options ? S.options.attacks : []).map((a) => a.tile));
  const bombard = new Set(S.targetMode === "bombard" && S.city ? S.city.bombard : []);
  // a selected city shows its improved tiles: worked (green, with yields) or free (gold, click to staff)
  const cityTiles = new Map(S.selected && S.selected.kind === "city" && S.city ? S.city.workable.map((w) => [w.tile, w]) : []);
  const visible = [];
  const total = S.view.width * S.view.height;
  for (let i = 0; i < total; i++) {
    const [sx, sy] = toScreen(...center(i));
    if (sx < -R * 3 || sy < -R * 3 || sx > W + R * 3 || sy > H + R * 3) continue;
    visible.push([i, sx, sy, S.tilesByIndex.has(i)]);
  }
  // 1. terrain
  for (const [i, sx, sy, shown] of visible) {
    if (!shown) continue;
    const sp = tileSprite(S.tilesByIndex.get(i), i, Ri);
    ctx.drawImage(sp, sx - sp.width / 2, sy - sp.height / 2);
  }
  // 2. coastlines: sand on the land side, foam on the water side
  for (const [i, sx, sy, shown] of visible) {
    if (!shown) continue;
    const t1 = S.tilesByIndex.get(i), water1 = t1.terrain === "coast" || t1.terrain === "ocean";
    for (const [n, edge] of neighbourEdges(i)) {
      const t2 = S.tilesByIndex.get(n);
      if (!t2) continue;
      const water2 = t2.terrain === "coast" || t2.terrain === "ocean";
      if (water1 === water2) continue;
      const k = water1 ? 0.93 : 0.95;
      const [x1, y1] = corner(sx, sy, R * k, edge), [x2, y2] = corner(sx, sy, R * k, (edge + 1) % 6);
      ctx.strokeStyle = water1 ? "rgba(235,248,255,0.55)" : "rgba(232,214,160,0.9)";
      ctx.lineWidth = Math.max(1.2, R * (water1 ? 0.07 : 0.1));
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
  }
  // 3. routes
  for (const [i, sx, sy, shown] of visible) {
    if (!shown) continue;
    const t1 = S.tilesByIndex.get(i);
    if (!(t1.route || S.citiesByTile.has(i))) continue;
    for (const [n] of neighbourEdges(i)) {
      if (n < i) continue;
      const t2 = S.tilesByIndex.get(n);
      if (!t2 || !(t2.route || S.citiesByTile.has(n))) continue;
      const [nx, ny] = toScreen(...center(n));
      const rail = t1.route === "railway" && t2.route === "railway";
      if (rail) {
        ctx.strokeStyle = "#3a3633"; ctx.lineWidth = Math.max(2, 3.2 * z);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(nx, ny); ctx.stroke();
        ctx.strokeStyle = "#8a8580"; ctx.lineWidth = Math.max(1, 1 * z); ctx.setLineDash([2 * z, 3 * z]);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(nx, ny); ctx.stroke(); ctx.setLineDash([]);
      } else {
        ctx.strokeStyle = "#5a4027"; ctx.lineWidth = Math.max(2, 3 * z);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(nx, ny); ctx.stroke();
        ctx.strokeStyle = "#a07a4c"; ctx.lineWidth = Math.max(1, 1.4 * z);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(nx, ny); ctx.stroke();
      }
    }
  }
  // 4. improvements and resources
  for (const [i, sx, sy, shown] of visible) {
    if (!shown) continue;
    const t1 = S.tilesByIndex.get(i);
    if (t1.improvement && z > 0.3) { drawImprovedHex(i, t1.improvement, sx, sy, R); drawImprovement(t1.improvement, sx, sy, R); }
    if (t1.turret && z > 0.3) drawTurret(t1, sx, sy, R);
    if (t1.resource && t1.visible && z > 0.6) drawResource(t1.resource, sx, sy, R);
  }
  // 5. fog, and a light veil over remembered city hexes not seen right now
  drawFog(visible, R, t);
  for (const [i, sx, sy, shown] of visible) {
    if (shown && !S.tilesByIndex.get(i).visible) { hexPath(ctx, sx, sy, R + 0.6); ctx.fillStyle = "rgba(92,105,118,0.45)"; ctx.fill(); }
  }
  // 6. move and attack highlights
  for (const [i, sx, sy] of visible) {
    if (reach.has(i)) { hexPath(ctx, sx, sy, R - 1.5); ctx.fillStyle = "rgba(255,255,255,0.16)"; ctx.fill(); ctx.strokeStyle = "rgba(255,255,255,0.45)"; ctx.lineWidth = 1; ctx.stroke(); }
    if (attackable.has(i) || bombard.has(i)) { hexPath(ctx, sx, sy, R - 1.5); ctx.fillStyle = "rgba(220,60,50,0.28)"; ctx.fill(); ctx.strokeStyle = "#ff6b5a"; ctx.lineWidth = 2.2; ctx.stroke(); }
    if (cityTiles.has(i)) drawCityTile(cityTiles.get(i), i, sx, sy, R);
    if (S.flash && S.flash.tile === i && performance.now() < S.flash.until) {
      hexPath(ctx, sx, sy, R - 1); ctx.strokeStyle = `rgba(242,211,138,${0.5 + 0.5 * Math.sin(performance.now() / 120)})`; ctx.lineWidth = 4; ctx.stroke(); S.dirty = true;
    }
    if (S.hover === i) { hexPath(ctx, sx, sy, R - 1); ctx.strokeStyle = "rgba(255,244,214,0.85)"; ctx.lineWidth = 1.6; ctx.stroke(); }
  }
  // 7. cities, units, then banners on top
  for (const [i, sx, sy] of visible) { const c = S.citiesByTile.get(i); if (c) drawCity(c, sx, sy, R, i); }
  for (const [i, sx, sy] of visible) { const us = S.unitsByTile.get(i); if (us) drawUnits(us, sx, sy, R); }
  for (const [i, sx, sy] of visible) { const c = S.citiesByTile.get(i); if (c) drawBanner(c, sx, sy, R); }
  // 8. selection pulse
  if (S.selected && S.selected.kind === "unit") {
    const u = S.view.units.find((x) => x.id === S.selected.id);
    if (u) {
      const [sx, sy] = toScreen(...center(u.tile));
      const p = 0.5 + 0.5 * Math.sin(t / 220);
      hexPath(ctx, sx, sy, R - 1); ctx.strokeStyle = `rgba(255,215,106,${0.55 + 0.45 * p})`; ctx.lineWidth = 2.5 + p * 1.5; ctx.stroke();
    }
  }
  drawMinimap();
}

// Improved tiles stand out: a tinted hex with a bright inner rim, and a small figure when one of
// your citizens works it.
const IMP_TINT = { farm: "230,200,80", mine: "170,120,70", extractor: "90,90,90", hydroponic_plot: "120,210,140",
  solar_array: "90,170,230", wind_turbines: "200,220,240" };
function drawImprovedHex(i, kind, sx, sy, R) {
  const tint = IMP_TINT[kind] || "120,180,200";
  hexPath(ctx, sx, sy, R * 0.86);
  ctx.fillStyle = `rgba(${tint},0.18)`; ctx.fill();
  ctx.strokeStyle = `rgba(${tint},0.85)`; ctx.lineWidth = Math.max(1.5, R * 0.06); ctx.setLineDash([R * 0.18, R * 0.1]); ctx.stroke(); ctx.setLineDash([]);
  const w = S.view.worked && S.view.worked[i];
  if (w && S.cam.zoom > 0.5) {
    const x = sx - R * 0.42, y = sy - R * 0.42, r = R * 0.12;
    ctx.fillStyle = "#f2d38a"; ctx.beginPath(); ctx.arc(x, y - r * 0.9, r * 0.55, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.moveTo(x - r, y + r); ctx.quadraticCurveTo(x, y - r * 0.6, x + r, y + r); ctx.fill();
  }
}
function drawImprovement(kind, sx, sy, R) {
  if (kind === "farm") {
    ctx.fillStyle = "rgba(230,205,95,0.85)";
    for (let k = 0; k < 3; k++) ctx.fillRect(sx - 0.45 * R, sy + (0.1 + k * 0.14) * R, 0.55 * R, 0.07 * R);
    return;
  }
  ctx.save(); ctx.translate(sx + 0.3 * R, sy - 0.42 * R);
  const s = R * 0.13;
  if (kind === "mine") { ctx.fillStyle = "#2c241c"; ctx.beginPath(); ctx.moveTo(-s * 1.3, s); ctx.lineTo(0, -s * 1.1); ctx.lineTo(s * 1.3, s); ctx.fill(); ctx.fillStyle = "#c9a35c"; ctx.fillRect(-s * 0.3, -s * 0.1, s * 0.6, s * 0.9); }
  else if (kind === "extractor") { ctx.strokeStyle = "#1b1b1b"; ctx.lineWidth = Math.max(1, s * 0.4); ctx.beginPath(); ctx.moveTo(-s, s); ctx.lineTo(0, -s * 1.4); ctx.lineTo(s, s); ctx.moveTo(-s * 0.5, 0); ctx.lineTo(s * 0.5, 0); ctx.stroke(); }
  else if (kind === "radio_beacon" || kind === "sensor_mast") { ctx.strokeStyle = "#c88df2"; ctx.lineWidth = Math.max(1, s * 0.35); ctx.beginPath(); ctx.moveTo(0, s); ctx.lineTo(0, -s); ctx.stroke(); ctx.beginPath(); ctx.arc(0, -s, s, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke(); }
  else if (kind === "military_base") { ctx.fillStyle = "#7a2d24"; ctx.fillRect(-s, -s * 0.6, s * 2, s * 1.4); ctx.fillStyle = "#e9d8a6"; ctx.fillRect(-s * 0.2, -s * 1.4, s * 0.15, s * 0.8); ctx.fillStyle = "#c0392b"; ctx.fillRect(-s * 0.05, -s * 1.4, s * 0.7, s * 0.4); }
  else { ctx.fillStyle = "#3a5a7a"; ctx.fillRect(-s, -s * 0.5, s * 2, s); }
  ctx.restore();
}
function drawResource(res, sx, sy, R) {
  const x = sx - 0.45 * R, y = sy - 0.38 * R, r = 0.17 * R;
  const strategic = ["oil", "aluminum", "uranium", "rare_earths"].includes(res);
  ctx.fillStyle = strategic ? "rgba(30,20,40,0.85)" : "rgba(20,30,15,0.8)";
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = strategic ? "#c88df2" : "#e8d47a"; ctx.lineWidth = 1.2; ctx.stroke();
  ctx.fillStyle = "#fff4d6"; ctx.font = `700 ${Math.round(r * 1.1)}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(res[0].toUpperCase(), x, y + 0.5);
}

function drawCity(c, sx, sy, R, i) {
  const owner = c.owner ? OWNER[c.owner] : "#888";
  const rnd = rng(i * 31 + 7);
  if (c.status === "overrun") {
    const rg = ctx.createRadialGradient(sx, sy, R * 0.1, sx, sy, R * 0.85);
    rg.addColorStop(0, "rgba(220,50,40,0.6)"); rg.addColorStop(1, "rgba(90,15,10,0)");
    ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(sx, sy, R * 0.85, 0, Math.PI * 2); ctx.fill();
    const n = 3 + Math.min(5, Math.floor(c.pop / 2));
    for (let k = 0; k < n; k++) {
      const a = (k / n) * Math.PI * 2 + rnd(), d = k === 0 ? 0 : R * (0.25 + rnd() * 0.25);
      const x = sx + Math.cos(a) * d, y = sy + Math.sin(a) * d * 0.7 + R * 0.15, h = R * (0.35 + rnd() * 0.3);
      ctx.fillStyle = "#5e1612"; ctx.beginPath(); ctx.moveTo(x - R * 0.1, y); ctx.quadraticCurveTo(x - R * 0.12, y - h * 0.6, x, y - h); ctx.quadraticCurveTo(x + R * 0.1, y - h * 0.5, x + R * 0.1, y); ctx.fill();
      ctx.fillStyle = "#e0453a"; ctx.beginPath(); ctx.moveTo(x - R * 0.04, y); ctx.quadraticCurveTo(x - R * 0.06, y - h * 0.6, x, y - h); ctx.lineTo(x, y); ctx.fill();
      ctx.fillStyle = "#ffd27a"; ctx.beginPath(); ctx.arc(x, y - h * 0.55, R * 0.025, 0, Math.PI * 2); ctx.fill();
    }
    return;
  }
  if (c.status === "empty") {
    ctx.fillStyle = "rgba(60,55,50,0.5)"; ctx.beginPath(); ctx.ellipse(sx, sy + R * 0.12, R * 0.6, R * 0.38, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#6e675f";
    for (let k = 0; k < 5; k++) { const x = sx + (rnd() - 0.5) * R, y = sy + (rnd() - 0.4) * R * 0.6; ctx.fillRect(x, y, R * (0.08 + rnd() * 0.12), R * (0.05 + rnd() * 0.15)); }
    return;
  }
  const dormant = c.status === "dormant";
  ctx.fillStyle = dormant ? "rgba(90,85,78,0.55)" : "rgba(150,135,110,0.6)";
  ctx.beginPath(); ctx.ellipse(sx, sy + R * 0.1, R * 0.68, R * 0.45, 0, 0, Math.PI * 2); ctx.fill();
  const n = 4 + Math.min(7, Math.floor(c.pop / 2));
  const spots = [];
  for (let k = 0; k < n; k++) {
    const a = (k / n) * Math.PI * 2 + rnd() * 0.5, d = R * (0.18 + rnd() * 0.32);
    spots.push([sx + Math.cos(a) * d, sy + Math.sin(a) * d * 0.62 + R * 0.08]);
  }
  spots.sort((a, b) => a[1] - b[1]);
  const roof = dormant ? "#7d7670" : shade(owner, -0.25);
  for (const [x, y] of spots) {
    const w = R * (0.13 + rnd() * 0.06), h = R * (0.1 + rnd() * 0.08);
    ctx.fillStyle = dormant ? "#a39e97" : "#e8dcc4"; ctx.fillRect(x - w / 2, y - h, w, h);
    ctx.fillStyle = "rgba(0,0,0,0.18)"; ctx.fillRect(x, y - h, w / 2, h);
    ctx.fillStyle = roof; ctx.beginPath(); ctx.moveTo(x - w * 0.62, y - h); ctx.lineTo(x, y - h - w * 0.55); ctx.lineTo(x + w * 0.62, y - h); ctx.fill();
  }
  const th = R * (c.is_capital ? 0.62 : 0.4);
  ctx.fillStyle = dormant ? "#9a948c" : "#f1e7d0"; ctx.fillRect(sx - R * 0.07, sy - th + R * 0.05, R * 0.14, th);
  ctx.fillStyle = "rgba(0,0,0,0.2)"; ctx.fillRect(sx, sy - th + R * 0.05, R * 0.07, th);
  ctx.fillStyle = dormant ? "#7d7670" : owner; ctx.beginPath(); ctx.moveTo(sx - R * 0.11, sy - th + R * 0.05); ctx.lineTo(sx, sy - th - R * 0.12); ctx.lineTo(sx + R * 0.11, sy - th + R * 0.05); ctx.fill();
}

function roundRect(x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function drawBanner(c, sx, sy, R) {
  if (S.cam.zoom < 0.42) return;
  const owner = c.owner ? OWNER[c.owner] : "#7e858b";
  const mine = c.owner === S.view.me;
  const status = c.status === "dormant" ? " · dormant" : c.status === "empty" ? " · ruins" : "";
  const label = (c.is_capital ? "★ " : "") + c.name + status;
  const fs = Math.max(10, Math.round(11 * Math.min(1.35, S.cam.zoom)));
  ctx.font = `500 ${fs}px Roboto, Arial, sans-serif`;
  const tw = ctx.measureText(label).width;
  const info = mine ? S.myCityInfo.get(c.id) : null;
  const prodText = info && info.head ? `${info.turns ?? "–"}` : "";
  ctx.font = `700 ${fs - 1}px sans-serif`;
  const pw = prodText ? ctx.measureText(prodText).width + fs * 1.2 : 0;
  const bh = fs * 1.75, bw = tw + bh + pw + fs * 1.2, bx = sx - bw / 2, by = sy - R * 1.32 - bh;
  ctx.fillStyle = "rgba(0,0,0,0.4)"; roundRect(bx + 2, by + 3, bw, bh, bh / 2); ctx.fill();
  const bg = ctx.createLinearGradient(0, by, 0, by + bh);
  bg.addColorStop(0, c.status === "overrun" ? "#5a1712" : "#2a3846"); bg.addColorStop(1, c.status === "overrun" ? "#2a0906" : "#141d26");
  ctx.fillStyle = bg; roundRect(bx, by, bw, bh, bh / 2); ctx.fill();
  ctx.strokeStyle = mine ? "#f2d38a" : shade(owner, -0.1); ctx.lineWidth = mine ? 1.6 : 1.2; ctx.stroke();
  ctx.fillStyle = owner; ctx.beginPath(); ctx.arc(bx + bh / 2, by + bh / 2, bh / 2 - 1.5, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#0b0f13"; ctx.font = `700 ${fs}px Roboto, Arial, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(c.pop), bx + bh / 2, by + bh / 2 + 0.5);
  ctx.fillStyle = "#f6efdc"; ctx.font = `500 ${fs}px Roboto, Arial, sans-serif`; ctx.textAlign = "left";
  ctx.fillText(label, bx + bh + fs * 0.4, by + bh / 2 + 0.5);
  if (prodText) {
    const px = bx + bh + fs * 0.6 + tw + fs * 0.4;
    ctx.fillStyle = "#e69a5c"; ctx.beginPath(); ctx.arc(px + fs * 0.35, by + bh / 2, fs * 0.32, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#f6efdc"; ctx.font = `700 ${fs - 1}px sans-serif`; ctx.fillText(prodText, px + fs * 0.8, by + bh / 2 + 0.5);
  }
  if (c.hp_now != null && c.max_hp) {
    const f = Math.max(0, Math.min(1, c.hp_now / c.max_hp));
    ctx.fillStyle = "rgba(0,0,0,0.6)"; ctx.fillRect(bx + bh * 0.6, by + bh + 1, bw - bh * 1.2, 4);
    ctx.fillStyle = f > 0.5 ? "#82c873" : f > 0.25 ? "#e6c45c" : "#e5705f"; ctx.fillRect(bx + bh * 0.6, by + bh + 1, (bw - bh * 1.2) * f, 4);
  }
}

function isCivilian(type) { const t = S.view.unit_types[type]; return t && t.role === "civilian"; }
function drawUnits(us, sx, sy, R) {
  const military = us.filter((u) => !isCivilian(u.type));
  const civil = us.filter((u) => isCivilian(u.type));
  if (military.length) drawBadge(military[0], sx, sy + 0.05 * R, 0.43 * R, R);
  if (civil.length) drawBadge(civil[0], sx + 0.45 * R, sy + 0.42 * R, 0.27 * R, R);
}
function drawBadge(u, x, y, r, R) {
  const owner = OWNER[u.owner] || "#999";
  const alien = u.owner === "aliens";
  ctx.fillStyle = "rgba(0,0,0,0.35)"; ctx.beginPath(); ctx.ellipse(x + 1, y + r * 0.95, r * 0.9, r * 0.3, 0, 0, Math.PI * 2); ctx.fill();
  const g = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, r * 0.1, x, y, r);
  g.addColorStop(0, alien ? "#4c1611" : "#2c3a48"); g.addColorStop(1, alien ? "#1f0705" : "#10171e");
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = owner; ctx.lineWidth = Math.max(2, r * 0.18); ctx.stroke();
  if (alien) { ctx.strokeStyle = "rgba(255,170,120,0.8)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, r + 1.5, 0, Math.PI * 2); ctx.stroke(); }
  drawUnitIcon(u, x, y, r * 0.62, alien ? "#ffb3a6" : shade(owner, 0.35));
  if (u.count > 1) {
    ctx.fillStyle = "#f2d38a"; ctx.beginPath(); ctx.arc(x + r * 0.82, y - r * 0.82, r * 0.38, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#1a1408"; ctx.font = `700 ${Math.max(7, Math.round(r * 0.45))}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("2", x + r * 0.82, y - r * 0.8);
  }
  if (u.promotions && u.promotions.length) {
    ctx.fillStyle = "#f2d38a"; ctx.font = `700 ${Math.max(7, Math.round(r * 0.5))}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("★".repeat(Math.min(3, u.promotions.length)), x, y + r + Math.max(6, r * 0.45));
  }
  if (u.fortified) { ctx.strokeStyle = "#e6e2d6"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r + 3.5, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); }
  const f = Math.max(0, Math.min(1, u.hp / (u.max_hp || 100)));
  if (f < 1) {
    ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fillRect(x - r, y + r + 2, 2 * r, 3.5);
    ctx.fillStyle = f > 0.5 ? "#82c873" : f > 0.25 ? "#e6c45c" : "#e5705f"; ctx.fillRect(x - r, y + r + 2, 2 * r * f, 3.5);
  }
  if (S.cam.zoom >= 1.25 && r > 8) {
    const label = code(u.type);
    ctx.font = `700 ${Math.max(8, Math.round(R * 0.2))}px sans-serif`;
    const w = ctx.measureText(label).width + 6;
    ctx.fillStyle = "rgba(10,14,18,0.8)"; ctx.fillRect(x - w / 2, y - r - R * 0.28, w, R * 0.24);
    ctx.fillStyle = "#f6efdc"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(label, x, y - r - R * 0.16);
  }
}
function drawUnitIcon(u, x, y, s, color) {
  const spec = S.view.unit_types[u.type] || {};
  ctx.save(); ctx.translate(x, y);
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = Math.max(1.5, s * 0.16); ctx.lineCap = "round";
  if (u.owner === "aliens") {
    for (const d of [-0.5, 0, 0.5]) { ctx.beginPath(); ctx.moveTo(d * s, s * 0.8); ctx.quadraticCurveTo(d * s * 2.2, 0, d * s * 0.6 + s * 0.15, -s * 0.85); ctx.stroke(); }
  } else if (spec.domain === "sea") {
    ctx.beginPath(); ctx.arc(0, -s * 0.6, s * 0.22, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, -s * 0.38); ctx.lineTo(0, s * 0.8); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, s * 0.15, s * 0.65, Math.PI * 0.15, Math.PI * 0.85); ctx.stroke();
  } else if (spec.role === "ranged") {
    ctx.save(); ctx.rotate(-0.5); ctx.fillRect(-s * 0.15, -s * 0.9, s * 0.3, s * 1.2); ctx.restore();
    ctx.beginPath(); ctx.arc(0, s * 0.45, s * 0.38, 0, Math.PI * 2); ctx.stroke();
  } else if (spec.role === "recon") {
    ctx.beginPath(); ctx.moveTo(-s * 0.9, 0); ctx.quadraticCurveTo(0, -s * 0.8, s * 0.9, 0); ctx.quadraticCurveTo(0, s * 0.8, -s * 0.9, 0); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, s * 0.25, 0, Math.PI * 2); ctx.fill();
  } else if (spec.role === "civilian") {
    if (u.type === "restoration_team") { ctx.beginPath(); ctx.moveTo(-s * 0.7, 0); ctx.lineTo(0, -s * 0.7); ctx.lineTo(s * 0.7, 0); ctx.lineTo(s * 0.5, 0); ctx.lineTo(s * 0.5, s * 0.7); ctx.lineTo(-s * 0.5, s * 0.7); ctx.lineTo(-s * 0.5, 0); ctx.closePath(); ctx.stroke(); }
    else if (u.type === "trade_convoy") { ctx.strokeRect(-s * 0.6, -s * 0.5, s * 1.2, s * 1); ctx.beginPath(); ctx.moveTo(-s * 0.6, -s * 0.5); ctx.lineTo(s * 0.6, s * 0.5); ctx.moveTo(s * 0.6, -s * 0.5); ctx.lineTo(-s * 0.6, s * 0.5); ctx.stroke(); }
    else { ctx.save(); ctx.rotate(0.7); ctx.fillRect(-s * 0.1, -s * 0.2, s * 0.2, s * 1.1); ctx.fillRect(-s * 0.45, -s * 0.6, s * 0.9, s * 0.4); ctx.restore(); }
  } else {
    for (const sgn of [-1, 1]) {
      ctx.save(); ctx.rotate(sgn * 0.75);
      ctx.beginPath(); ctx.moveTo(0, -s * 0.95); ctx.lineTo(0, s * 0.55); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-s * 0.28, s * 0.4); ctx.lineTo(s * 0.28, s * 0.4); ctx.stroke();
      ctx.restore();
    }
  }
  ctx.restore();
}

// =============================================================================================
// minimap

const mini = $("minimap");
const mctx = mini.getContext("2d");
function drawMinimap() {
  const v = S.view, sx = mini.width / v.width, sy = mini.height / v.height;
  mctx.fillStyle = FOG_THICK; mctx.fillRect(0, 0, mini.width, mini.height);
  for (const i of S.explored) { const [c, r] = colRow(i); mctx.fillStyle = FOG_MIST; mctx.fillRect(c * sx, r * sy, sx + 0.6, sy + 0.6); }
  for (const [i, t] of S.tilesByIndex) { const [c, r] = colRow(i); mctx.fillStyle = MINI[t.terrain]; mctx.fillRect(c * sx, r * sy, sx + 0.6, sy + 0.6); }
  for (const c of S.citiesByTile.values()) {
    const [cc, rr] = colRow(c.tile);
    mctx.fillStyle = "#0b0f13"; mctx.fillRect(cc * sx - 2, rr * sy - 2, 5, 5);
    mctx.fillStyle = c.owner ? OWNER[c.owner] : "#ccc"; mctx.fillRect(cc * sx - 1.5, rr * sy - 1.5, 4, 4);
  }
  const [x0, y0] = toWorld(0, 0), [x1, y1] = toWorld(canvas.clientWidth, canvas.clientHeight);
  const ww = SQ3 * R0 * v.width, wh = 1.5 * R0 * v.height;
  mctx.strokeStyle = "#f2d38a"; mctx.lineWidth = 1.2;
  mctx.strokeRect(x0 / ww * mini.width, y0 / wh * mini.height, (x1 - x0) / ww * mini.width, (y1 - y0) / wh * mini.height);
}
mini.addEventListener("click", (e) => {
  const rect = mini.getBoundingClientRect();
  const fx = (e.clientX - rect.left) / rect.width, fy = (e.clientY - rect.top) / rect.height;
  centerOnWorld(fx * SQ3 * R0 * S.view.width, fy * 1.5 * R0 * S.view.height);
});
function centerOnWorld(wx, wy) {
  S.cam.x = wx - canvas.clientWidth / 2 / S.cam.zoom;
  S.cam.y = wy - canvas.clientHeight / 2 / S.cam.zoom;
  S.dirty = true;
}
function centerOnTile(i) { centerOnWorld(...center(i)); }

// =============================================================================================
// top bar, pending list, event log

function renderChrome() {
  const v = S.view, e = v.economy;
  $("turninfo").innerHTML = `${ICON.turn}Turn <b>${v.turn}</b> · ${v.year}`;
  const gd = e.gold_per_turn;
  $("gold").innerHTML = `${ICON.gold}<b style="color:var(--gold)">${e.gold}</b> <span class="${gd >= 0 ? "good" : "bad"}">(${gd >= 0 ? "+" : ""}${gd})</span>`;
  const rs = v.research;
  $("science").innerHTML = `${ICON.science}<b style="color:var(--science)">+${e.science_per_turn}</b> · ${rs ? `${esc(pretty(rs.tech))} <span class="muted">(${rs.turns ?? "–"})</span>` : '<span class="bad">choose research</span>'}`;
  $("beacon").innerHTML = `${ICON.beacon}<b style="color:var(--beacon)">${e.beacon_points}</b>${e.arrival_cost ? `/${e.arrival_cost}` : ""} <span class="muted">rarity ${e.rarity}</span>`;
  for (const [id, y] of [["gold", "gold"], ["science", "science"], ["beacon", "beacon"]]) { $(id).dataset.tip = breakdownHtml(y, e); $(id).removeAttribute("title"); }
  const knownAlien = Object.values(v.cities).filter((c) => c.status === "overrun").length;
  $("threat").innerHTML = `${ICON.ship}${v.mothership_alive ? "Mothership <b class='bad'>active</b>" : "Mothership <b class='good'>destroyed</b>"} · alien cities <b>${knownAlien}</b>`;
  const ul = $("pending");
  ul.innerHTML = "";
  for (const p of v.pending.slice(0, 14)) {
    const li = document.createElement("li");
    li.textContent = describePending(p);
    li.onclick = () => resolvePending(p);
    ul.appendChild(li);
  }
  if (v.pending.length > 14) { const li = document.createElement("li"); li.className = "muted"; li.textContent = `…and ${v.pending.length - 14} more`; ul.appendChild(li); }
  if (!v.pending.length) { const li = document.createElement("li"); li.className = "muted"; li.textContent = "Nothing. Ready for the next turn."; ul.appendChild(li); }
  const log = $("log");
  log.innerHTML = "";
  for (const ev of v.events.slice(-40).reverse()) {
    const li = document.createElement("li"); li.textContent = describeEvent(ev);
    const t = eventTile(ev);
    if (t != null) { li.classList.add("clickable"); li.title = "Show on the map"; li.onclick = () => goToEvent(ev); }
    log.appendChild(li);
  }
  const btn = $("endturn");
  const next = nextAction();
  btn.textContent = v.outcome ? pretty(v.outcome) : next ? ACTION_LABEL[next.kind] : "Next turn";
  btn.title = next ? "Takes you to it. Shift-click to end the turn anyway." : "End the turn (Enter)";
  btn.classList.toggle("waiting", !!next);
  btn.disabled = !!v.outcome;
  if (v.outcome && !S.shownOutcome) { S.shownOutcome = true; openScreen("scores"); }
}

function cityName(id) { const c = S.view.cities[id]; return c ? c.name : `city ${id}`; }
function unitLabel(id) { const u = S.view.units.find((x) => x.id === id); return u ? pretty(u.type) : "A unit"; }
function describePending(p) {
  return {
    choose_research: "Choose research",
    choose_production: `${cityName(p.city)}: choose production`,
    unit_needs_orders: `${unitLabel(p.unit)} needs orders`,
    recruit_unseated: "A recruit has no council seat",
    offer_received: "A recruit is offered to you",
    deal_received: "A deal is proposed to you",
    choose_espionage_tech: "Choose your alien technology",
    city_can_attack: `${cityName(p.city)} can attack an enemy`,
    unit_promotion: `${unitLabel(p.unit)} can be promoted`,
  }[p.kind] || pretty(p.kind);
}
async function resolvePending(p) {
  if (p.kind === "choose_research") return openScreen("techs");
  if (p.kind === "choose_production") { centerOnTile(S.view.cities[p.city].tile); return selectCity(p.city); }
  if (p.kind === "unit_needs_orders") { const u = S.view.units.find((x) => x.id === p.unit); if (u) centerOnTile(u.tile); return selectUnit(p.unit); }
  if (p.kind === "recruit_unseated" || p.kind === "offer_received") return openScreen("council");
  if (p.kind === "deal_received") return openScreen("diplomacy");
  if (p.kind === "choose_espionage_tech") return openScreen("projects");
  if (p.kind === "unit_promotion") {
    const u = S.view.units.find((x) => x.id === p.unit);
    if (u && S.view.unit_types[u.type]?.fixed) { const c = S.citiesByTile.get(u.tile); if (c) { centerOnTile(u.tile); return selectCity(c.id); } }
    if (u) centerOnTile(u.tile); return selectUnit(p.unit);
  }
  if (p.kind === "city_can_attack") {
    centerOnTile(S.view.cities[p.city].tile); await selectCity(p.city);
    S.dirty = true; toast("Enemy near the city: click a red hex to fire, or Hold fire.");
  }
}
function describeEvent(e) {
  const m = {
    turn_started: () => `Turn ${e.turn} begins (${e.year}).`,
    city_grew: () => `${cityName(e.city)} grew to ${e.pop}.`,
    citizen_born: () => `${e.name} was born in ${cityName(e.city)} (${statText(e.stats)}${e.traits.length ? `, ${e.traits.map(pretty).join(", ")}` : ""}).`,
    contact_made: () => e.how === "distress" ? `${pretty(e.other === S.view.me ? e.player : e.other)} has fallen: its position is now known to all.` : `First contact: ${pretty(e.other === S.view.me ? e.player : e.other)}! You can now trade and ally.`,
    alien_tech: () => `The aliens developed ${pretty(e.tech)}.`,
    pillaged: () => `Aliens pillaged a ${pretty(e.lost)}.`,
    turret_destroyed: () => "Aliens destroyed one of your turrets.",
    civilians_captured: () => "Aliens captured civilians.",
    citizen_grew_up: () => `${e.name} of ${cityName(e.city)} has grown up and can work.`,
    citizen_job: () => "Citizen job changed.",
    unit_promoted: () => `${unitLabel(e.unit)} promoted: ${promoName(e.promotion)}.`,
    building_completed: () => `${cityName(e.city)} built ${pretty(e.building)}.`,
    unit_completed: () => `${cityName(e.city)} trained ${pretty(e.type)}.`,
    tech_learned: () => `Learned ${pretty(e.tech)}.`,
    city_reclaimed: () => `Reclaimed ${cityName(e.city)}.`,
    city_refounded: () => `Refounded ${cityName(e.city)}.`,
    city_liberated: () => `Liberated ${cityName(e.city)}!`,
    city_overrun: () => `${cityName(e.city)} was overrun by aliens.`,
    unit_destroyed: () => `${pretty(e.type)} destroyed.`,
    recruit_arrived: () => `${e.name} answered the beacon${e.legendary ? " (legendary)" : ""}.`,
    recruit_betrayed: () => `${e.name} betrayed you.`,
    recruit_died: () => `${e.name} died.`,
    mothership_strike: () => `The mothership struck ${cityName(e.city)}.`,
    barrage_fired: () => "The world barrage fired. The mothership is destroyed!",
    game_over: () => `Game over: ${pretty(e.outcome)}.`,
    attack: () => `Attack: ${e.damage_to_defender} dealt, ${e.damage_to_attacker} taken.`,
    production_stalled: () => `${cityName(e.city)} cannot finish ${pretty(e.item.split(":")[1])}.`,
    gold_deficit: () => `Treasury empty: ${e.shortfall} taken from research.`,
    unit_moved: () => `${unitLabel(e.unit)} moved.`,
    research_set: () => `Researching ${pretty(e.tech)}.`,
    production_set: () => `${cityName(e.city)} now builds ${e.items.map((x) => pretty(x.split(":")[1])).join(", ") || "nothing"}.`,
    job_started: () => `Engineers started ${pretty(e.improvement)}.`,
    improvement_built: () => `${pretty(e.improvement)} completed.`,
    unit_fortified: () => `${unitLabel(e.unit)} fortified.`,
    unit_skipped: () => `${unitLabel(e.unit)} waits.`,
    deal_accepted: () => `Deal accepted with ${pretty(e.proposer)}.`,
    shipment_arrived: () => `A shipment from ${pretty(e.from)} arrived.`,
    unit_landed: () => `${unitLabel(e.unit)} landed abroad.`,
  };
  return m[e.kind] ? m[e.kind]() : pretty(e.kind);
}

// =============================================================================================
// selection panels

function clearSelection() {
  S.selected = null; S.options = null; S.city = null; S.targetMode = null;
  $("side").classList.add("hidden");
  S.dirty = true;
}
async function selectUnit(id, centerIt = false) {
  try { S.options = await api(`/api/unit/${id}`); } catch (err) { clearSelection(); return; }
  S.selected = { kind: "unit", id }; S.city = null; S.targetMode = null;
  if (centerIt) centerOnTile(S.options.unit.tile);
  renderUnitPanel(); S.dirty = true;
}
function renderUnitPanel() {
  const o = S.options, u = o.unit, spec = o.spec, side = $("side");
  const moves = (u.moves_left / 30).toFixed(1).replace(/\.0$/, "");
  const ranged = spec.ranged_strength ? ` · ranged ${spec.ranged_strength} (range ${spec.range})` : "";
  side.innerHTML = `
    <div class="title">${esc(pretty(u.type))}${u.count > 1 ? " ×2" : ""}</div>
    <div class="muted">${esc(spec.role)} · strength ${spec.strength * u.count}${ranged}</div>
    ${spec.fixed ? `<div class="muted">City defence: never moves${spec.no_attack ? " and never attacks; it only protects its city" : "; fires at anything in range"}. It adds to the city's strength.</div>` : ""}
    <div class="row">HP ${u.hp}/${100 * u.count}${spec.fixed ? "" : ` · moves ${moves}/${spec.moves}`}${u.fortified ? " · fortified" : ""}${u.job ? ` · building ${pretty(u.job.improvement)} (${u.job.turns_left})` : ""}</div>
    <div class="bar"><i style="width:${Math.round(100 * u.hp / (100 * u.count))}%"></i></div>
    <div class="actions" id="uactions"></div>
    <div class="muted" style="font-size:12px">${spec.fixed ? (spec.no_attack ? "" : "Red hexes can be fired on (hover for the odds).") : "Click a highlighted hex to move; red hexes can be attacked (hover for the odds)."}</div>`;
  const a = $("uactions");
  const add = (label, fn, title = "") => { const b = document.createElement("button"); b.textContent = label; b.title = title; b.onclick = fn; a.appendChild(b); };
  const pr = o.promotion;
  if (spec.role !== "civilian") {
    a.insertAdjacentHTML("beforebegin", `<div class="row muted">Experience ${pr.xp} · next promotion at ${pr.next}${pr.taken.length ? ` · ${pr.taken.map(promoName).join(", ")}` : ""}</div>`);
    for (let k = 0; k < Math.min(1, pr.due); k++) for (const opt of pr.options) {
      add(`Promote: ${promoName(opt.id)}`, () => send({ kind: "promote_unit", unit: u.id, promotion: opt.id }), opt.note);
      a.lastChild.classList.add("primary");
    }
  }
  if (u.job) add(`Cancel ${pretty(u.job.improvement)}`, () => send({ kind: "cancel_job", unit: u.id }), "Stop building (the work is lost) so the engineers can move away");
  if (spec.role !== "civilian" && !u.job && u.attacks_left > 0) add("Fortify (F)", () => send({ kind: "fortify", unit: u.id }), "+25% defence; a unit that neither moves nor attacks heals 20 HP a turn at home, 10 outside");
  add("Skip (S)", () => send({ kind: "skip_unit", unit: u.id }));
  for (const imp of o.builds) {
    const bi = o.build_info[imp];
    const change = Object.keys(bi.after).filter((k) => bi.after[k] !== bi.before[k]).map((k) => `${k} ${bi.before[k]} → ${bi.after[k]}`);
    const extra = `<div class="tip-kind">${change.length ? `This tile: ${change.join(", ")}` : "No change to this tile's yields"}${bi.city ? ` · works for ${esc(bi.city)}` : " · outside your cities' land"}</div>`;
    const short = change.length ? ` (${Object.keys(bi.after).filter((k) => bi.after[k] > bi.before[k]).map((k) => `+${bi.after[k] - bi.before[k]} ${k}`).join(", ")})` : "";
    add(`Build ${pretty(imp)}${short}`, () => send({ kind: "build_improvement", unit: u.id, improvement: imp }));
    a.lastChild.dataset.tip = infoHtml(pretty(imp), bi, extra); a.lastChild.title = "";
  }
  if (o.refound) add("Refound city", () => send({ kind: "refound_city", unit: u.id }));
  if (o.merges.length) a.insertAdjacentHTML("afterend", '<div class="muted small">Move onto the highlighted unit of the same type to merge into a stack of two.</div>');
  if (o.splits.length) add("Split stack", () => send({ kind: "split_unit", unit: u.id, target: o.splits[0] }));
  if (o.ships.length) {
    const sel = document.createElement("select");
    for (const s of o.ships) { const opt = document.createElement("option"); opt.value = s.city; opt.textContent = `${s.name} (${s.price} gold)`; sel.appendChild(opt); }
    a.appendChild(sel);
    add("Ship abroad", () => send({ kind: "ship_unit", unit: u.id, city: Number(sel.value) }));
  }
  side.classList.remove("hidden");
}
async function selectCity(id, centerIt = false) {
  if (!S.selected || S.selected.kind !== "city" || S.selected.id !== id) S.cityListOpen = false;
  try { S.city = await api(`/api/city/${id}`); } catch (err) { clearSelection(); return; }
  S.selected = { kind: "city", id }; S.options = null; S.targetMode = null;
  if (centerIt) centerOnTile(S.city.city.tile);
  // Civ style: a city that can fire shows its targets in red straight away; click one to fire.
  if (S.city.bombard.length) S.targetMode = "bombard";
  renderCityPanel(); S.dirty = true;
}
function yieldBox(k, total, lines) {
  const parts = lines.filter((l) => l[1] === k).map((l) => `${pretty(l[0].replace(/^\w+:/, ""))}: ${l[2] >= 0 ? "+" : ""}${l[2]}`);
  return `<div class="yield y-${k}" title="${esc(parts.join("\n") || "nothing")}"><b>${total}</b>${pretty(k)}</div>`;
}
function renderCityPanel() {
  const d = S.city, c = d.city, side = $("side");
  if (window.Advisors) Advisors.trigger("production");
  const surplus = d.totals.food - d.food_eaten;
  const head = c.queue[0];
  const headOpt = head ? d.options.find((o) => o.item === head) : null;
  const groups = { building: [], unit: [], project: [] };
  for (const o of d.options) groups[o.kind].push(o);
  const list = Object.entries(groups).filter(([, v]) => v.length).map(([k, v]) =>
    `<div class="group">${k}s</div>` + v.map((o) => `<div class="item${o.item === head ? " current" : ""}" data-price="${o.price ?? ""}" data-item="${esc(o.item)}" data-tip="${esc(infoHtml(pretty(o.id), o.info, `<div class="tip-kind">${o.cost != null ? `Cost ${o.cost} production` : "Ongoing"}${o.turns != null ? ` · ${o.turns} turns here` : ""}${o.price ? ` · or buy now for ${o.price} gold` : ""}</div>`))}"><span>${esc(pretty(o.id))}</span><span class="muted">${o.cost ?? ""}${o.turns != null ? ` · ${o.turns}t` : ""}${o.price ? ` · ${o.price}g` : ""}</span></div>`).join("")).join("");
  side.innerHTML = `
    <div class="title">${c.is_capital ? "★ " : ""}${esc(c.name)}</div>
    <div class="row muted">Population ${c.pop} · food ${c.food_store}/${d.growth_threshold} (${surplus >= 0 ? "+" : ""}${surplus}) · ${c.connected ? "connected" : '<span class="bad">not connected: produces nothing</span>'}</div>
    <div class="row muted">HP ${c.hp}/${d.max_hp} · strength ${Math.round(d.strength / 100)}</div>
    <div class="yields">${YIELD_KEYS.map((k) => yieldBox(k, d.totals[k], d.lines)).join("")}</div>
    <div class="row">Focus <select id="focus">${d.focuses.map((f) => `<option ${f === c.focus ? "selected" : ""}>${f}</option>`).join("")}</select></div>
    <h3>Producing</h3>
    <div class="row">${head ? `${esc(pretty(head.split(":")[1]))} <span class="muted">${c.production_store}/${headOpt?.cost ?? "–"}${headOpt?.turns != null ? ` · ${headOpt.turns} turns` : ""}</span>` : '<span class="bad">nothing</span>'}
      ${headOpt?.price ? `<button class="small" id="buy" ${S.view.economy.gold < headOpt.price ? "disabled" : ""}>Buy ${headOpt.price}g</button>` : ""}</div>
    ${head && !S.cityListOpen ? '<div class="actions"><button id="changeprod">Change production…</button></div>' : `<h3>${head ? "Change production" : "Choose production"}</h3>
    <div class="list" id="prodlist">${list}</div>`}
    <h3>Citizens <button class="small" id="citpage">Citizens page</button></h3>
    <div class="muted small">Improved tiles are outlined on the map: green ✓ is worked, gold + is free; click a + to put your best citizen there.</div>
    <div class="citizens">${d.citizens.map((p) => citizenRow(p, d)).join("")}</div>
    <h3>Defences</h3>
    <div class="muted">${(S.defencesByTile.get(c.tile) || []).map((u) => `${esc(pretty(u.type))} (${u.hp}/${u.max_hp} HP${u.promotion ? `, level ${u.promotion.level + 1}` : ""})${u.promotion && u.promotion.upgrade_cost != null ? ` <button class="small" data-upgrade-gun="${u.id}" ${S.view.economy.gold < u.promotion.upgrade_cost ? "disabled" : ""} title="+${u.promotion.strength_pct}% attack and defence">Upgrade (${u.promotion.upgrade_cost}g)</button>` : ""}`).join(", ") || "none"}${(S.defencesByTile.get(c.tile) || []).some((u) => !S.view.unit_types[u.type].no_attack) ? ". Guns fire at the nearest weak enemy in range at the end of every turn." : ""}</div>
    <h3>Buildings</h3>
    <div class="muted">${c.buildings.map(pretty).join(", ") || "none"}</div>
    ${d.bombard.length ? `<div class="actions"><span class="bad">Enemies in range are marked red: click one to fire.</span>${S.view.pending.some((p) => p.kind === "city_can_attack" && p.city === c.id) ? '<button id="holdfire">Hold fire</button>' : ""}</div>` : ""}`;
  side.querySelectorAll("select[data-citizen]").forEach((el) => el.onchange = () => send({ kind: "set_citizen_job", citizen: Number(el.dataset.citizen), job: el.value }));
  if ($("holdfire")) $("holdfire").onclick = () => send({ kind: "city_hold_fire", city: c.id });
  side.querySelectorAll("[data-upgrade-gun]").forEach((el) => el.onclick = () => send({ kind: "upgrade_defence", unit: Number(el.dataset.upgradeGun) }));
  if ($("citpage")) $("citpage").onclick = () => openScreen("population", c.id);
  side.querySelectorAll("#prodlist .item").forEach((el) => el.onclick = async () => {
    if (el.dataset.item === head) return;
    S.cityListOpen = false;
    await send({ kind: "set_production", city: c.id, items: [el.dataset.item] });
    // Civ style: once the city has something to build, move on to the next decision
    if (!S.view.pending.some((p) => p.kind === "choose_production" && p.city === c.id)) { clearSelection(); }
  });
  if ($("changeprod")) $("changeprod").onclick = () => { S.cityListOpen = true; renderCityPanel(); };
  $("focus").onchange = (e) => send({ kind: "set_focus", city: c.id, focus: e.target.value });
  if ($("buy")) $("buy").onclick = () => send({ kind: "purchase", city: c.id });
  side.classList.remove("hidden");
}

// =============================================================================================
// commands

async function send(cmd) {
  if (S.busy) return;
  S.busy = true;
  try { const res = await api("/api/command", cmd); if (res.ok === false) toast(res.error); } catch (err) { toast(err.message); }
  S.busy = false;
  await refresh(true);
}
// Like Civ V, the big button names the next thing that needs you and takes you there; it only
// says "Next turn" when nothing is left. Shift-click (or Shift+Enter) ends the turn anyway.
const ACTION_ORDER = ["city_can_attack", "unit_promotion", "choose_research", "choose_production", "unit_needs_orders", "choose_espionage_tech",
  "deal_received", "offer_received", "recruit_unseated"];
const ACTION_LABEL = {
  choose_research: "Choose research", choose_production: "Choose production", unit_needs_orders: "Unit needs orders",
  choose_espionage_tech: "Choose alien tech", deal_received: "Answer a proposal", offer_received: "Answer an offer",
  recruit_unseated: "Seat a recruit", city_can_attack: "City can attack", unit_promotion: "Promote a unit",
};
function nextAction() {
  if (!S.view) return null;
  for (const kind of ACTION_ORDER) {
    const p = S.view.pending.find((x) => x.kind === kind);
    if (p) return p;
  }
  return null;
}
async function mainButton(force = false) {
  if (S.busy || !S.view || S.view.outcome) return;
  const next = nextAction();
  if (next && !force) return resolvePending(next);
  S.busy = true;
  $("endturn").textContent = "Aliens moving…";
  try { await api("/api/end_turn", {}); } catch (err) { toast(err.message); }
  S.busy = false;
  await refresh(true);
  if (!summaryOff() && !S.view.outcome) openScreen("summary");
}
$("endturn").onclick = (e) => mainButton(e.shiftKey);

// =============================================================================================
// map input

let drag = null;
canvas.addEventListener("mousedown", (e) => { drag = { x: e.clientX, y: e.clientY, cx: S.cam.x, cy: S.cam.y, moved: false }; });
window.addEventListener("mouseup", (e) => {
  if (drag && !drag.moved && e.target === canvas && e.button === 0) onClick(e);
  drag = null; canvas.classList.remove("dragging");
});
canvas.addEventListener("mousemove", (e) => {
  if (!S.view) return;
  if (drag) {
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; canvas.classList.add("dragging"); }
    if (drag.moved) { S.cam.x = drag.cx - dx / S.cam.zoom; S.cam.y = drag.cy - dy / S.cam.zoom; S.dirty = true; }
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const i = pick(e.clientX - rect.left, e.clientY - rect.top);
  if (i !== S.hover) { S.hover = i; S.dirty = true; }
  showTooltip(i, e.clientX - rect.left, e.clientY - rect.top);
});
canvas.addEventListener("mouseleave", () => { S.hover = null; $("tooltip").classList.add("hidden"); S.dirty = true; });
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const [wx, wy] = toWorld(mx, my);
  S.cam.zoom = Math.max(0.3, Math.min(2.6, S.cam.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
  S.cam.x = wx - mx / S.cam.zoom; S.cam.y = wy - my / S.cam.zoom;
  S.dirty = true;
}, { passive: false });
canvas.addEventListener("contextmenu", (e) => { e.preventDefault(); clearSelection(); });

async function onClick(e) {
  const rect = canvas.getBoundingClientRect();
  const i = pick(e.clientX - rect.left, e.clientY - rect.top);
  if (i === null) return;
  if (S.targetMode === "bombard" && S.city) {
    if (S.city.bombard.includes(i)) return send({ kind: "city_attack", city: S.city.city.id, target: i });
  }
  if (S.city && S.selected && S.selected.kind === "city" && S.city.workable.some((w) => w.tile === i)) {
    const worked = S.city.citizens.some((p) => p.tile === i);
    if (!worked) return send({ kind: "assign_best_citizen", city: S.city.city.id, tile: i }).then(() => S.city && toastJob());
  }
  if (S.options) {
    const u = S.options.unit;
    if (S.options.attacks.some((a) => a.tile === i)) return send({ kind: "attack", unit: u.id, target: i });
    if (S.options.reachable.includes(i) || mergeTiles().includes(i)) return send({ kind: "move_unit", unit: u.id, target: i });
  }
  const mine = (S.unitsByTile.get(i) || []).filter((u) => u.owner === S.view.me);
  const city = S.citiesByTile.get(i);
  if (mine.length) {
    let next = mine[0];
    if (S.selected && S.selected.kind === "unit") {
      const k = mine.findIndex((u) => u.id === S.selected.id);
      if (k >= 0 && k === mine.length - 1 && city && city.owner === S.view.me) return selectCity(city.id);
      if (k >= 0) next = mine[(k + 1) % mine.length];
    }
    return selectUnit(next.id);
  }
  if (city && city.owner === S.view.me) return selectCity(city.id);
  const tt = S.tilesByIndex.get(i);
  if (tt && tt.turret && tt.built_by === S.view.me) return showTurretPanel(i);
  clearSelection();
}

function showTooltip(i, x, y) {
  const tip = $("tooltip");
  if (i === null) { tip.classList.add("hidden"); return; }
  let html = "";
  const attack = S.options && S.options.attacks.find((a) => a.tile === i);
  if (attack) { html = previewHtml(attack.preview); if (window.Advisors) Advisors.trigger("combat"); }
  else {
    const t = S.tilesByIndex.get(i), c = S.citiesByTile.get(i), us = S.unitsByTile.get(i) || [];
    if (t) {
      html += `<b>${pretty(t.terrain)}</b>${t.elevation !== "flat" ? ` · ${t.elevation}` : ""}${t.feature ? ` · ${t.feature}` : ""}`;
      if (t.resource && t.visible) html += `<br>Resource: ${pretty(t.resource)}`;
      if (t.improvement || t.route) html += `<br>${[t.improvement, t.route].filter(Boolean).map(pretty).join(", ")}`;
      if (t.turret) html += `<br><b>Turret</b> level ${t.turret} · ${t.turret_hp} HP${t.built_by === S.view.me ? " · click to upgrade" : ""}`;
      if (t.yields) {
        const ys = Object.entries(t.yields).filter(([, v]) => v).map(([k, v]) => `<span class="y-${k}">+${v} ${k}</span>`).join(" ");
        if (ys) html += `<br>Tile gives ${ys}`;
      }
      const w = S.view.worked && S.view.worked[i];
      if (w) {
        const bs = hundredthsText(w.bonus);
        html += `<br>Worked by <b>${esc(w.citizen)}</b> for ${esc(w.city)}${bs ? ` (adds ${bs})` : ""}`;
      } else if (t.improvement) html += '<br><span class="muted">Not worked: no grown citizen on it</span>';
      if (!t.visible) html += '<br><span class="muted">not currently seen</span>';
    } else if (S.explored.has(i)) html = '<span class="muted">Mist: explored, not seen now</span>';
    else html = '<span class="muted">Fog: unexplored</span>';
    if (c) html += `<br><b>${esc(c.name)}</b> · ${c.status}${c.owner ? ` · ${pretty(c.owner)}` : ""} · pop ${c.pop}`;
    for (const u of us) html += `<br>${pretty(u.owner)}: ${pretty(u.type)}${u.count > 1 ? " ×2" : ""} (${u.hp} HP)`;
  }
  tip.innerHTML = html;
  tip.classList.remove("hidden");
  tip.style.left = `${Math.min(x + 16, canvas.clientWidth - 350)}px`;
  tip.style.top = `${y + 16}px`;
}
function strengthLines(side) {
  return side.lines.map((l) => {
    if (l.kind === "base") return `${pretty(l.source)} ${l.value}`;
    if (l.kind === "multiplier") return `${pretty(l.source)} ×${l.value}`;
    if (l.kind === "pct_of") return `${pretty(l.source)} ${l.value}%`;
    if (l.kind === "flat_hundredths") return `${pretty(l.source)} +${(l.value / 100).toFixed(1)}`;
    return `${pretty(l.source)} ${l.value >= 0 ? "+" : ""}${l.value}%`;
  }).join("<br>");
}
// Combat preview, Civ V style: an outcome banner, both strengths with their modifiers, and HP
// bars where the flashing red part is the damage each side should take.
function hpBar(side, dmg) {
  const max = side.max_hp || 100, hp = side.hp, lost = Math.min(hp, dmg.expected);
  const keep = Math.max(0, hp - lost);
  return `<div class="hpbar"><div class="keep" style="height:${100 * keep / max}%"></div><div class="lose" style="height:${100 * lost / max}%"></div></div>
    <div class="hptext">${hp} → <b>${keep}</b><br><span class="muted">${dmg.min}-${dmg.max} dmg</span></div>`;
}
function modLines(side) {
  return side.lines.filter((l) => l.kind !== "base" || l.source !== "base").map((l) => {
    const v = l.kind === "pct" ? `${l.value >= 0 ? "+" : ""}${l.value}%` : l.kind === "pct_of" ? `×${l.value}%` : l.kind === "multiplier" ? `×${l.value}` : l.kind === "flat_hundredths" ? `+${(l.value / 100).toFixed(1)}` : `+${l.value}`;
    const good = !(l.kind === "pct_of" && l.value < 100) && !(l.kind === "pct" && l.value < 0);
    return `<div class="mod"><span>${esc(pretty(l.source.replace(/^\w+:/, "")))}</span><b class="${good ? "good" : "bad"}">${v}</b></div>`;
  }).join("");
}
function previewHtml(p) {
  if (p.kind === "capture") return '<div class="cbanner capture">CAPTURE</div><div class="muted">Only civilians stand here: walk in to take them.</div>';
  const dd = p.damage_to_defender, da = p.damage_to_attacker;
  const kills = dd.expected >= p.defender.hp, dies = da.expected >= p.attacker.hp;
  const [label, cls] = kills && p.defender.type === "city" && p.kind === "melee" ? ["CAPTURE CITY", "win"]
    : kills ? ["DECISIVE VICTORY", "win"] : dies ? ["LIKELY DEFEAT", "lose"]
    : p.kind === "ranged" ? ["RANGED ATTACK", "win"]
    : dd.expected > da.expected * 1.5 ? ["MAJOR VICTORY", "win"] : dd.expected >= da.expected ? ["MINOR VICTORY", "even"] : ["COSTLY ATTACK", "lose"];
  return `<div class="cbanner ${cls}">${label}</div>
    <div class="cgrid">
      <div class="cside">
        <div class="cname">Your ${esc(pretty(p.attacker.type))}</div>
        <div class="cstr">${(p.attacker.strength / 100).toFixed(1)}</div><div class="muted small">strength</div>
        ${modLines(p.attacker)}
      </div>
      <div class="cbars">${hpBar(p.attacker, da)}</div>
      <div class="cbars">${hpBar(p.defender, dd)}</div>
      <div class="cside">
        <div class="cname">${p.defender.type === "city" ? "City" : esc(pretty(p.defender.type))}</div>
        <div class="cstr">${(p.defender.strength / 100).toFixed(1)}</div><div class="muted small">strength</div>
        ${modLines(p.defender)}
      </div>
    </div>
    <div class="cdmg"><span>You deal <b class="good">${dd.expected}</b></span><span>You take <b class="bad">${da.expected}</b></span></div>`;
}

window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || !S.inGame) return;
  if (e.key === "Escape") {
    if (!$("modal").classList.contains("hidden")) closeModal();
    else if (S.selected) clearSelection();
    else openScreen("menu");
  } else if (e.key === "Enter") mainButton(e.shiftKey);
  else if (e.key === " " || e.key === "n") { e.preventDefault(); const p = S.view.pending.find((x) => x.kind === "unit_needs_orders"); if (p) resolvePending(p); }
  else if (e.key === "f" && S.options) send({ kind: "fortify", unit: S.options.unit.id });
  else if (e.key === "s" && S.options) send({ kind: "skip_unit", unit: S.options.unit.id });
  else if (e.key === "t") openScreen("techs");
  else if (e.key === "c") openScreen("council");
  else if (e.key === "d") openScreen("diplomacy");
  else if (e.key === "p") openScreen("projects");
  else if (e.key.startsWith("Arrow")) {
    const d = 120 / S.cam.zoom;
    if (e.key === "ArrowLeft") S.cam.x -= d;
    if (e.key === "ArrowRight") S.cam.x += d;
    if (e.key === "ArrowUp") S.cam.y -= d;
    if (e.key === "ArrowDown") S.cam.y += d;
    S.dirty = true;
  }
});

// =============================================================================================
// screens (modal)

document.querySelectorAll("#topbar nav button").forEach((b) => b.onclick = () => openScreen(b.dataset.screen));
// Top-bar numbers open their screens: science -> tech, beacon -> council, gold -> diplomacy,
// mothership -> projects (Civ V style).
for (const [id, screen] of [["science", "techs"], ["beacon", "council"], ["gold", "diplomacy"], ["threat", "projects"]]) {
  $(id).classList.add("clickable"); $(id).onclick = () => openScreen(screen);
}
document.querySelector("#modal .close").onclick = closeModal;
$("modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
// Hover cards for anything with data-tip (production items, tech unlocks): what it does, Civ style.
const itemTip = document.createElement("div");
itemTip.id = "itemtip"; itemTip.className = "hidden"; document.body.appendChild(itemTip);
document.addEventListener("mouseover", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (!el) { itemTip.classList.add("hidden"); return; }
  itemTip.innerHTML = el.dataset.tip; itemTip.classList.remove("hidden");
  const r = el.getBoundingClientRect(), w = itemTip.offsetWidth, h = itemTip.offsetHeight;
  let x = r.right + 8, y = r.top;
  if (el.closest("#topbar")) { x = r.left; y = r.bottom + 6; }  // under the top bar numbers
  if (x + w > innerWidth - 8) x = Math.max(8, r.left - w - 8);
  if (y + h > innerHeight - 8) y = Math.max(8, innerHeight - h - 8);
  itemTip.style.left = `${x}px`; itemTip.style.top = `${y}px`;
});
function closeModal() { $("modal").classList.add("hidden"); document.querySelector(".modal-box").classList.remove("narrow"); S.screen = null; }

async function openScreen(name, arg = null) {
  S.screen = name; S.screenArg = arg;
  const body = $("modal-body");
  try {
    if (name === "techs") body.innerHTML = techScreen(await api("/api/techs"));
    else if (name === "council") { S.councilData = await api("/api/council"); body.innerHTML = councilScreen(S.councilData); }
    else if (name === "population") body.innerHTML = populationScreen(await api("/api/population"), arg);
    else if (name === "cities") body.innerHTML = citiesScreen(await api("/api/cities"));
    else if (name === "units") body.innerHTML = unitsScreen(await api("/api/units"), arg);
    else if (name === "summary") body.innerHTML = summaryScreen();
    else if (name === "log") body.innerHTML = logScreen();
    else if (name === "diplomacy") body.innerHTML = diplomacyScreen(await api("/api/diplomacy"));
    else if (name === "projects") body.innerHTML = projectsScreen(await api("/api/projects"));
    else if (name === "scores") body.innerHTML = scoresScreen(await api("/api/scores"));
    else if (name === "menu") body.innerHTML = gameMenu(await api("/api/saves"));
  } catch (err) { toast(err.message); return; }
  document.querySelector(".modal-box").classList.toggle("narrow", name === "menu");
  $("modal").classList.remove("hidden");
  wireScreen(name);
}
async function act(cmd, screen) {
  try { const r = await api("/api/command", cmd); if (r.ok === false) toast(r.error); } catch (err) { toast(err.message); }
  await refresh(true);
  if (screen) openScreen(screen);
}

// Tech timeline (Civ V style): one row from what you know now to the far future, left to right,
// not split by tree. Each card shows its projected turns and what it unlocks; tags on the unlocks
// show what they help (military, science, food...). Hover an unlock for the details.
const TIER_NAME = ["Present day (2025)", "Near future", "Next generation", "Advanced", "Far future", "Beyond"];
const TAG_LABEL = { food: "Food", production: "Production", science: "Science", gold: "Gold", beacon: "Beacon",
  military: "Military", defence: "Defence", sight: "Sight", movement: "Movement" };
function tagChips(tags) { return tags.map((t) => `<span class="tag ${t}">${TAG_LABEL[t] || pretty(t)}</span>`).join(""); }
function infoHtml(title, info, extra = "") {
  return `<div class="tip-title">${esc(title)}</div>${info.note ? `<div class="tip-note">${esc(info.note)}</div>` : ""}
    <ul>${info.lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>${extra}${info.tags.length ? `<div>${tagChips(info.tags)}</div>` : ""}`;
}
// The tech tree: two starter branches on the left, each tech opening two more to the right
// (2, 4, 8, 16...). Lines join each tech to the one it needs. Present-day tech sits in its own
// column. Each card shows turns at the current science rate and what it unlocks (hover).
function techCard(t, d) {
  const tags = [...new Set([...(t.tree === "beacon" ? ["beacon"] : []), ...(t.effects ? t.effects.tags : []), ...t.unlocks.flatMap((u) => u.tags)])];
  const when = t.status === "known" ? "Known" : t.status === "researching" ? `Researching · ${t.turns ?? "–"} turns (${d.progress}/${t.cost})`
    : t.turns != null ? `${t.turns} turns · ${t.cost} science` : `${t.cost} science`;
  const un = t.unlocks.map((u) => `<span class="unlock" data-tip="${esc(infoHtml(pretty(u.item.split(":")[1]), u, `<div class="tip-kind">${pretty(u.item.split(":")[0])}</div>`))}">${esc(pretty(u.item.split(":")[1]))}</span>`).join("");
  return `<div class="tech ${t.status}" data-tech="${t.id}" data-tip="${esc(`<div class="tip-title">${esc(pretty(t.id))}</div><div class="tip-note">${esc(t.note)}</div>`)}">
    <div class="name">${esc(pretty(t.id))}</div><div class="meta when">${when}</div>
    ${t.effects && t.effects.lines.length ? `<div class="effects">${t.effects.lines.map((l) => `<div>• ${esc(l)}</div>`).join("")}</div>` : ""}
    ${un ? `<div class="unlocks">${un}</div>` : ""}<div class="tags">${tagChips(tags)}</div></div>`;
}
function techScreen(d) {
  const tree = d.techs.filter((t) => t.tree !== "alien" && t.tier > 0);
  const byId = Object.fromEntries(tree.map((t) => [t.id, t]));
  const kids = {};
  for (const t of tree) for (const p of t.prereqs) if (byId[p]) (kids[p] = kids[p] || []).push(t.id);
  const roots = tree.filter((t) => !t.prereqs.some((p) => byId[p])).map((t) => t.id);
  const span = {};
  const height = (id) => span[id] ?? (span[id] = Math.max(1, (kids[id] || []).reduce((a, k) => a + height(k), 0)));
  const COLW = 250, ROWH = 124, CARDH = 112, LEFT = 230;
  const pos = {};
  let row = 0;
  const place = (id, top) => {
    let y = top;
    for (const k of kids[id] || []) { place(k, y); y += height(k); }
    pos[id] = { x: LEFT + (byId[id].tier - 1) * COLW, y: (top + height(id) / 2 - 0.5) * ROWH };
  };
  for (const r of roots) { place(r, row); row += height(r); }
  const H = row * ROWH, maxTier = Math.max(...tree.map((t) => t.tier)), W = LEFT + maxTier * COLW;
  const lines = tree.flatMap((t) => t.prereqs.filter((p) => pos[p]).map((p) => {
    const a = pos[p], b = pos[t.id], x1 = a.x + COLW - 30, y1 = a.y + CARDH / 2, x2 = b.x, y2 = b.y + CARDH / 2;
    return `<path d="M${x1},${y1} C${x1 + 20},${y1} ${x2 - 20},${y2} ${x2},${y2}" class="link ${t.status}"/>`;
  })).join("");
  const cards = tree.map((t) => `<div class="node" style="left:${pos[t.id].x}px;top:${pos[t.id].y}px;width:${COLW - 30}px">${techCard(t, d)}</div>`).join("");
  const heads = Array.from({ length: maxTier }, (_, k) => `<div class="levelhead" style="left:${LEFT + k * COLW}px">Level ${k + 1}</div>`).join("");
  const present = d.techs.filter((t) => t.tree !== "alien" && t.tier === 0).map((t) => techCard(t, d)).join("");
  const alien = d.techs.filter((t) => t.tree === "alien");
  return `<h2>Technology</h2><p class="muted">Two starter branches on the left; each tech opens two more. Click a gold-edged tech to research it; hover an unlock for what it does. Science: +${S.view.economy.science_per_turn} per turn.</p>
    <div class="techtree"><div class="treecanvas" style="width:${W}px;height:${H + 30}px">
      <div class="present" style="height:${H}px"><div class="levelhead static">Present day (known)</div>${present}
        ${alien.length ? `<div class="levelhead static" style="margin-top:14px">Alien (espionage only)</div>${alien.map((t) => techCard(t, d)).join("")}` : ""}</div>
      ${heads}<svg class="links" width="${W}" height="${H + 30}">${lines}</svg>${cards}</div></div>`;
}
function scoreChips(scores) { return Object.entries(scores).map(([d, v]) => `<span class="chip ${d}">${pretty(d)} +${v}%</span>`).join(""); }
// The council (designer 2026-11-14, after a reference layout): three general seats on top, the
// two seats of each domain in a row below, and every possible member (alien recruits and grown
// citizens) underneath. Click a member, then a seat; click x to free a seat.
function memberCard(m, picked) {
  const chips = Object.entries(m.scores).map(([k, v]) => `<span class="tag ${k}">${v} ${k}</span>`).join("");
  return `<div class="member ${m.kind}${picked ? " picked" : ""}" data-member="${m.kind}:${m.id}">
    <div class="avatar">${m.kind === "recruit" ? "◈" : "●"}</div><div class="mname">${esc(m.name)}${m.seats.length && !m.pinned ? ' <span class="autotag" title="Placed by Auto: it gives way to recruits; click it and a seat to fix it here">auto</span>' : ""}</div>
    <div class="muted small">${esc(m.where)}</div><div>${chips}</div>
    ${m.traits.length ? `<div class="small">${m.traits.map((t) => `<span class="trait">${esc(pretty(t))}</span>`).join(" ")}</div>` : ""}</div>`;
}
function councilScreen(d) {
  const pick = S.councilPick || "";
  const slot = (seat, k) => {
    const m = d.board[seat][k];
    if (m) return `<div class="seat filled" data-seat-slot="${seat}">${memberCard(m, pick === `${m.kind}:${m.id}`)}
      <button class="small unseat" data-free="${m.kind}:${m.id}:${seat}" title="Free this seat">×</button></div>`;
    return `<div class="seat empty" data-seat-slot="${seat}"><div class="muted">${pick ? "Seat here" : "Empty"}</div></div>`;
  };
  const general = Array.from({ length: d.general_seats }, (_, k) => slot("general", k)).join("");
  const domains = d.domains.map((x) => `<div class="domaincol"><div class="seathead tag ${x}">${pretty(x)}${d.bonus[x] ? ` +${d.bonus[x]}%` : ""}</div>
      ${Array.from({ length: d.seats_per_domain }, (_, k) => slot(x, k)).join("")}</div>`).join("");
  // members already on a seat are shown on the board only (designer: so you can see who is assigned)
  const pool = d.members.filter((m) => !m.seats.length || pick === `${m.kind}:${m.id}`).map((m) => memberCard(m, pick === `${m.kind}:${m.id}`)).join("");
  const others = S.view.players.filter((p) => p.id !== S.view.me);
  const gifts = d.recruits.map((r) => `<div class="row small">${esc(r.name)} · ${r.lifespan ? `age ${r.age}/${r.lifespan}` : "immortal"}${r.betrayal ? ` · <span class="bad">betrayal ${r.betrayal / 10}%/turn</span>` : ""}
      <select data-giftto="${r.id}">${others.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select><button class="small" data-gift="${r.id}">Gift</button></div>`).join("");
  const offers = d.offers.map((o) => `<div class="row">${pretty(o.from_player)} offers recruit #${o.recruit} for ${o.price} gold
      <button class="small" data-accept-offer="${o.id}">Accept</button><button class="small" data-decline-offer="${o.id}">Decline</button></div>`).join("");
  return `<h2>The Council</h2>
    <p class="muted">General seats add all of a member's stats; a domain seat adds only that domain. Alien recruits give percentages to every city; a citizen gives its stats to its own city. ${pick ? "<b>Now click a seat.</b>" : "Click a member, then a seat."}</p>
    <div class="seatrow general">${general}</div>
    <div class="seatrow domains">${domains}</div>
    ${offers ? `<h3>Offers</h3>${offers}` : ""}
    <h3>Unassigned members</h3><div class="pool">${pool || '<p class="muted">Everyone is on a seat. Free a seat (×) to move someone.</p>'}</div>
    ${gifts ? `<h3>Recruits: gifts</h3>${gifts}` : ""}`;
}
// After a council change, say what it did to the per-turn totals.
function perTurn() {
  const e = S.view.economy, b = e.breakdown;
  return { gold: e.gold_per_turn, science: e.science_per_turn, beacon: b ? b.beacon.sources.reduce((a, [, v]) => a + v, 0) : 0 };
}
async function councilChange(fn) {
  const before = perTurn();
  await fn();
  const after = perTurn();
  const diff = Object.keys(after).filter((k) => after[k] !== before[k]).map((k) => `${pretty(k)} ${after[k] - before[k] > 0 ? "+" : ""}${after[k] - before[k]} per turn`);
  toast(diff.length ? `Council change: ${diff.join(", ")}` : "Council change: no change to gold, science or beacon (food and production show in each city).");
}
async function seatMember(key, seat, d) { return councilChange(() => seatMember0(key, seat, d)); }
async function freeSeat(key, d) { return councilChange(() => freeSeat0(key, d)); }
async function seatMember0(key, seat, d) {
  const [kind, id] = key.split(":"); const n = Number(id);
  if (kind === "citizen") return act({ kind: "set_citizen_job", citizen: n, job: `council:${seat}` }, "council");
  const m = d.members.find((x) => x.kind === "recruit" && x.id === n);
  const seats = seat === "general" ? ["general"] : [...new Set([...m.seats.filter((s) => s !== "general"), seat])];
  return act({ kind: "seat_recruit", recruit: n, seats }, "council");
}
async function freeSeat0(key, d) {
  const [kind, id, seat] = key.split(":"); const n = Number(id);
  if (kind === "citizen") return act({ kind: "set_citizen_job", citizen: n, job: "auto" }, "council");
  const m = d.members.find((x) => x.kind === "recruit" && x.id === n);
  const rest = m.seats.filter((s) => s !== seat);
  return act(rest.length ? { kind: "seat_recruit", recruit: n, seats: rest } : { kind: "unseat_recruit", recruit: n }, "council");
}
// Population: every city's citizens and what they do (or one city's, from its panel).
function populationScreen(d, only) {
  const cities = d.cities.filter((c) => only == null || c.id === only);
  return `<h2>Population</h2>
    <p class="muted">Children grow up faster with more spare food. Grown citizens work one improved tile (half their stats there) or sit on the council (full stats to their city). Pick a job for each, or leave it on Auto.</p>
    ${only != null ? '<p><button class="small" id="pop-all">Show all cities</button></p>' : ""}
    ${cities.map((c) => `<div class="popcity"><h3>${esc(c.name)} · population ${c.pop}</h3>
      <div class="muted small">${c.on_tiles} on tiles · ${c.on_council} on the council · ${c.children} growing up · ${c.idle ? `<span class="bad">${c.idle} idle</span>` : "0 idle"} · food ${c.surplus_food >= 0 ? "+" : ""}${c.surplus_food}/turn, next citizen at ${c.growth[0]}/${c.growth[1]}</div>
      <div class="citizens wide">${c.citizens.map((p) => citizenRow(p, c)).join("")}</div></div>`).join("")}`;
}
function termsText(t) {
  const parts = [];
  if (t.gold) parts.push(`${t.gold} gold`);
  if (t.gold_per_turn) parts.push(`${t.gold_per_turn} gold/turn`);
  for (const [r, n] of Object.entries(t.resources || {})) parts.push(`${n} ${pretty(r)}`);
  for (const x of t.techs || []) parts.push(pretty(x));
  if ((t.recruits || []).length) parts.push(`${t.recruits.length} recruit(s)`);
  if ((t.units || []).length) parts.push(`${t.units.length} unit(s)`);
  if (t.alliance) parts.push("alliance");
  return parts.join(", ") || "nothing";
}
function diplomacyScreen(d) {
  const unmet = d.players.filter((p) => !p.met);
  const rows = d.players.filter((p) => p.met).map((p) => `<tr>
      <td><b style="color:${OWNER[p.id]}">${esc(p.name)}</b><br><span class="muted">${pretty(p.character || "")}</span></td>
      <td>${p.cities} cities${p.fallen ? ' · <span class="bad">fallen</span>' : ""}${p.allied ? ' · <span class="good">allied</span>' : ""}</td>
      <td><div class="actions">
        <input type="number" min="1" value="50" style="width:70px" data-goldfor="${p.id}"><button class="small" data-aid="${p.id}">Send gold</button>
        ${d.giftable_techs[p.id].length ? `<select data-techfor="${p.id}">${d.giftable_techs[p.id].map((t) => `<option value="${t}">${pretty(t)}</option>`).join("")}</select><button class="small" data-giftech="${p.id}">Give tech</button>` : ""}
        ${!p.allied ? `<button class="small" data-ally="${p.id}" ${d.has_alliance_tech ? "" : `disabled title="Needs ${pretty(d.alliance_tech)} on both sides"`}>Propose alliance</button>` : ""}
      </div></td></tr>`).join("");
  const incoming = d.incoming.map((x) => `<div class="row">${pretty(x.proposer)} gives <b>${termsText(x.give)}</b> for <b>${termsText(x.take)}</b>
      <button class="small" data-accept-deal="${x.id}">Accept</button><button class="small" data-decline-deal="${x.id}">Decline</button></div>`).join("");
  const active = d.active.map((x) => `<div class="row muted">${pretty(x.proposer)} ↔ ${pretty(x.receiver)}: ${termsText(x.give)} for ${termsText(x.take)} (until turn ${x.ends_turn})</div>`).join("");
  return `<h2>Diplomacy</h2>
    ${incoming ? `<h3>Proposals to you</h3>${incoming}` : ""}
    ${rows ? `<table><tr><th>Continent</th><th>Status</th><th>Actions</th></tr>${rows}</table>` : '<p>You have not met any other continent yet.</p>'}
    ${unmet.length ? `<h3>Not yet met</h3><p class="muted">${unmet.map((p) => esc(p.name)).join(", ")}: somewhere across the ocean, and the map is different every game. Build a <b>scout boat</b> in a coastal city and sail out to find them; once you sight their land or units you can trade, ally, give aid and ship troops.</p>` : ""}
    ${active ? `<h3>Active deals</h3>${active}` : ""}
    <p class="muted">Nobody fights anybody: gifts count toward your MVP score. Techs and recruits travel by sea from your ports.</p>`;
}
function projectsScreen(d) {
  const b = d.barrage;
  const bar = (p, c) => `<div class="bar"><i style="width:${Math.min(100, Math.round(100 * p / c))}%"></i></div>`;
  const myCities = S.view.my_cities.map((c) => `<option value="${c.id}">${esc(cityName(c.id))}</option>`).join("");
  const barrage = b
    ? `<div>${b.done ? '<b class="good">Fired. The mothership is destroyed.</b>' : `Host: <b>${esc(d.host_name)}</b> · ${b.progress}/${b.cost} · started turn ${b.started_turn} (fires no earlier than turn ${b.started_turn + d.barrage_min_turns})`}</div>
       ${bar(b.progress, b.cost)}
       <div class="muted">Contributions: ${Object.entries(b.contributions).map(([p, v]) => `${pretty(p)} ${v}`).join(", ") || "none"}</div>
       ${b.done ? "" : `<div class="actions"><input type="number" min="1" value="100" style="width:80px" id="fundb"><button class="small" data-fund="${b.id}" data-input="fundb">Fund with gold</button>
         <span class="muted">or set a city's production to the Barrage project</span></div>`}`
    : d.has_barrage_tech
      ? `<div class="actions">Host city <select id="hostcity">${myCities}</select><button class="primary" id="startbarrage">Start the world barrage</button></div>`
      : `<p class="muted">Research ${pretty(d.barrage_tech)} to start it. Researching it stops alien reinforcements.</p>`;
  const ops = d.espionage.map((p) => `<div class="card"><b>${pretty(p.mode)} operation</b> by ${pretty(p.starter)} · ${p.progress}/${p.cost}
      ${bar(p.progress, p.cost)}
      ${p.offered.length ? (p.chooser === S.view.me
        ? `<div class="actions">${p.offered.map((t) => `<button class="small" data-choose="${p.id}" data-tech="${t}">${pretty(t)}</button>`).join("")}</div>`
        : `<div class="muted">${pretty(p.chooser)} is choosing.</div>`)
        : `<div class="actions"><input type="number" min="1" value="100" style="width:80px" id="fund${p.id}"><button class="small" data-fund="${p.id}" data-input="fund${p.id}">Fund</button></div>`}</div>`).join("");
  return `<h2>Projects</h2>
    <div class="row">Mothership: ${d.mothership_alive ? '<b class="bad">active</b>' : '<b class="good">destroyed</b>'} · reinforcements ${d.reinforcements_stopped ? '<b class="good">stopped</b>' : '<b class="bad">landing</b>'} · alien cities known: ${d.alien_cities_known}</div>
    <h3>World barrage</h3>${barrage}
    <h3>Alien espionage</h3>
    ${d.my_operation ? "" : `<div class="actions"><button data-espionage="shared">Open a shared operation</button><button data-espionage="solo">Open a solo operation</button><span class="muted">${d.espionage_cost} gold each</span></div>`}
    <div class="cards">${ops || '<p class="muted">No operations.</p>'}</div>`;
}
function scoresScreen(d) {
  const rows = d.ranking.map((r, k) => `<tr><td>${k + 1}</td><td><b style="color:${OWNER[r.player]}">${esc(d.names[r.player])}</b>${r.player === S.view.me ? " (you)" : ""}</td>
      <td><b>${r.total}</b></td><td class="muted">${r.lines.map((l) => `${pretty(l.entry)} ${l.raw} → ${l.points}`).join(" · ")}</td></tr>`).join("");
  const outcome = d.outcome ? `<p class="title">${d.outcome === "victory" ? "Victory! Earth is free." : "Defeat. Every continent has fallen."} (turn ${d.outcome_turn})</p>` : "";
  return `<h2>MVP standings</h2>${outcome}<table><tr><th>#</th><th>Continent</th><th>Score</th><th>Lines</th></tr>${rows}</table>`;
}
function savedAgo(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}
function saveRows(saves) {
  if (!saves.length) return '<p class="muted" style="padding:10px">No saved games yet.</p>';
  return saves.map((m) => `<div class="save-row">
      <b>${esc(m.name === "autosave" ? "Autosave" : m.name)}</b>
      <span>${esc(m.player_name || "")}</span>
      <span class="opt">${m.turn != null ? `Turn ${m.turn} · ${m.year}` : ""}</span>
      <span class="opt muted">${savedAgo(m.saved_at)}</span>
      <button class="small" data-loadsave="${esc(m.name)}">Load</button></div>`).join("");
}
function gameMenu(saves) {
  return `<h2>Menu</h2>
    <div class="menu-stack">
      <button class="menu-btn primary" id="m-resume">Resume</button>
      <div class="row"><input id="savename" value="turn${S.view.turn}" style="flex:1"><button id="m-save">Save game</button></div>
      <h3>Load game</h3>
      <div class="save-list">${saveRows(saves)}</div>
      <label class="row"><input type="checkbox" id="m-advice" ${window.Advisors && !Advisors.isOff() ? "checked" : ""}> Show advisor tips</label>
      <button class="menu-btn" id="m-title">Main menu</button>
    </div>
    <p class="muted">Enter: next turn · Space: next unit · F: fortify · S: skip · T/C/D/P: screens · Esc: menu · drag or arrows: pan · wheel: zoom.</p>`;
}

function wireScreen(name) {
  const body = $("modal-body");
  const on = (sel, fn) => body.querySelectorAll(sel).forEach((el) => el.onclick = () => fn(el));
  if (name === "techs") on(".tech.available", (el) => act({ kind: "set_research", tech: el.dataset.tech }, null).then(closeModal));
  if (name === "cities") {
    body.querySelectorAll("[data-gocity]").forEach((el) => el.onclick = () => { closeModal(); selectCity(Number(el.dataset.gocity), true); });
    body.querySelectorAll("[data-sort]").forEach((el) => el.onclick = () => { S.citySort = el.dataset.sort; openScreen("cities"); });
  }
  if (name === "units") {
    body.querySelectorAll("[data-gounit]").forEach((el) => el.onclick = () => {
      closeModal(); const id = Number(el.dataset.gounit), tile = Number(el.dataset.tile);
      const u = S.view.units.find((x) => x.id === id);
      if (u && S.view.unit_types[u.type]?.fixed) { const c = S.citiesByTile.get(tile); if (c) return selectCity(c.id, true); }
      centerOnTile(tile); selectUnit(id);
    });
    body.querySelectorAll("[data-ufilter]").forEach((el) => el.onclick = () => openScreen("units", el.dataset.ufilter));
  }
  if (name === "summary" || name === "log") {
    body.querySelectorAll("[data-ev]").forEach((el) => el.onclick = () => { closeModal(); goToEvent(S.evIndex[Number(el.dataset.ev)]); });
    if ($("sum-off")) $("sum-off").onchange = (e) => { try { localStorage.setItem("beacon.summary.off", e.target.checked ? "1" : "0"); } catch (err) { /* ignore */ } };
    if ($("sum-log")) $("sum-log").onclick = () => openScreen("log");
  }
  if (name === "population") {
    body.querySelectorAll("select[data-citizen]").forEach((el) => el.onchange = () => act({ kind: "set_citizen_job", citizen: Number(el.dataset.citizen), job: el.value }, null).then(() => openScreen("population", S.screenArg)));
    if ($("pop-all")) $("pop-all").onclick = () => openScreen("population");
  }
  if (name === "council") {
    const d = S.councilData;
    body.querySelectorAll("[data-member]").forEach((el) => el.onclick = (ev) => {
      ev.stopPropagation();
      S.councilPick = S.councilPick === el.dataset.member ? null : el.dataset.member;
      body.innerHTML = councilScreen(d); wireScreen("council");
    });
    body.querySelectorAll("[data-seat-slot]").forEach((el) => el.onclick = () => {
      if (!S.councilPick) return;
      const key = S.councilPick; S.councilPick = null;
      seatMember(key, el.dataset.seatSlot, d);
    });
    on("[data-free]", (el) => { S.councilPick = null; freeSeat(el.dataset.free, d); });
    on("[data-gift]", (el) => act({ kind: "offer_recruit", recruit: Number(el.dataset.gift), to_player: body.querySelector(`[data-giftto="${el.dataset.gift}"]`).value, price: 0 }, "council"));
    on("[data-accept-offer]", (el) => act({ kind: "accept_offer", offer: Number(el.dataset.acceptOffer) }, "council"));
    on("[data-decline-offer]", (el) => act({ kind: "decline_offer", offer: Number(el.dataset.declineOffer) }, "council"));
  }
  if (name === "diplomacy") {
    const deal = (to, give, take) => ({ kind: "propose_deal", to_player: to, give, take, duration: 10 });
    on("[data-aid]", (el) => act(deal(el.dataset.aid, { gold: Number(body.querySelector(`[data-goldfor="${el.dataset.aid}"]`).value) }, {}), "diplomacy"));
    on("[data-giftech]", (el) => act(deal(el.dataset.giftech, { techs: [body.querySelector(`[data-techfor="${el.dataset.giftech}"]`).value] }, {}), "diplomacy"));
    on("[data-ally]", (el) => act(deal(el.dataset.ally, { alliance: true }, { alliance: true }), "diplomacy"));
    on("[data-accept-deal]", (el) => act({ kind: "accept_deal", deal: Number(el.dataset.acceptDeal) }, "diplomacy"));
    on("[data-decline-deal]", (el) => act({ kind: "decline_deal", deal: Number(el.dataset.declineDeal) }, "diplomacy"));
  }
  if (name === "projects") {
    if ($("startbarrage")) $("startbarrage").onclick = () => act({ kind: "start_barrage", city: Number($("hostcity").value) }, "projects");
    on("[data-fund]", (el) => act({ kind: "fund_project", project: Number(el.dataset.fund), gold: Number($(el.dataset.input).value) }, "projects"));
    on("[data-espionage]", (el) => act({ kind: "start_espionage", mode: el.dataset.espionage }, "projects"));
    on("[data-choose]", (el) => act({ kind: "choose_espionage_tech", project: Number(el.dataset.choose), tech: el.dataset.tech }, "projects"));
  }
  if (name === "menu") {
    $("m-resume").onclick = closeModal;
    $("m-save").onclick = async () => { try { await api("/api/save", { name: $("savename").value }); toast("Game saved."); openScreen("menu"); } catch (err) { toast(err.message); } };
    $("m-title").onclick = () => { closeModal(); showTitle(); };
    $("m-advice").onchange = (e) => { if (window.Advisors) { if (e.target.checked) Advisors.reset(); else Advisors.setOff(true); } };
    on("[data-loadsave]", async (el) => { try { await api("/api/load", { name: el.dataset.loadsave }); closeModal(); await enterGame(); } catch (err) { toast(err.message); } });
  }
}

// =============================================================================================
// title screen

const tcan = $("title-bg");
const tctx = tcan.getContext("2d");
const STARS = Array.from({ length: 220 }, (_, k) => { const r = rng(k + 5); return [r(), r() * 0.75, r() * 1.4 + 0.3, r() * 6.28]; });
function drawTitle(t) {
  const W = tcan.clientWidth, H = tcan.clientHeight;
  if (tcan.width !== W || tcan.height !== H) { tcan.width = W; tcan.height = H; }
  const sky = tctx.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, "#050811"); sky.addColorStop(0.6, "#0c1424"); sky.addColorStop(1, "#1a2433");
  tctx.fillStyle = sky; tctx.fillRect(0, 0, W, H);
  for (const [x, y, s, ph] of STARS) {
    tctx.globalAlpha = 0.45 + 0.45 * Math.sin(t / 900 + ph);
    tctx.fillStyle = "#e9eef8"; tctx.fillRect(x * W, y * H, s, s);
  }
  tctx.globalAlpha = 1;
  const cx = W * 0.5, cy = H * 1.62, r = H * 1.05;
  const glow = tctx.createRadialGradient(cx, cy, r * 0.96, cx, cy, r * 1.08);
  glow.addColorStop(0, "rgba(110,180,230,0.55)"); glow.addColorStop(1, "rgba(110,180,230,0)");
  tctx.fillStyle = glow; tctx.beginPath(); tctx.arc(cx, cy, r * 1.08, 0, Math.PI * 2); tctx.fill();
  const earth = tctx.createRadialGradient(cx - r * 0.2, cy - r * 0.9, r * 0.1, cx, cy, r);
  earth.addColorStop(0, "#3d6d8f"); earth.addColorStop(0.5, "#1f3c58"); earth.addColorStop(1, "#0b1726");
  tctx.fillStyle = earth; tctx.beginPath(); tctx.arc(cx, cy, r, 0, Math.PI * 2); tctx.fill();
  const mx = W * 0.5 + Math.sin(t / 4000) * W * 0.03, my = H * 0.2 + Math.sin(t / 2600) * 6, mw = Math.min(W * 0.32, 420);
  tctx.fillStyle = "rgba(160,70,200,0.18)"; tctx.beginPath(); tctx.ellipse(mx, my + mw * 0.06, mw * 0.55, mw * 0.08, 0, 0, Math.PI * 2); tctx.fill();
  tctx.fillStyle = "#151020"; tctx.beginPath();
  tctx.moveTo(mx - mw / 2, my); tctx.lineTo(mx - mw * 0.32, my - mw * 0.06); tctx.lineTo(mx + mw * 0.32, my - mw * 0.06); tctx.lineTo(mx + mw / 2, my);
  tctx.lineTo(mx + mw * 0.3, my + mw * 0.05); tctx.lineTo(mx - mw * 0.3, my + mw * 0.05); tctx.closePath(); tctx.fill();
  tctx.strokeStyle = "rgba(200,140,240,0.5)"; tctx.lineWidth = 1; tctx.stroke();
  for (let k = -3; k <= 3; k++) { tctx.fillStyle = `rgba(190,110,240,${0.5 + 0.4 * Math.sin(t / 300 + k)})`; tctx.beginPath(); tctx.arc(mx + k * mw * 0.08, my + mw * 0.03, 2.2, 0, Math.PI * 2); tctx.fill(); }
  const beam = tctx.createLinearGradient(0, H * 0.55, 0, H);
  beam.addColorStop(0, "rgba(242,211,138,0)"); beam.addColorStop(1, "rgba(242,211,138,0.22)");
  tctx.fillStyle = beam; tctx.beginPath(); tctx.moveTo(W * 0.5 - 4, H * 0.55); tctx.lineTo(W * 0.5 + 4, H * 0.55); tctx.lineTo(W * 0.5 + 60, H); tctx.lineTo(W * 0.5 - 60, H); tctx.fill();
  const puff = puffSprite();
  for (let k = 0; k < 14; k++) {
    const h1 = hash(k, 3), size = H * (0.35 + h1 * 0.3);
    const x = ((h1 * W * 1.5 + t * 0.012 * (0.5 + h1)) % (W * 1.4)) - W * 0.2;
    tctx.globalAlpha = 0.35; tctx.drawImage(puff, x - size / 2, H * (0.72 + hash(k, 4) * 0.25) - size / 2, size, size);
  }
  tctx.globalAlpha = 1;
}
function titleLoop(t) { if (!S.inGame) { drawTitle(t); requestAnimationFrame(titleLoop); } }

function showPanel(id) { for (const p of ["title-main", "title-new", "title-load", "title-howto"]) $(p).classList.toggle("hidden", p !== id); }
async function showTitle() {
  S.inGame = false;
  $("game").classList.add("hidden");
  $("title").classList.remove("hidden");
  showPanel("title-main");
  requestAnimationFrame(titleLoop);
  try {
    const st = await api("/api/status");
    const btn = $("btn-continue");
    btn.innerHTML = `Continue <span style="font-size:13px;opacity:.75">· ${esc(st.player_name)}, turn ${st.turn}</span>`;
    btn.classList.toggle("hidden", !!st.outcome);
  } catch (err) { $("btn-continue").classList.add("hidden"); }
}
let chosenContinent = null;
async function showNewGame() {
  const cs = await api("/api/continents");
  chosenContinent = chosenContinent || cs[2].id;
  $("continent-cards").innerHTML = cs.map((c) => `<div class="ccard ${c.id === chosenContinent ? "selected" : ""}" data-c="${c.id}" style="--c:${OWNER[c.id]}">
      <div class="name">${esc(c.name)}</div><div class="cap">Capital: ${esc(c.capital)}</div><div class="note">${esc(c.note)}</div></div>`).join("");
  document.querySelectorAll(".ccard").forEach((el) => el.onclick = () => { chosenContinent = el.dataset.c; document.querySelectorAll(".ccard").forEach((x) => x.classList.toggle("selected", x === el)); });
  if (!$("new-seed").value) $("new-seed").value = 1 + Math.floor(Math.random() * 99999);
  showPanel("title-new");
}
async function showLoad() {
  const saves = await api("/api/saves");
  $("save-list").innerHTML = saveRows(saves);
  $("save-list").querySelectorAll("[data-loadsave]").forEach((el) => el.onclick = async () => {
    try { await api("/api/load", { name: el.dataset.loadsave }); await enterGame(); } catch (err) { toast(err.message); }
  });
  showPanel("title-load");
}
$("btn-continue").onclick = () => enterGame();
$("btn-new").onclick = () => showNewGame();
$("btn-load").onclick = () => showLoad();
$("btn-howto").onclick = () => showPanel("title-howto");
$("btn-random").onclick = () => { $("new-seed").value = 1 + Math.floor(Math.random() * 99999); };
document.querySelectorAll(".title-panel .back").forEach((b) => b.onclick = () => showPanel("title-main"));
$("btn-start").onclick = async () => {
  $("btn-start").textContent = "Generating the world…";
  try { await api("/api/new", { seed: Number($("new-seed").value) || 1, human: chosenContinent }); S.shownOutcome = false; await enterGame(); }
  catch (err) { toast(err.message); }
  $("btn-start").textContent = "Begin";
};

async function enterGame() {
  $("title").classList.add("hidden");
  $("game").classList.remove("hidden");
  S.inGame = true;
  S.view = null; S.selected = null; S.options = null; S.city = null;
  resize();
  await refresh(false);
  const capital = Object.values(S.view.cities).find((c) => c.owner === S.view.me && c.is_capital);
  S.cam.zoom = 1.6;
  if (capital) centerOnTile(capital.tile);
  splash(`${S.view.players.find((p) => p.id === S.view.me).name} · ${S.view.year}`);
}

// =============================================================================================
// start

window.addEventListener("resize", () => { if (S.inGame) resize(); });
// the map is drawn on a canvas, so redraw once the web fonts have arrived
if (document.fonts) document.fonts.ready.then(() => { S.dirty = true; });
requestAnimationFrame(frame);
showTitle();

function statText(stats) { return Object.entries(stats).map(([k, v]) => `+${v} ${k}`).join(", "); }
// bonuses in hundredths (citizens' half stats): 150 -> "+1.5 production"
function hundredthsText(b) {
  return Object.entries(b).filter(([, v]) => v).map(([k, v]) => `+${(v / 100).toFixed(2).replace(/\.?0+$/, "")} ${k}`).join(", ");
}

// One citizen in the city panel: stats, trait, growing up, and a job picker (Auto, Council, or one
// of the city's improved tiles).
function citizenRow(p, d) {
  const stats = Object.entries(p.stats).map(([k, v]) => `<span class="tag ${k}">+${v} ${k}</span>`).join("");
  const traits = p.traits.map((t) => `<span class="trait" title="${esc(t.note)}">${esc(pretty(t.id))}</span>`).join("");
  let where;
  if (!p.adult) where = `<span class="muted">child · grows up in ${p.turns_to_grow} turns (${p.growth}/${p.growth_needed})</span>`;
  else if (p.tile != null) where = `works a ${esc(pretty(p.improvement))}: ${hundredthsText(p.bonus) || "no extra"} (half its stats)`;
  else if (p.seats.length) where = `on the council (${pretty(p.seats[0])} seat): ${hundredthsText(p.bonus)}${p.military ? `, +${p.military} city strength` : ""}`;
  else where = '<span class="bad">idle: no improved tile or council seat free</span>';
  const tiles = d.workable.map((w) => `<option value="tile:${w.tile}" ${p.job === `tile:${w.tile}` ? "selected" : ""}>Tile: ${esc(pretty(w.improvement))} (${statText(Object.fromEntries(Object.entries(w.yields).filter(([, v]) => v)))})</option>`).join("");
  const pick = p.adult ? `<select data-citizen="${p.id}"><option value="auto" ${p.job === "auto" ? "selected" : ""}>Auto</option><option value="${p.job.startsWith("council") ? esc(p.job) : "council"}" ${p.job.startsWith("council") ? "selected" : ""}>Council${p.job.startsWith("council:") ? ` (${pretty(p.job.slice(8))} seat)` : ""}</option>${tiles}</select>` : "";
  return `<div class="citizen"><div class="row"><b>${esc(p.name)}</b> ${traits} ${pick}</div><div>${stats}</div><div class="muted small">${where}</div></div>`;
}

function promoName(id) {
  return { attack_10: "+10% attack", defence_10: "+10% defence", dig_in: "Dig in (+20% defence)", field_medic: "Field medic (+10 heal)",
    blitz: "Blitz (+1 move)", breakthrough: "Breakthrough (+20% vs infantry)", siege_master: "Siege master (+25% vs cities)",
    barrage: "Barrage (+15% attack)", sea_legs: "Sea legs (+1 move)", gold_upgrade: "Upgraded" }[id] || pretty(id);
}

// Hexes of units the selected unit can merge with: moving there merges them (no button).
function mergeTiles() {
  if (!S.options) return [];
  return S.options.merges.map((id) => (S.view.units.find((x) => x.id === id) || {}).tile).filter((t) => t != null);
}

// Hover card for a top-bar number: what produces it, by kind of source and by city.
function breakdownHtml(y, e) {
  const b = e.breakdown && e.breakdown[y];
  if (!b) return "";
  const total = y === "gold" ? e.gold_per_turn : y === "science" ? e.science_per_turn : null;
  const rows = b.sources.map(([k, v]) => `<li>${esc(k)}: <b>${v >= 0 ? "+" : ""}${v}</b></li>`).join("");
  const costs = (b.costs || []).filter(([, v]) => v).map(([k, v]) => `<li>${esc(k)}: <b class="bad">${v}</b></li>`).join("");
  const cities = b.cities.map(([k, v]) => `${esc(k)} +${v}`).join(", ");
  return `<div class="tip-title">${pretty(y)}${total != null ? ` ${total >= 0 ? "+" : ""}${total} per turn` : " per turn"}</div>
    <ul>${rows}${costs}</ul>${cities ? `<div class="tip-kind">By city: ${cities}</div>` : ""}
    ${b.unlinked.length ? `<div class="tip-kind bad">Not connected (produce nothing): ${b.unlinked.map(esc).join(", ")}</div>` : ""}
    <div class="tip-kind">Click to open its screen.</div>`;
}

// A turret's panel: its level, HP and the gold upgrade.
function showTurretPanel(i) {
  clearSelection();
  const t = S.tilesByIndex.get(i), r = S.view.turret_rules, cost = r.costs[i];
  const str = r.strength_base + r.strength_per_level * (t.turret - 1);
  const side = $("side");
  side.innerHTML = `<div class="title">Turret</div>
    <div class="muted">Guards this ${esc(pretty(t.improvement || "tile"))}. Fires at enemies next to it at the end of every turn; aliens must destroy it before they can pillage the tile.</div>
    <div class="row">Level ${t.turret}/${r.max_level} · strength ${str} · ${t.turret_hp} HP</div>
    <div class="actions">${cost != null ? `<button class="primary" id="upturret" ${S.view.economy.gold < cost ? "disabled" : ""}>Upgrade for ${cost} gold</button>` : '<span class="muted">Top level</span>'}</div>`;
  if ($("upturret")) $("upturret").onclick = () => send({ kind: "upgrade_turret", tile: i }).then(() => showTurretPanel(i));
  side.classList.remove("hidden");
}

function drawTurret(t, sx, sy, R) {
  const x = sx + R * 0.38, y = sy + R * 0.3, s = R * 0.16;
  ctx.fillStyle = "#38424c"; ctx.fillRect(x - s, y - s * 0.4, s * 2, s * 1.2);
  ctx.fillStyle = "#5c6b78"; ctx.beginPath(); ctx.arc(x, y - s * 0.4, s * 0.7, Math.PI, 0); ctx.fill();
  ctx.strokeStyle = "#c9d4dc"; ctx.lineWidth = Math.max(1, s * 0.3); ctx.beginPath(); ctx.moveTo(x, y - s * 0.6); ctx.lineTo(x + s * 1.3, y - s * 1.2); ctx.stroke();
  ctx.fillStyle = "#f2d38a"; ctx.font = `700 ${Math.max(7, Math.round(s * 0.9))}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(t.turret), x, y + s * 0.25);
}

const YIELD_COLOR = { food: "#7cc35a", production: "#e69a5c", science: "#6cbbec", gold: "#f2d15c", beacon: "#c88df2" };
function drawCityTile(w, i, sx, sy, R) {
  const worker = S.city.citizens.find((p) => p.tile === i);
  hexPath(ctx, sx, sy, R - 2);
  ctx.fillStyle = worker ? "rgba(90,200,110,0.16)" : "rgba(242,211,138,0.12)"; ctx.fill();
  ctx.strokeStyle = worker ? "#6fdc7c" : "#f2d38a"; ctx.lineWidth = 2.4; ctx.setLineDash(worker ? [] : [R * 0.15, R * 0.1]); ctx.stroke(); ctx.setLineDash([]);
  // yield dots: one coloured disc per yield type with its amount
  const ys = Object.entries(w.yields).filter(([, v]) => v > 0);
  const r = Math.max(5, R * 0.17);
  ys.forEach(([k, v], n) => {
    const x = sx + (n - (ys.length - 1) / 2) * r * 2.2, y = sy + R * 0.5;
    ctx.fillStyle = YIELD_COLOR[k]; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#10161c"; ctx.font = `700 ${Math.round(r * 1.2)}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String(v), x, y + 0.5);
  });
  const bx = sx, by = sy - R * 0.5, br = Math.max(7, R * 0.2);
  ctx.fillStyle = worker ? "#2f8a35" : "#b8860b"; ctx.beginPath(); ctx.arc(bx, by, br, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#fff"; ctx.font = `700 ${Math.round(br * 1.3)}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(worker ? "✓" : "+", bx, by + 0.5);
  if (worker && S.cam.zoom > 0.8) { ctx.font = `600 ${Math.max(9, Math.round(R * 0.2))}px Roboto, sans-serif`; ctx.fillStyle = "#e9ffe6"; ctx.fillText(worker.name, sx, sy - R * 0.78); }
}
function toastJob() { toast("Assigned the best citizen to that tile."); }

// -- information screens (designer 2026-11-14): cities, units, turn summary, log -------------

function summaryOff() { try { return localStorage.getItem("beacon.summary.off") === "1"; } catch (e) { return false; } }
function eventTile(e) {
  if (e.tile != null) return e.tile;
  if (e.city != null && S.view.cities[e.city]) return S.view.cities[e.city].tile;
  if (e.target != null && typeof e.target === "number") return e.target;
  if (e.to != null) return e.to;
  const u = e.unit != null && S.view.units.find((x) => x.id === e.unit);
  return u ? u.tile : null;
}
function goToEvent(e) {
  const t = eventTile(e);
  if (t == null) return;
  centerOnTile(t);
  const c = S.citiesByTile.get(t);
  if (c && c.owner === S.view.me) selectCity(c.id);
  S.flash = { tile: t, until: performance.now() + 1600 }; S.dirty = true;
}
const YIELD_ICON = { food: "🌾", production: "⚙", science: "⚗", gold: "●", beacon: "◈" };
function citiesScreen(d) {
  const key = S.citySort || "name";
  const val = (c) => key === "name" ? c.name : key === "pop" ? -c.pop : -(c.yields[key] ?? 0);
  const rows = [...d.cities].sort((a, b) => (val(a) < val(b) ? -1 : val(a) > val(b) ? 1 : 0)).map((c) => {
    const notes = [!c.connected && '<span class="bad">not connected</span>', c.threatened && '<span class="bad">aliens near</span>',
      c.idle && `<span class="bad">${c.idle} idle</span>`, c.children && `${c.children} growing up`, c.hp < c.max_hp && `HP ${c.hp}/${c.max_hp}`].filter(Boolean).join(" · ");
    return `<tr class="clickable" data-gocity="${c.id}">
      <td><b>${c.capital ? "★ " : ""}${esc(c.name)}</b></td>
      <td>${c.pop}<span class="muted small">${c.grows_in != null ? ` (+1 in ${c.grows_in})` : c.food < 0 ? ' <span class="bad">starving</span>' : ""}</span></td>
      ${YIELD_KEYS.map((k) => `<td class="y-${k}"><b>${k === "food" ? (c.food >= 0 ? "+" : "") + c.food : c.yields[k]}</b></td>`).join("")}
      <td>${c.building ? `${esc(pretty(c.building.split(":")[1]))} <span class="muted">${c.turns != null ? `${c.turns}t` : ""}</span>` : '<span class="bad">nothing</span>'}</td>
      <td class="small">${notes}</td></tr>`;
  }).join("");
  const head = (k, label) => `<th class="clickable" data-sort="${k}" title="Sort">${label}${key === k ? " ▾" : ""}</th>`;
  const tot = (k) => d.cities.reduce((a, c) => a + (k === "food" ? c.food : c.yields[k]), 0);
  return `<h2>Cities</h2><p class="muted">Click a city to go to it; click a heading to sort. Food is the surplus per turn.</p>
    <table class="overview"><tr>${head("name", "City")}${head("pop", "Pop")}${YIELD_KEYS.map((k) => head(k, `${YIELD_ICON[k]} ${pretty(k)}`)).join("")}<th>Building</th><th>Notes</th></tr>${rows}
    <tr class="total"><td>Total</td><td>${d.cities.reduce((a, c) => a + c.pop, 0)}</td>${YIELD_KEYS.map((k) => `<td class="y-${k}"><b>${tot(k)}</b></td>`).join("")}<td></td><td></td></tr></table>`;
}
function unitsScreen(d, filter) {
  const f = filter || "all";
  const keep = (u) => f === "all" || (f === "military" && ["melee", "ranged"].includes(u.role)) || (f === "civilian" && ["civilian", "recon"].includes(u.role))
    || (f === "defence" && u.role === "defence") || (f === "orders" && u.doing === "needs orders") || (f === "promote" && u.due > 0) || (f === "abroad" && u.abroad);
  const list = d.units.filter(keep);
  const btn = (k, label, n) => `<button class="small ${f === k ? "primary" : ""}" data-ufilter="${k}">${label} (${n})</button>`;
  const count = (k) => d.units.filter((u) => k === "all" || (k === "military" && ["melee", "ranged"].includes(u.role)) || (k === "civilian" && ["civilian", "recon"].includes(u.role)) || (k === "defence" && u.role === "defence") || (k === "orders" && u.doing === "needs orders") || (k === "promote" && u.due > 0) || (k === "abroad" && u.abroad)).length;
  const rows = list.map((u) => `<tr class="clickable" data-gounit="${u.id}" data-tile="${u.tile}">
      <td><b>${esc(pretty(u.type))}</b>${u.count > 1 ? " ×2" : ""}${u.promotions.filter((p) => p !== "gold_upgrade").length ? ` <span class="good">${"★".repeat(Math.min(3, u.promotions.length))}</span>` : ""}</td>
      <td>${esc(u.where)}${u.abroad ? ' <span class="muted">(abroad)</span>' : ""}</td>
      <td><div class="bar small"><i style="width:${Math.round(100 * u.hp / u.max_hp)}%"></i></div><span class="small">${u.hp}/${u.max_hp}</span></td>
      <td>${u.role === "defence" ? "—" : `${u.moves}/${u.full_moves}`}</td>
      <td>${u.role === "defence" || u.role === "civilian" ? "—" : `${u.xp}${u.due ? ' <span class="good">promote!</span>' : ""}`}</td>
      <td class="${u.doing === "needs orders" ? "bad" : "muted"}">${esc(u.doing)}</td></tr>`).join("");
  return `<h2>Units</h2>
    <div class="row">${btn("all", "All", count("all"))}${btn("military", "Military", count("military"))}${btn("civilian", "Scouts & civilians", count("civilian"))}${btn("defence", "City defences", count("defence"))}${btn("orders", "Need orders", count("orders"))}${btn("promote", "Promotion due", count("promote"))}${btn("abroad", "Abroad", count("abroad"))}</div>
    <table class="overview"><tr><th>Unit</th><th>Where</th><th>HP</th><th>Moves</th><th>XP</th><th>Doing</th></tr>${rows || '<tr><td colspan="6" class="muted">None.</td></tr>'}</table>`;
}
// Group a turn's events for the summary and the log.
const SUMMARY_GROUPS = [
  ["Cities", ["citizen_born", "citizen_grew_up", "city_grew", "city_starved", "building_completed", "unit_completed", "production_stalled", "item_dropped"]],
  ["Research", ["tech_learned", "alien_tech"]],
  ["War", ["city_liberated", "city_overrun", "unit_destroyed", "civilians_captured", "pillaged", "turret_destroyed", "mothership_strike", "city_attack", "turret_fired"]],
  ["World", ["contact_made", "recruit_arrived", "recruit_betrayed", "recruit_died", "deal_accepted", "shipment_arrived", "unit_landed", "continent_fallen", "continent_revived", "barrage_fired", "reinforcements_stopped"]],
];
function eventItems(events) {
  S.evIndex = S.evIndex || [];
  return (e) => { S.evIndex.push(e); const i = S.evIndex.length - 1;
    return `<li class="${eventTile(e) != null ? "clickable" : ""}" data-ev="${i}">${esc(describeEvent(e))}</li>`; };
}
function summaryBody(events) {
  S.evIndex = [];
  const item = eventItems(events);
  const used = new Set();
  const groups = SUMMARY_GROUPS.map(([title, kinds]) => {
    const evs = events.filter((e) => kinds.includes(e.kind));
    evs.forEach((e) => used.add(e));
    if (!evs.length) return "";
    return `<div class="sumgroup"><h3>${title}</h3><ul>${evs.slice(0, 25).map(item).join("")}${evs.length > 25 ? `<li class="muted">…and ${evs.length - 25} more</li>` : ""}</ul></div>`;
  }).join("");
  const attacks = events.filter((e) => e.kind === "attack");
  const fights = attacks.length ? `<div class="sumgroup"><h3>Battles</h3><ul><li>${attacks.length} attacks this turn; ${events.filter((e) => e.kind === "unit_destroyed" && e.owner === S.view.me).length} of your units lost.</li></ul></div>` : "";
  return groups + fights || '<p class="muted">A quiet turn.</p>';
}
function summaryScreen() {
  const v = S.view;
  return `<h2>Turn ${v.turn} · ${v.year}</h2>
    <p class="muted">What happened since your last turn. Click an entry to see it on the map.</p>
    <div class="sumgrid">${summaryBody(v.events)}</div>
    <div class="row"><label><input type="checkbox" id="sum-off" ${summaryOff() ? "checked" : ""}> Don't show this at the start of each turn</label>
    <button class="small" id="sum-log">Full log</button></div>`;
}
function logScreen() {
  S.evIndex = [];
  const item = eventItems();
  const turns = [...(S.history || [])].reverse().map((h) => `<h3>Turn ${h.turn}</h3><ul>${h.events.filter((e) => e.kind !== "turn_started").map(item).join("") || '<li class="muted">Nothing.</li>'}</ul>`).join("");
  return `<h2>Log</h2><p class="muted">Events of the last turns this session (newest first). Click one to see it on the map.</p><div class="logbody">${turns}</div>`;
}
$("open-log").onclick = () => openScreen("log");
