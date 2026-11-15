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
// UI icons (visuals pass 2): small bronze medallions, each with a coloured glyph, in the manner of
// Civ's yield icons. One shared gradient set is defined once in the page (see ICON_DEFS).
const medal = (glyph, tone) => `<svg class="icon medal" viewBox="0 0 20 20"><circle cx="10" cy="10" r="9.3" fill="url(#md-${tone})" stroke="#3a2a10" stroke-width="0.8"/><circle cx="10" cy="10" r="8.1" fill="none" stroke="#f2d38a" stroke-opacity="0.55" stroke-width="0.7"/>${glyph}</svg>`;
const ICON = {
  gold: medal('<circle cx="10" cy="10" r="4.6" fill="#f6dc7a" stroke="#8a6d1c" stroke-width="0.9"/><path d="M10 7.2v5.6M8.3 8.4h2.8a1.1 1.1 0 0 1 0 2.2H9a1.1 1.1 0 0 0 0 2.2h2.8" fill="none" stroke="#7a5c12" stroke-width="0.9"/>', "gold"),
  science: medal('<path d="M8.4 4.5h3.2M9 4.8v3.6l-3.2 5.6c-.3.6.1 1.3.8 1.3h6.8c.7 0 1.1-.7.8-1.3L11 8.4V4.8" fill="#bfe6fb" stroke="#e8f6ff" stroke-width="0.9" stroke-linejoin="round"/><path d="M7 12.6h6l1 1.8H6z" fill="#3fa0d8"/>', "science"),
  beacon: medal('<circle cx="10" cy="12.2" r="1.7" fill="#f0dcff"/><path d="M7 9.6a4.2 4.2 0 0 1 6 0M5.2 7.4a6.8 6.8 0 0 1 9.6 0" fill="none" stroke="#f0dcff" stroke-width="1.2" stroke-linecap="round"/><path d="M10 12.2v3.6" stroke="#f0dcff" stroke-width="1.2"/>', "beacon"),
  turn: medal('<path d="M6.5 4.8h7M6.5 15.2h7M7.3 5c0 3.3 5.4 3.3 5.4 5S7.3 11.7 7.3 15M12.7 5c0 3.3-5.4 3.3-5.4 5s5.4 1.7 5.4 5" fill="none" stroke="#fff1cf" stroke-width="1.1"/><path d="M8.4 14.2h3.2L10 12.4z" fill="#f2d38a"/>', "turn"),
  ship: medal('<ellipse cx="10" cy="11" rx="6" ry="2.2" fill="#e9c6ff"/><path d="M6.8 10.4a3.2 3 0 0 1 6.4 0z" fill="#fff0ff"/><circle cx="7.4" cy="11.2" r=".6" fill="#7a2fb0"/><circle cx="10" cy="11.6" r=".6" fill="#7a2fb0"/><circle cx="12.6" cy="11.2" r=".6" fill="#7a2fb0"/>', "ship"),
  food: medal('<path d="M10 15.5V6.5" stroke="#fff3c4" stroke-width="1"/><path d="M10 6c-1.6.4-1.6 2.2 0 2.6 1.6-.4 1.6-2.2 0-2.6zM10 8.6c-1.8.4-1.8 2.3 0 2.7 1.8-.4 1.8-2.3 0-2.7zM10 11.2c-2 .4-2 2.3 0 2.7 2-.4 2-2.3 0-2.7z" fill="#ffe08a"/>', "food"),
  production: medal('<path d="M10 5.2l1 .2.4 1.2 1.1.6 1.2-.4.7.8-.4 1.2.6 1.1 1.2.4.2 1-.2 1-1.2.4-.6 1.1.4 1.2-.7.8-1.2-.4-1.1.6-.4 1.2-1 .2-1-.2-.4-1.2-1.1-.6-1.2.4-.7-.8.4-1.2-.6-1.1-1.2-.4-.2-1 .2-1 1.2-.4.6-1.1-.4-1.2.7-.8 1.2.4 1.1-.6.4-1.2z" fill="#ffd2a8"/><circle cx="10" cy="10" r="1.9" fill="#8a4a1c"/>', "production"),
};
const ICON_DEFS = `<svg width="0" height="0" style="position:absolute"><defs>${Object.entries({
  gold: ["#d9a93a", "#6b4a10"], science: ["#3a8fc4", "#0f3550"], beacon: ["#9a5ad6", "#33124f"], turn: ["#9a7a3a", "#3a2a10"],
  ship: ["#8a3ab0", "#2a0f3a"], food: ["#5a9a3a", "#1f3a12"], production: ["#c46a2a", "#4a1f08"],
}).map(([k, [a, b]]) => `<radialGradient id="md-${k}" cx="35%" cy="30%" r="80%"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></radialGradient>`).join("")}</defs></svg>`;
document.body.insertAdjacentHTML("afterbegin", ICON_DEFS);

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
  g.beginPath(); hexSub(g, cx, cy, r);
}
function hexSub(g, cx, cy, r) {  // add a hex to the current path (to fill many hexes in one call)
  for (let k = 0; k < 6; k++) { const [x, y] = corner(cx, cy, r, k); if (k === 0) g.moveTo(x, y); else g.lineTo(x, y); }
  g.closePath();
}

// =============================================================================================
// painted terrain (visuals pass 1): each terrain is a seamless painted texture, laid across the
// map as one continuous surface inside a blurred mask of its hexes, so terrains blend softly with
// no per-hex seams; beaches and surf soften the shores; features (forests, jungle, hills,
// mountains, marsh) are sprites that spill over hex edges.

const PAINT = {
  grassland: { base: "#5c8c38", blobs: ["#4b7a2d", "#6f9f45", "#3e6826", "#7fae52"], fleck: "rgba(214,232,120,0.35)" },
  plains: { base: "#a89a4c", blobs: ["#b9aa5b", "#958a40", "#c6b86d", "#8c8a46"], fleck: "rgba(255,240,170,0.35)" },
  desert: { base: "#d9bd80", blobs: ["#e6cc93", "#cba86a", "#efd9a6", "#c49c5e"], fleck: "rgba(255,248,220,0.45)" },
  tundra: { base: "#86896f", blobs: ["#9a9d82", "#6f735c", "#adb09a", "#7b7f63"], fleck: "rgba(235,238,225,0.35)" },
  snow: { base: "#e4ebf0", blobs: ["#ffffff", "#cdd8e1", "#f2f6f9", "#bfcbd6"], fleck: "rgba(255,255,255,0.6)" },
  coast: { base: "#3f97ad", blobs: ["#4cabc0", "#348aa0", "#5fbccc", "#2d7c93"], fleck: "rgba(220,245,255,0.25)" },
  ocean: { base: "#1f5670", blobs: ["#25637d", "#1a4a62", "#2c6e88", "#164258"], fleck: "rgba(170,220,240,0.14)" },
  beach: { base: "#d8c48e", blobs: ["#e6d6a6", "#c9b27a", "#efe2bd"], fleck: "rgba(255,255,240,0.4)" },
};
const TEX = new Map();
// Photo textures (visuals round 2): CC0 aerial ground from Poly Haven (web/static/terrain), graded
// per terrain to the map palette, with the painted texture laid softly over them for broad tone
// variation. Until they load the painted textures stand in, and the ground is rebuilt after.
const TERRAIN_PHOTO = {
  grassland: ["grass", "saturate(1.7) brightness(1.22) hue-rotate(12deg)", "rgba(120,175,55,0.2)"],
  plains: ["grass", "sepia(0.55) saturate(2) hue-rotate(-18deg) brightness(1.3)", "rgba(215,180,80,0.24)"],
  desert: ["dunes", "sepia(0.65) saturate(1.6) brightness(1.32)", "rgba(230,190,120,0.25)"],
  beach: ["sand", "sepia(0.45) saturate(1.3) brightness(1.35)", "rgba(240,220,170,0.2)"],
  tundra: ["tundra", "saturate(0.6) brightness(1.08)", "rgba(140,140,120,0.2)"],
  snow: ["snow", "brightness(1.45) contrast(0.75) saturate(0.35)", "rgba(240,246,250,0.35)"],
};
const PHOTOS = {};
let photosPending = 0;
for (const src of new Set(Object.values(TERRAIN_PHOTO).map((p) => p[0]))) {
  const im = new Image(); photosPending++;
  im.onload = im.onerror = () => {
    if (--photosPending === 0) {  // every photo is in: drop painted stand-ins and rebuild the ground
      for (const k of Object.keys(TERRAIN_PHOTO)) TEX.delete(k);
      CHUNKS.clear(); if (typeof S !== "undefined") S.dirty = true;
    }
  };
  im.src = `terrain/${src}.jpg`; PHOTOS[src] = im;
}
function photoTexture(kind) {
  const spec = TERRAIN_PHOTO[kind];
  if (!spec || photosPending) return null;
  const im = PHOTOS[spec[0]];
  if (!im.naturalWidth) return null;
  const N = 512, c = document.createElement("canvas"); c.width = c.height = N;
  const g = c.getContext("2d");
  g.filter = spec[1]; g.drawImage(im, 0, 0, N, N); g.filter = "none";
  g.fillStyle = spec[2]; g.fillRect(0, 0, N, N);
  return c;
}
// A 256px seamless painted texture: soft blobs (drawn wrapped at the edges) plus brush flecks.
function terrainTexture(kind) {
  if (TEX.has(kind)) return TEX.get(kind);
  const photo = photoTexture(kind);
  if (photo) {  // the painted texture adds broad, soft tone variation over the photo
    const painted = paintedTexture(kind), g = photo.getContext("2d");
    g.globalAlpha = 0.22; g.globalCompositeOperation = "soft-light";
    for (const ox of [0, 256]) for (const oy of [0, 256]) g.drawImage(painted, ox, oy);
    g.globalAlpha = 1; g.globalCompositeOperation = "source-over";
    TEX.set(kind, photo);
    return photo;
  }
  if (TERRAIN_PHOTO[kind] && photosPending) return paintedTexture(kind);  // a stand-in, not cached
  const c = paintedTexture(kind);
  PAINTED.set(kind, c);
  return c;
}
const PAINTED = new Map();
function paintedTexture(kind) {
  if (PAINTED.has(kind)) return PAINTED.get(kind);
  const P = PAINT[kind], N = 256, c = document.createElement("canvas");
  c.width = c.height = N;
  const g = c.getContext("2d"), rnd = rng(kind.length * 977 + kind.charCodeAt(0));
  g.fillStyle = P.base; g.fillRect(0, 0, N, N);
  const blob = (x, y, r, col, a) => {
    for (const ox of [-N, 0, N]) for (const oy of [-N, 0, N]) {
      const rg = g.createRadialGradient(x + ox, y + oy, 0, x + ox, y + oy, r);
      rg.addColorStop(0, col); rg.addColorStop(1, "rgba(0,0,0,0)");
      g.globalAlpha = a; g.fillStyle = rg; g.beginPath(); g.arc(x + ox, y + oy, r, 0, Math.PI * 2); g.fill();
    }
  };
  for (let k = 0; k < 70; k++) blob(rnd() * N, rnd() * N, 18 + rnd() * 46, P.blobs[k % P.blobs.length], 0.45 + rnd() * 0.35);
  g.globalAlpha = 1;
  for (let k = 0; k < 380; k++) {  // brush strokes, like a painted map
    const x = rnd() * N, y = rnd() * N, len = 2 + rnd() * 6, a = (rnd() - 0.5) * 0.8;
    g.strokeStyle = rnd() < 0.55 ? P.fleck : "rgba(0,0,0,0.10)"; g.lineWidth = 1 + rnd() * 1.4;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len); g.stroke();
  }
  if (kind === "desert" || kind === "beach") {  // dune ripples
    g.strokeStyle = "rgba(160,120,60,0.18)"; g.lineWidth = 1.5;
    for (let k = 0; k < 26; k++) { const x = rnd() * N, y = rnd() * N; g.beginPath(); g.arc(x, y + 20, 22, Math.PI * 1.15, Math.PI * 1.85); g.stroke(); }
  }
  if (kind === "coast" || kind === "ocean") {  // wave glints
    g.strokeStyle = kind === "coast" ? "rgba(235,250,255,0.28)" : "rgba(170,210,255,0.16)"; g.lineWidth = 1.4;
    for (let k = 0; k < 60; k++) {
      const x = rnd() * N, y = rnd() * N;
      g.beginPath(); g.moveTo(x - 6, y); g.quadraticCurveTo(x - 3, y - 2.5, x, y); g.quadraticCurveTo(x + 3, y + 2.5, x + 6, y); g.stroke();
    }
  }
  TEX.set(kind, c);
  return c;
}
function isWater(t) { return t.terrain === "coast" || t.terrain === "ocean"; }
// Scratch canvases reused while building chunks, to avoid churning memory.
const LAYERS = [];
function layerCanvas(w, h, slot) {
  let c = LAYERS[slot];
  if (!c) { c = document.createElement("canvas"); LAYERS[slot] = c; }
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  return c;
}
// Feature sprites drawn over the blended ground (trees, hills, peaks, marsh), cached.
const FEATURES = new Map();
// Rendered feature art (visuals round 2): forests, jungle, hills and mountains rendered in Blender
// from Poly Haven CC0 models and textures (web/static/features, sources in its README), seen from
// the map camera and fitted to the hex. Until they load, the painted sprites stand in.
const FEATURE_FILES = { forest: 4, jungle: 2, hills: 3, mountain: 3 };
const FEATURE_ART = {};
let featurePending = 0;
for (const [kind, n] of Object.entries(FEATURE_FILES)) {
  FEATURE_ART[kind] = [];
  for (let k = 0; k < n; k++) {
    const im = new Image(); featurePending++;
    im.onload = im.onerror = () => { if (--featurePending === 0) { FEATURES.clear(); RELIEF = undefined; CHUNKS.clear(); if (typeof S !== "undefined") S.dirty = true; } };
    im.src = `features/${kind}_${k}.png`; FEATURE_ART[kind].push(im);
  }
}
const featureArt = (kind, v) => { if (featurePending) return null; const list = FEATURE_ART[kind].filter((im) => im.naturalWidth); return list.length ? list[v % list.length] : null; };
// forest tints by climate and season: cold forests turn dark blue-green, a few warm ones autumnal
function forestFilter(t, variant) {
  if (t.terrain === "tundra" || t.terrain === "snow") return "hue-rotate(28deg) saturate(0.75) brightness(0.82) contrast(1.1)";
  if (variant === 5 && t.terrain !== "desert") return "hue-rotate(-38deg) saturate(1.9) brightness(1.22)";
  if (variant === 4) return "hue-rotate(-14deg) saturate(1.6) brightness(1.22)";
  return "saturate(1.55) hue-rotate(12deg) brightness(1.28) contrast(1.05)";
}
// hill relief: the rendered grey shading, re-centred on mid-grey so that overlay only lights the
// slopes facing the sun and shades the rest, with soft edges
let RELIEF;
function hillRelief() {
  if (RELIEF !== undefined) return RELIEF;
  if (featurePending) return null;
  const src = FEATURE_ART.hills.filter((im) => im.naturalWidth);
  if (!src.length) return (RELIEF = null);
  RELIEF = src.map((im) => {
    const N = 256, c = document.createElement("canvas"); c.width = c.height = N;
    const g = c.getContext("2d", { willReadFrequently: true }); g.drawImage(im, 0, 0, N, N);
    const img = g.getImageData(0, 0, N, N), d = img.data;
    let sum = 0, cnt = 0;
    for (let p = 0; p < d.length; p += 4) if (d[p + 3] > 200) { sum += d[p]; cnt++; }
    const mean = cnt ? sum / cnt : 128;
    for (let p = 0; p < d.length; p += 4) {
      const v = Math.max(0, Math.min(255, 128 + (d[p] - mean) * 1.6));
      const x = (p / 4) % N, y = Math.floor(p / 4 / N), r = Math.hypot(x - N / 2, y - N / 2) / (N * 0.38);
      d[p] = d[p + 1] = d[p + 2] = v; d[p + 3] = d[p + 3] * Math.max(0, Math.min(1, (1 - r) * 3));
    }
    g.putImageData(img, 0, 0);
    return c;
  });
  return RELIEF;
}
function featureSprite(t, Rb, variant, rendered = false) {
  const key = `${t.elevation}|${t.feature || ""}|${t.terrain}|${Rb}|${variant}|${rendered ? 1 : 0}`;
  let c = FEATURES.get(key);
  if (c !== undefined) return c;
  if (FEATURES.size > 900) FEATURES.clear();
  if ((t.elevation === "flat" || (t.elevation === "hills" && rendered)) && !t.feature) { FEATURES.set(key, null); return null; }
  const tall = t.elevation === "mountain" && rendered;  // rendered mountains need a taller canvas
  const w = Math.ceil(Rb * (tall ? 3.9 : 2.6)), h = Math.ceil(Rb * (tall ? 4.8 : 2.8));
  c = document.createElement("canvas"); c.width = w; c.height = h;
  const g = c.getContext("2d"), cx = w / 2, cy = h / 2 + Rb * 0.1;
  const rnd = rng(variant * 131 + (t.feature || "").length * 17 + t.elevation.length * 5 + t.terrain.length);
  const art = (kind) => { const im = featureArt(kind, variant); if (!im) return false; g.drawImage(im, cx - w / 2, cy - w / 2, w, w); return true; };
  if (t.feature === "marsh") paintMarsh(g, cx, cy, Rb, rnd);
  if (t.elevation === "hills" && !rendered) paintHills(g, cx, cy, Rb, rnd, t.terrain);
  if (t.feature === "forest") { g.filter = forestFilter(t, variant); if (!art("forest")) { g.filter = "none"; paintForest(g, cx, cy, Rb, rnd, t.terrain); } g.filter = "none"; }
  if (t.feature === "jungle") { g.filter = "saturate(1.7) hue-rotate(18deg) brightness(0.92) contrast(1.1)"; if (!art("jungle")) { g.filter = "none"; paintJungle(g, cx, cy, Rb, rnd); } g.filter = "none"; }
  if (t.elevation === "mountain") {
    if (t.terrain === "desert") g.filter = "sepia(0.4) saturate(1.3) brightness(1.05)";
    const im = featureArt("mountain", variant);  // rendered with the hex centre 62% down the frame
    if (im) g.drawImage(im, cx - w / 2, cy - w * 0.62, w, w);
    else { g.filter = "none"; paintMountains(g, cx, cy, Rb, rnd, t.terrain); }
    g.filter = "none";
  }
  FEATURES.set(key, c);
  return c;
}
function paintHills(g, cx, cy, R, rnd, terrain) {
  const tone = { desert: ["#e4c98f", "#a7834e"], snow: ["#ffffff", "#9fb0c0"], tundra: ["#a9ab92", "#5f624f"] }[terrain] || ["#9fbf6a", "#4c6a2c"];
  const mounds = [[-0.42, 0.28, 0.62], [0.36, 0.34, 0.55], [0.0, -0.08, 0.5], [-0.15, 0.55, 0.42]];
  for (const [dx, dy, s] of mounds) {
    const x = cx + dx * R, y = cy + dy * R, w = R * 0.62 * s * (0.9 + rnd() * 0.2), h = R * 0.5 * s;
    g.fillStyle = "rgba(0,0,0,0.18)"; g.beginPath(); g.ellipse(x + w * 0.15, y + h * 0.1, w, h * 0.35, 0, 0, Math.PI * 2); g.fill();
    const hg = g.createLinearGradient(x - w, y - h, x + w * 0.6, y);
    hg.addColorStop(0, tone[0]); hg.addColorStop(1, tone[1]);
    g.fillStyle = hg; g.beginPath(); g.moveTo(x - w, y); g.bezierCurveTo(x - w * 0.6, y - h * 1.1, x + w * 0.5, y - h * 1.15, x + w, y); g.closePath(); g.fill();
    g.strokeStyle = "rgba(40,30,15,0.25)"; g.lineWidth = Math.max(1, R * 0.03); g.stroke();
  }
}
function paintForest(g, cx, cy, R, rnd, terrain) {
  const cold = terrain === "tundra" || terrain === "snow";
  // trees grow in clumps with clearings between them; density varies from hex to hex
  const pts = [], clumps = 2 + Math.floor(rnd() * 3), total = 7 + Math.floor(rnd() * 8);
  const centres = Array.from({ length: clumps }, () => [cx + (rnd() - 0.5) * 1.1 * R, cy + (rnd() - 0.5) * 0.9 * R]);
  for (let k = 0; k < total; k++) {
    const [qx, qy] = centres[k % clumps], a = rnd() * Math.PI * 2, d = Math.sqrt(rnd()) * R * 0.32;
    pts.push([qx + Math.cos(a) * d, qy + Math.sin(a) * d * 0.75, 0.7 + rnd() * 0.55]);
  }
  // a darker forest floor under each clump
  for (const [qx, qy] of centres) {
    const fg = g.createRadialGradient(qx, qy + R * 0.05, 0, qx, qy + R * 0.05, R * 0.42);
    fg.addColorStop(0, cold ? "rgba(40,60,45,0.35)" : "rgba(30,60,20,0.35)"); fg.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = fg; g.beginPath(); g.ellipse(qx, qy + R * 0.05, R * 0.45, R * 0.32, 0, 0, Math.PI * 2); g.fill();
  }
  pts.sort((a, b) => a[1] - b[1]);
  for (const [x, y, s] of pts) {
    g.fillStyle = "rgba(0,0,0,0.22)"; g.beginPath(); g.ellipse(x + R * 0.06, y + R * 0.09, R * 0.13 * s, R * 0.05 * s, 0, 0, Math.PI * 2); g.fill();
    if (cold || rnd() < 0.55) {
      const hgt = R * 0.42 * s, wid = R * 0.15 * s;
      g.fillStyle = cold ? "#2d4a36" : "#2b5226"; g.beginPath(); g.moveTo(x, y - hgt); g.lineTo(x - wid, y + R * 0.04); g.lineTo(x + wid, y + R * 0.04); g.fill();
      g.fillStyle = cold ? "#46684f" : "#3f7433"; g.beginPath(); g.moveTo(x, y - hgt); g.lineTo(x - wid, y + R * 0.04); g.lineTo(x - wid * 0.1, y + R * 0.04); g.fill();
      if (cold) { g.fillStyle = "rgba(240,245,250,0.85)"; g.beginPath(); g.moveTo(x, y - hgt); g.lineTo(x - wid * 0.35, y - hgt * 0.62); g.lineTo(x + wid * 0.35, y - hgt * 0.62); g.fill(); }
    } else {
      g.fillStyle = "#4b3420"; g.fillRect(x - R * 0.02, y - R * 0.05, R * 0.04, R * 0.1);
      g.fillStyle = "#3d6b2b"; g.beginPath(); g.arc(x, y - R * 0.13 * s, R * 0.14 * s, 0, Math.PI * 2); g.fill();
      g.fillStyle = "#5a8f3c"; g.beginPath(); g.arc(x - R * 0.04 * s, y - R * 0.17 * s, R * 0.08 * s, 0, Math.PI * 2); g.fill();
    }
  }
}
function paintJungle(g, cx, cy, R, rnd) {
  const pts = [];
  for (let k = 0; k < 15; k++) pts.push([cx + (rnd() - 0.5) * 1.6 * R, cy + (rnd() - 0.5) * 1.35 * R, 0.7 + rnd() * 0.6]);
  pts.sort((a, b) => a[1] - b[1]);
  for (const [x, y, s] of pts) {
    g.fillStyle = "rgba(0,0,0,0.25)"; g.beginPath(); g.ellipse(x + R * 0.05, y + R * 0.08, R * 0.15 * s, R * 0.05 * s, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#1c4a22"; g.beginPath(); g.arc(x, y - R * 0.08 * s, R * 0.17 * s, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#2f6e32"; g.beginPath(); g.arc(x - R * 0.05 * s, y - R * 0.13 * s, R * 0.11 * s, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "#3f8a3a"; g.lineWidth = Math.max(1, R * 0.03);
    for (let f = 0; f < 4; f++) { const a = (f / 4) * Math.PI * 2 + rnd(); g.beginPath(); g.moveTo(x, y - R * 0.1 * s); g.quadraticCurveTo(x + Math.cos(a) * R * 0.12 * s, y - R * 0.2 * s, x + Math.cos(a) * R * 0.2 * s, y - R * 0.05 * s); g.stroke(); }
  }
}
function paintMountains(g, cx, cy, R, rnd, terrain) {
  const peaks = [[-0.38, 0.95, 0.55], [0.3, 0.75, 0.5], [0.0, 1.15, 0.6], [0.55, 0.5, 0.35]];
  peaks.sort((a, b) => b[1] - a[1]);
  for (const [dx, hgt, wid] of peaks) {
    const bx = cx + dx * R, by = cy + R * 0.55, px = bx + (rnd() - 0.5) * R * 0.1, py = by - hgt * R * (0.85 + rnd() * 0.25);
    g.fillStyle = "rgba(0,0,0,0.22)"; g.beginPath(); g.ellipse(bx + R * 0.1, by, wid * R * 1.05, R * 0.12, 0, 0, Math.PI * 2); g.fill();
    const lg = g.createLinearGradient(bx - wid * R, py, px, by);
    lg.addColorStop(0, "#a49a8b"); lg.addColorStop(1, "#7d7466");
    g.fillStyle = lg; g.beginPath(); g.moveTo(bx - wid * R, by); g.lineTo(px, py); g.lineTo(px + R * 0.02, by); g.fill();
    const dg = g.createLinearGradient(px, py, bx + wid * R, by);
    dg.addColorStop(0, "#5f574c"); dg.addColorStop(1, "#40392f");
    g.fillStyle = dg; g.beginPath(); g.moveTo(px, py); g.lineTo(bx + wid * R, by); g.lineTo(px - R * 0.02, by); g.fill();
    g.strokeStyle = "rgba(30,25,20,0.35)"; g.lineWidth = Math.max(1, R * 0.025);
    g.beginPath(); g.moveTo(px, py); g.lineTo(px - wid * R * 0.3, py + hgt * R * 0.45); g.lineTo(px - wid * R * 0.15, by); g.stroke();
    const cap = terrain === "snow" || terrain === "tundra" ? 0.5 : 0.32;
    g.fillStyle = "#f4f7fa"; g.beginPath(); g.moveTo(px, py);
    g.lineTo(px - wid * R * cap, py + hgt * R * cap * 0.9); g.lineTo(px - wid * R * cap * 0.4, py + hgt * R * cap * 0.7);
    g.lineTo(px, py + hgt * R * cap * 0.95); g.lineTo(px + wid * R * cap * 0.5, py + hgt * R * cap * 0.65);
    g.lineTo(px + wid * R * cap, py + hgt * R * cap * 0.9); g.closePath(); g.fill();
  }
}
function paintMarsh(g, cx, cy, R, rnd) {
  for (let k = 0; k < 6; k++) {
    const x = cx + (rnd() - 0.5) * 1.3 * R, y = cy + (rnd() - 0.5) * 1.1 * R;
    const pg = g.createRadialGradient(x, y, 0, x, y, R * 0.25);
    pg.addColorStop(0, "rgba(70,120,140,0.75)"); pg.addColorStop(1, "rgba(50,90,100,0)");
    g.fillStyle = pg; g.beginPath(); g.ellipse(x, y, R * 0.26, R * 0.11, 0, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "rgba(55,85,35,0.9)"; g.lineWidth = Math.max(1, R * 0.025);
    for (const d of [-0.1, -0.03, 0.04, 0.11]) { g.beginPath(); g.moveTo(x + d * R, y - R * 0.02); g.quadraticCurveTo(x + d * R * 1.2, y - R * 0.15, x + d * R * 1.6, y - R * 0.27); g.stroke(); }
  }
}

// =============================================================================================
// ground chunks: terrain and coasts rendered once per 16x16 block of hexes at a few zoom steps,
// redrawn only when a tile in the block changes. Keeps the frame cheap however rich the art.

const CHUNK = 16;
const ZOOM_STEPS = [6, 9, 13, 18, 24, 32, 44, 58];
const CHUNKS = new Map();      // `${cx},${cy}|${Rb}` -> canvas
const CHUNK_VER = new Map();   // `${cx},${cy}` -> version, bumped when a tile changes
let TILE_SIG = new Map();      // tile index -> signature of what the ground shows
function zoomStep(R) { return ZOOM_STEPS.find((b) => b >= R) || ZOOM_STEPS[ZOOM_STEPS.length - 1]; }
function tileSig(t) { return `${t.terrain}|${t.elevation}|${t.feature || ""}`; }
// After each refresh: mark the chunks whose ground changed (new tiles explored, terrain known).
function invalidateGround(v) {
  const next = new Map();
  for (const [k, t] of Object.entries(v.tiles)) {
    const i = Number(k), sig = tileSig(t);
    next.set(i, sig);
    if (TILE_SIG.get(i) !== sig) bumpChunk(i, v.width);
  }
  for (const i of TILE_SIG.keys()) if (!next.has(i)) bumpChunk(i, v.width);
  TILE_SIG = next;
}
function bumpChunk(i, width) {
  const c = i % width, r = Math.floor(i / width);
  const seen = new Set();
  for (const dc of [-2, 0, 2]) for (const dr of [-2, 0, 2]) {  // a chunk blends 2 hexes past its edge
    const key = `${Math.floor((c + dc) / CHUNK)},${Math.floor((r + dr) / CHUNK)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    CHUNK_VER.set(key, (CHUNK_VER.get(key) || 0) + 1);
  }
}
const CHUNK_PAD = 2 * R0;  // world units of overdraw around a chunk (features spill over)
function chunkOrigin(cx, cy) { return [cx * CHUNK * SQ3 * R0 - CHUNK_PAD, cy * CHUNK * 1.5 * R0 - CHUNK_PAD]; }
// Fill a mask canvas (white where wanted) with a terrain's texture, aligned to the world.
function texturise(mg, kind, w, h, wx, wy, Rb) {
  mg.globalCompositeOperation = "source-in";
  const tex = terrainTexture(kind), size = tex.width;
  // photo tiles (512 px) span about three hexes; painted tiles (256 px) keep their old scale
  const sc = size === 512 ? Rb / 95 : Math.max(0.35, Rb / 40);
  const pat = mg.createPattern(tex, "repeat");
  pat.setTransform(new DOMMatrix().translate(-wx % (size * sc), -wy % (size * sc)).scale(sc));
  mg.fillStyle = pat; mg.fillRect(0, 0, w, h);
  mg.globalCompositeOperation = "source-over";
}
// A 256px seamless value-noise tile (two octaves), to wobble coastlines.
let NOISE = null;
function noiseTile() {
  if (NOISE) return NOISE;
  const N = 256, c = document.createElement("canvas"); c.width = c.height = N;
  const g = c.getContext("2d"), img = g.createImageData(N, N), rnd = rng(4242);
  const grids = [8, 16].map((n) => ({ n, v: Array.from({ length: n * n }, () => rnd()) }));
  const sm = (t) => t * t * (3 - 2 * t);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    let v = 0, amp = 0.65;
    for (const { n, v: gv } of grids) {
      const fx = (x / N) * n, fy = (y / N) * n, x0 = Math.floor(fx), y0 = Math.floor(fy), tx = sm(fx - x0), ty = sm(fy - y0);
      const at = (a, b) => gv[((b + n) % n) * n + ((a + n) % n)];
      const top = at(x0, y0) * (1 - tx) + at(x0 + 1, y0) * tx, bot = at(x0, y0 + 1) * (1 - tx) + at(x0 + 1, y0 + 1) * tx;
      v += (top * (1 - ty) + bot * ty) * amp; amp = 0.35;
    }
    const o = (y * N + x) * 4; img.data[o] = img.data[o + 1] = img.data[o + 2] = Math.round(v * 255); img.data[o + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  return (NOISE = c);
}
// Smooth coastline masks for one chunk: land hexes are blurred into a field, wobbled by world-aligned
// noise, then cut at three levels: the land itself, a beach band just inside the shore, and a surf
// band just outside it. Hexes next to unexplored ones count as land, so fog edges show no coast.
function coastMasks(w, h, Rb, k, ox, oy, land, anyWater) {
  if (!anyWater) return null;
  // the field is smooth, so it is built at a quarter of the chunk's size and scaled up when drawn
  const q = 4, wq = Math.ceil(w / q), hq = Math.ceil(h / q);
  const F = layerCanvas(wq, hq, 3), fg = F.getContext("2d", { willReadFrequently: true });
  fg.setTransform(1, 0, 0, 1, 0, 0); fg.fillStyle = "#000"; fg.fillRect(0, 0, wq, hq);
  fg.setTransform(1 / q, 0, 0, 1 / q, 0, 0);
  // half a wide blur (smooth, wavy coasts) plus half a narrow one (so one-hex islands survive)
  fg.beginPath();
  for (const [i, , x, y] of land) {
    hexSub(fg, x, y, Rb);
    for (const [n] of neighbourEdges(i)) {
      if (S.tilesByIndex.has(n)) continue;
      const [nx, ny] = center(n); hexSub(fg, (nx - ox) * k, (ny - oy) * k, Rb);
    }
  }
  fg.globalCompositeOperation = "lighter"; fg.fillStyle = "#808080";
  fg.filter = `blur(${Math.max(1, (Rb * 0.85) / q)}px)`; fg.fill("nonzero");
  fg.filter = `blur(${Math.max(0.7, (Rb * 0.32) / q)}px)`; fg.fill("nonzero");
  fg.filter = "none"; fg.globalCompositeOperation = "source-over"; fg.setTransform(1, 0, 0, 1, 0, 0);
  const N = layerCanvas(wq, hq, 4), ng = N.getContext("2d", { willReadFrequently: true });
  const pat = ng.createPattern(noiseTile(), "repeat"), sc = (Rb * 12) / 256 / q;
  pat.setTransform(new DOMMatrix().translate(-((ox * k) / q) % (256 * sc), -((oy * k) / q) % (256 * sc)).scale(sc));
  ng.fillStyle = pat; ng.fillRect(0, 0, wq, hq);
  const f = fg.getImageData(0, 0, wq, hq).data, nz = ng.getImageData(0, 0, wq, hq).data;
  const out = [fg.createImageData(wq, hq), fg.createImageData(wq, hq), fg.createImageData(wq, hq)];
  const [ld, bd, sd] = out.map((o) => o.data);
  const ss = (a, b, v) => { if (v <= a) return 0; if (v >= b) return 1; const t = (v - a) / (b - a); return t * t * (3 - 2 * t); };
  for (let p = 0; p < f.length; p += 4) {
    const v = f[p] / 255 + (nz[p] / 255 - 0.5) * 0.34;
    const landA = ss(0.45, 0.55, v), inner = ss(0.6, 0.72, v), surf = ss(0.28, 0.44, v) - landA;
    ld[p] = ld[p + 1] = ld[p + 2] = bd[p] = bd[p + 1] = bd[p + 2] = sd[p] = sd[p + 1] = sd[p + 2] = 255;
    ld[p + 3] = landA * 255; bd[p + 3] = Math.max(0, landA - inner) * 255; sd[p + 3] = Math.max(0, surf) * 200;
  }
  const make = (img) => {  // scale the small mask up to the chunk's size
    const small = document.createElement("canvas"); small.width = wq; small.height = hq; small.getContext("2d").putImageData(img, 0, 0);
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const cg = c.getContext("2d"); cg.imageSmoothingQuality = "high"; cg.drawImage(small, 0, 0, wq * q, hq * q);
    return c;
  };
  return { land: make(out[0]), beach: make(out[1]), surf: make(out[2]) };
}
function renderChunk(cx, cy, Rb) {
  const k = Rb / R0, [ox, oy] = chunkOrigin(cx, cy);
  const w = Math.ceil(((CHUNK + 1.5) * SQ3 * R0 + 2 * CHUNK_PAD) * k) + 4;
  const h = Math.ceil(((CHUNK * 1.5 + 2.5) * R0 + 2 * CHUNK_PAD) * k) + 4;
  const W0 = S.view.width;
  const tiles = [], ring = [];  // the chunk's own hexes, and its own plus a ring of neighbours
  for (let r = cy * CHUNK - 2; r < Math.min(S.view.height, (cy + 1) * CHUNK + 2); r++) {
    if (r < 0) continue;
    for (let col = cx * CHUNK - 2; col < Math.min(W0, (cx + 1) * CHUNK + 2); col++) {
      if (col < 0) continue;
      const i = r * W0 + col, t = S.tilesByIndex.get(i);
      if (!t) continue;
      const [wx, wy] = center(i);
      const row = [i, t, (wx - ox) * k, (wy - oy) * k];
      ring.push(row);
      if (r >= cy * CHUNK && r < (cy + 1) * CHUNK && col >= cx * CHUNK && col < (cx + 1) * CHUNK) tiles.push(row);
    }
  }
  if (!tiles.length) return null;  // nothing explored here yet: no canvas
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const g = c.getContext("2d");
  const coastal = (i) => neighbourEdges(i).some(([n]) => { const t2 = S.tilesByIndex.get(n); return t2 && isWater(t2); });
  // 1. ground, clipped to this chunk's own hexes (the ring of neighbours only feeds the blending).
  //    Water first, then the land cut out by a smooth coastline mask with a beach band inside it
  //    and a surf band outside it.
  g.save(); g.beginPath();
  for (const [, , x, y] of tiles) for (let q = 0; q < 6; q++) { const [px, py] = corner(x, y, Rb + 0.6, q); if (q === 0) g.moveTo(px, py); else g.lineTo(px, py); }
  g.clip();
  const blurPx = Math.max(1.5, Rb * 0.38);
  const paintLayer = (target, kind, rows, grow, blur = blurPx) => {  // one terrain as a world-aligned texture in a blurred mask
    const m = layerCanvas(w, h, 0), mg = m.getContext("2d");
    mg.clearRect(0, 0, w, h);
    mg.filter = `blur(${blur}px)`; mg.fillStyle = "#fff"; mg.beginPath();
    for (const [i, , x, y] of rows) hexSub(mg, x, y, Rb * grow(i));
    mg.fill("nonzero"); mg.filter = "none";
    texturise(mg, kind, w, h, ox * k, oy * k, Rb);
    target.drawImage(m, 0, 0);
  };
  const water = ring.filter(([, t]) => isWater(t)), land = ring.filter(([, t]) => !isWater(t));
  // water: deep ocean everywhere as the base, then the shallows (coast hexes, and land hexes, so a
  // coastline that curves inland shows shallows) as one widely blurred layer: no hard hex edges
  g.beginPath(); for (const [, , x, y] of ring) hexSub(g, x, y, Rb + 1);
  g.fillStyle = PAINT.ocean.base; g.fill();
  paintLayer(g, "ocean", ring.filter(([, t]) => t.terrain === "ocean"), () => 1.1, Math.max(2, Rb * 0.5));
  paintLayer(g, "coast", ring.filter(([, t]) => t.terrain !== "ocean"), () => 1.05, Math.max(2, Rb * 0.8));
  if (land.length) {
    const masks = coastMasks(w, h, Rb, k, ox, oy, land, water.length > 0);
    if (masks) {  // surf: a soft white band just off the shore
      const sm = layerCanvas(w, h, 0), smg = sm.getContext("2d");
      smg.clearRect(0, 0, w, h); smg.drawImage(masks.surf, 0, 0);
      smg.globalCompositeOperation = "source-in"; smg.fillStyle = "rgba(236,248,255,0.6)"; smg.fillRect(0, 0, w, h); smg.globalCompositeOperation = "source-over";
      g.drawImage(sm, 0, 0);
    }
    // land: each terrain grown past its hex, then cut to the coastline
    const L = layerCanvas(w, h, 1), lg = L.getContext("2d");
    lg.clearRect(0, 0, w, h);
    for (const kind of ["snow", "tundra", "desert", "plains", "grassland"]) {
      lg.beginPath(); for (const [, t, x, y] of land) if (t.terrain === kind) hexSub(lg, x, y, Rb * 1.3);
      lg.fillStyle = PAINT[kind].base; lg.fill();
    }
    for (const kind of ["snow", "tundra", "desert", "plains", "grassland"]) {
      const mine = land.filter(([, t]) => t.terrain === kind);
      if (mine.length) paintLayer(lg, kind, mine, () => (masks ? 1.22 : 1.02));
    }
    if (masks) {
      // beach: sand along the shore, inside the coastline (pale shingle on cold coasts)
      const B = layerCanvas(w, h, 2), bg = B.getContext("2d");
      bg.clearRect(0, 0, w, h); bg.drawImage(masks.beach, 0, 0);
      texturise(bg, "beach", w, h, ox * k, oy * k, Rb);
      lg.drawImage(B, 0, 0);
      lg.globalCompositeOperation = "destination-in"; lg.drawImage(masks.land, 0, 0); lg.globalCompositeOperation = "source-over";
    }
    g.drawImage(L, 0, 0);
  }
  g.restore();
  // 2. a thin light hex grid over land and water, as in Civ
  if (Rb >= 13) {
    g.lineWidth = 1;
    for (const water of [false, true]) {
      g.strokeStyle = water ? "rgba(200,235,255,0.13)" : "rgba(255,250,225,0.14)"; g.beginPath();
      for (const [, t, x, y] of tiles) if (isWater(t) === water) hexSub(g, x, y, Rb - 0.5);
      g.stroke();
    }
  }
  // 3. hills shade the ground under them (rendered relief, laid in overlay so the terrain keeps
  //    its colour), then features over the ground, back to front
  const relief = hillRelief();
  if (relief) {
    g.save(); g.globalCompositeOperation = "overlay";
    for (const [i, t, x, y] of tiles) {
      if (t.elevation !== "hills") continue;
      const im = relief[Math.floor(hash(i, 5) * relief.length)], s = Rb * 2.6;
      g.drawImage(im, x - s / 2, y - s / 2, s, s);
    }
    g.restore();
  }
  for (const [i, t, x, y] of [...tiles].sort((a, b) => a[3] - b[3])) {
    const sp = featureSprite(t, Rb, Math.floor(hash(i, 3) * 6), !!relief);
    if (sp) g.drawImage(sp, x - sp.width / 2, y - sp.height / 2 - Rb * 0.1);
  }
  return c;
}
function drawGround(W, H, R) {
  const Rb = zoomStep(R), scale = R / Rb;
  const [wx0, wy0] = toWorld(0, 0), [wx1, wy1] = toWorld(W, H);
  const cx0 = Math.max(0, Math.floor(wx0 / (CHUNK * SQ3 * R0)) - 1), cx1 = Math.floor(wx1 / (CHUNK * SQ3 * R0)) + 1;
  const cy0 = Math.max(0, Math.floor(wy0 / (CHUNK * 1.5 * R0)) - 1), cy1 = Math.floor(wy1 / (CHUNK * 1.5 * R0)) + 1;
  for (let cy = cy0; cy <= cy1; cy++) {
    for (let cx = cx0; cx <= cx1; cx++) {
      if (cx * CHUNK >= S.view.width || cy * CHUNK >= S.view.height) continue;
      const key = `${cx},${cy}|${Rb}`, ver = CHUNK_VER.get(`${cx},${cy}`) || 0;
      let entry = CHUNKS.get(key);
      if (!entry || entry.ver !== ver) {
        entry = { ver, canvas: renderChunk(cx, cy, Rb) };
        CHUNKS.delete(key); CHUNKS.set(key, entry);
        if (CHUNKS.size > 90) CHUNKS.delete(CHUNKS.keys().next().value);  // least recently made
      }
      if (!entry.canvas) continue;
      const [ox, oy] = chunkOrigin(cx, cy);
      const [sx, sy] = toScreen(ox, oy);
      ctx.drawImage(entry.canvas, sx, sy, entry.canvas.width * scale, entry.canvas.height * scale);
    }
  }
}
// The hexes on screen, from the camera (rows and columns), with their screen centres.
function visibleTiles(W, H, R) {
  const out = [];
  const [wx0, wy0] = toWorld(-R * 3, -R * 3), [wx1, wy1] = toWorld(W + R * 3, H + R * 3);
  const r0 = Math.max(0, Math.floor((wy0 - R0) / (1.5 * R0)) - 1), r1 = Math.min(S.view.height - 1, Math.ceil((wy1 - R0) / (1.5 * R0)) + 1);
  const c0 = Math.max(0, Math.floor(wx0 / (SQ3 * R0)) - 1), c1 = Math.min(S.view.width - 1, Math.ceil(wx1 / (SQ3 * R0)) + 1);
  for (let r = r0; r <= r1; r++) {
    for (let c = c0; c <= c1; c++) {
      const i = r * S.view.width + c;
      const [sx, sy] = toScreen(...center(i));
      out.push([i, sx, sy, S.tilesByIndex.has(i)]);
    }
  }
  return out;
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
  const newWorld = !S.view || S.view.seed !== v.seed || S.view.width !== v.width || S.view.me !== v.me;
  // keep a log of past turns' events in this browser session (the server sends the latest)
  S.history = S.history || [];
  if (newTurn || !S.history.length) S.history.push({ turn: v.turn, events: v.events });
  else S.history[S.history.length - 1].events = v.events;
  if (S.history.length > 40) S.history.shift();
  S.view = v;
  S.explored = new Set(v.explored);
  S.tilesByIndex = new Map(Object.entries(v.tiles).map(([k, t]) => [Number(k), t]));
  if (newWorld) { TILE_SIG = new Map(); CHUNKS.clear(); CHUNK_VER.clear(); }
  invalidateGround(v);
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
  showNewStory();
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
  // only the rows and columns on screen (the map has ~27,000 hexes)
  const visible = visibleTiles(W, H, R);
  // 1-2. the ground (terrain and coasts), from cached chunks (see "ground chunks")
  drawGround(W, H, R);
  // 3. routes: from each route hex's centre to the edge it shares with each joined neighbour, so
  //    joins meet at edges and bends look natural (dirt roads; railways with ties and rails)
  if (z > 0.25) for (const [i, sx, sy, shown] of visible) {
    if (!shown) continue;
    const t1 = S.tilesByIndex.get(i);
    if (!(t1.route || S.citiesByTile.has(i))) continue;
    const joins = neighbourEdges(i).filter(([n]) => { const t2 = S.tilesByIndex.get(n); return t2 && (t2.route || S.citiesByTile.has(n)) && (t1.route || t2.route); });
    for (const [n, edge] of joins) {
      const t2 = S.tilesByIndex.get(n);
      const [ax, ay] = corner(sx, sy, R, edge), [bx, by] = corner(sx, sy, R, (edge + 1) % 6);
      const mx = (ax + bx) / 2, my = (ay + by) / 2;
      const rail = t1.route === "railway" && t2.route === "railway";
      drawRouteSegment(sx, sy, mx, my, R, rail, i * 7 + n);
    }
    if (t1.route && joins.length && !S.citiesByTile.has(i)) {  // a small hub where branches meet
      ctx.fillStyle = t1.route === "railway" ? "#3d3833" : "#8a6a42";
      ctx.beginPath(); ctx.arc(sx, sy, Math.max(1.5, R * 0.09), 0, Math.PI * 2); ctx.fill();
    }
  }
  // 4. improvements and resources
  for (const [i, sx, sy, shown] of visible) {
    if (!shown) continue;
    const t1 = S.tilesByIndex.get(i);
    if (t1.improvement && z > 0.3) { drawImprovedHex(i, t1.improvement, sx, sy, R); drawImprovement(t1.improvement, sx, sy, R, Math.floor(hash(i, 9) * 6)); }
    if (t1.turret && z > 0.3) drawTurret(t1, sx, sy, R);
    if (t1.resource && t1.visible && z > 0.6) drawResource(t1.resource, sx, sy, R);
  }
  // 4b. territory borders: a line in the owner's colour along every edge where ownership changes,
  //     with a soft glow inside, as in Civ
  if (z > 0.2) drawBorders(visible, R);
  // 5. fog, and a light veil over remembered city hexes not seen right now
  drawFog(visible, R, t);
  for (const [i, sx, sy, shown] of visible) {
    if (shown && !S.tilesByIndex.get(i).visible) { hexPath(ctx, sx, sy, R + 0.6); ctx.fillStyle = "rgba(92,105,118,0.45)"; ctx.fill(); }
  }
  // 5b. Starfall and exploration finds, drawn over the fog (everyone sees the sky)
  drawStarfall(R, t);
  for (const tile of S.view.sites || []) {
    const [sx, sy] = toScreen(...center(tile));
    if (sx < -R || sy < -R || sx > W + R || sy > H + R) continue;
    drawSite(sx, sy, R, t);
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
  for (const [i, sx, sy] of visible) { const c = S.citiesByTile.get(i); if (c) drawOutskirts(c, i, sx, sy, R); }
  for (const [i, sx, sy] of visible) { const c = S.citiesByTile.get(i); if (c) drawCity(c, sx, sy, R, i); }
  for (const [i, sx, sy] of visible) { const us = S.unitsByTile.get(i); if (us) drawUnits(us, sx, sy, R, S.citiesByTile.has(i)); }
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
  // a citizen working the tile: a small figure (the painted improvement itself shows it is built)
  const w = S.view.worked && S.view.worked[i];
  if (w && S.cam.zoom > 0.5) {
    const x = sx - R * 0.5, y = sy - R * 0.38, r = R * 0.13;
    ctx.fillStyle = "rgba(0,0,0,0.35)"; ctx.beginPath(); ctx.ellipse(x, y + r * 1.1, r, r * 0.35, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#f2d38a"; ctx.strokeStyle = "#4a3410"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(x, y - r * 0.9, r * 0.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x - r * 0.9, y + r); ctx.quadraticCurveTo(x, y - r * 0.6, x + r * 0.9, y + r); ctx.closePath(); ctx.fill(); ctx.stroke();
  }
}
function tileOwner(i) {
  const t = S.tilesByIndex.get(i);
  if (!t || t.city == null) return null;
  const c = S.view.cities[String(t.city)];
  return c && c.owner && c.status !== "empty" ? c.owner : null;
}
function drawBorders(visible, R) {
  const glow = [], lines = new Map();
  for (const [i, sx, sy, shown] of visible) {
    if (!shown) continue;
    const own = tileOwner(i);
    if (!own) continue;
    for (const [n, edge] of neighbourEdges(i)) {
      if (tileOwner(n) === own) continue;
      const [ax, ay] = corner(sx, sy, R, edge), [bx, by] = corner(sx, sy, R, (edge + 1) % 6);
      glow.push([own, sx, sy, ax, ay, bx, by]);
      if (!lines.has(own)) lines.set(own, []);
      lines.get(own).push([ax, ay, bx, by, sx, sy]);
    }
  }
  // the inner glow: a band from each border edge fading toward the hex centre
  for (const [own, sx, sy, ax, ay, bx, by] of glow) {
    const col = own === "aliens" ? "#e0362c" : OWNER[own] || "#999";
    const mx = (ax + bx) / 2, my = (ay + by) / 2, f = 0.5;
    const gr = ctx.createLinearGradient(mx, my, mx + (sx - mx) * f, my + (sy - my) * f);
    gr.addColorStop(0, hexA(col, 0.6)); gr.addColorStop(0.35, hexA(col, 0.22)); gr.addColorStop(1, hexA(col, 0));
    ctx.fillStyle = gr; ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
    ctx.lineTo(bx + (sx - bx) * f, by + (sy - by) * f); ctx.lineTo(ax + (sx - ax) * f, ay + (sy - ay) * f); ctx.closePath(); ctx.fill();
  }
  // the border line itself, inset a little so two neighbours' borders sit side by side
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (const [own, segs] of lines) {
    const col = own === "aliens" ? "#e0362c" : OWNER[own] || "#999";
    for (const [w, style] of [[Math.max(4, R * 0.2), "rgba(10,12,16,0.45)"], [Math.max(2.5, R * 0.13), col], [Math.max(1, R * 0.04), "rgba(255,250,230,0.8)"]]) {
      ctx.strokeStyle = style; ctx.lineWidth = w; ctx.beginPath();
      for (const [ax, ay, bx, by, sx, sy] of segs) {
        const k = 0.07;
        ctx.moveTo(ax + (sx - ax) * k, ay + (sy - ay) * k); ctx.lineTo(bx + (sx - bx) * k, by + (sy - by) * k);
      }
      ctx.stroke();
    }
  }
}
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}
// Improvements are painted once per (kind, zoom step) and drawn scaled.
const IMPS = new Map();
function drawImprovement(kind, sx, sy, R, variant = 0) {
  const Rb = zoomStep(R), v = kind === "farm" ? variant % 6 : 0, key = `${kind}|${Rb}|${v}`;
  let c = IMPS.get(key);
  if (!c) {
    c = document.createElement("canvas"); c.width = Math.ceil(Rb * 2.2); c.height = Math.ceil(Rb * 2.2);
    paintImprovement(c.getContext("2d"), kind, c.width / 2, c.height / 2, Rb, v);
    IMPS.set(key, c);
  }
  const s2 = R / Rb;
  ctx.drawImage(c, sx - c.width * s2 / 2, sy - c.height * s2 / 2, c.width * s2, c.height * s2);
}
function paintImprovement(g, kind, cx, cy, R, variant = 0) {
  const rnd = rng(kind.length * 31 + kind.charCodeAt(0) + variant * 977);
  const shadow = (x, y, w) => { g.fillStyle = "rgba(0,0,0,0.25)"; g.beginPath(); g.ellipse(x + w * 0.15, y, w, w * 0.32, 0, 0, Math.PI * 2); g.fill(); };
  if (kind === "farm") {
    // a patchwork of rectangular fields (greens, golds, ploughed browns) at an angle that changes from
    // hex to hex, with hedgerows between fields, crop rows in each and a farmstead
    g.save(); hexPath(g, cx, cy, R * 0.97); g.clip();
    const cols = ["#7fa83a", "#9bb848", "#c9b04a", "#d9c25a", "#6b8f32", "#b89a4a", "#8a6a3a", "#a9c060"];
    g.translate(cx, cy); g.rotate(-0.6 + rnd() * 1.2);
    const fw = R * (0.42 + rnd() * 0.12), fh = R * (0.3 + rnd() * 0.1);
    for (let row = -4; row <= 4; row++) {
      const shift = (rnd() - 0.5) * fw;
      for (let col = -4; col <= 4; col++) {
        const x = col * fw + shift, y = row * fh, w = fw * (0.85 + rnd() * 0.3);
        const c0 = cols[Math.floor(rnd() * cols.length)];
        const fg = g.createLinearGradient(x, y, x + w, y + fh); fg.addColorStop(0, shade(c0, 0.08)); fg.addColorStop(1, shade(c0, -0.12));
        g.fillStyle = fg; g.fillRect(x, y, w, fh);
        g.strokeStyle = "rgba(60,45,20,0.22)"; g.lineWidth = Math.max(0.7, R * 0.012);  // crop rows
        const vertical = rnd() < 0.5;
        for (let q = 1; q < 7; q++) { g.beginPath(); if (vertical) { g.moveTo(x + w * q / 7, y + 1); g.lineTo(x + w * q / 7, y + fh - 1); } else { g.moveTo(x + 1, y + fh * q / 7); g.lineTo(x + w - 1, y + fh * q / 7); } g.stroke(); }
        g.strokeStyle = "rgba(55,75,30,0.75)"; g.lineWidth = Math.max(1, R * 0.03); g.strokeRect(x, y, w, fh);  // hedgerow
      }
    }
    g.restore();
    // the farmstead: a house and a barn with a few trees
    const hx = cx + (rnd() - 0.5) * R * 0.5, hy = cy + (rnd() - 0.5) * R * 0.4, hw = R * 0.2, hh = R * 0.13;
    shadow(hx, hy + hh * 0.6, hw);
    g.fillStyle = "#efe2c4"; g.fillRect(hx - hw / 2, hy - hh / 2, hw, hh);
    g.fillStyle = "#9b3b2a"; g.beginPath(); g.moveTo(hx - hw * 0.62, hy - hh / 2); g.lineTo(hx, hy - hh * 1.3); g.lineTo(hx + hw * 0.62, hy - hh / 2); g.fill();
    g.fillStyle = "#7a2f22"; g.fillRect(hx + hw * 0.6, hy - hh * 0.3, hw * 0.7, hh * 0.8);
    g.fillStyle = "#5a5a5a"; g.fillRect(hx + hw * 0.55, hy - hh * 0.45, hw * 0.8, hh * 0.18);
    g.fillStyle = "#3e6a2a"; for (const [dx, dy] of [[-0.75, 0.2], [-0.55, 0.45], [0.2, 0.55]]) { g.beginPath(); g.arc(hx + dx * hw, hy + dy * hw, hw * 0.22, 0, Math.PI * 2); g.fill(); }
    return;
  }
  if (kind === "hydroponic_plot") {
    // field strips clipped to the hex, a farmhouse and (hydroponics) glass domes
    g.save(); hexPath(g, cx, cy, R * 0.86); g.clip();
    const cols = kind === "farm" ? ["#d9b84a", "#a9b83e", "#c7a23c", "#8fae3a", "#e0c463"] : ["#6fbf7a", "#4f9e5c", "#88d08f"];
    g.translate(cx, cy); g.rotate(-0.45);
    for (let k = -5; k <= 5; k++) {
      g.fillStyle = cols[(k + 10) % cols.length]; g.fillRect(-R * 1.4, k * R * 0.24, R * 2.8, R * 0.22);
      g.strokeStyle = "rgba(90,60,20,0.35)"; g.lineWidth = Math.max(1, R * 0.02);
      for (let x = -R * 1.4; x < R * 1.4; x += R * 0.12) { g.beginPath(); g.moveTo(x, k * R * 0.24 + 0.02 * R); g.lineTo(x, k * R * 0.24 + 0.2 * R); g.stroke(); }
    }
    g.restore();
    hexPath(g, cx, cy, R * 0.86); g.strokeStyle = "rgba(110,80,30,0.55)"; g.lineWidth = Math.max(1, R * 0.04); g.stroke();
    if (kind === "farm") {
      const hx = cx + R * 0.3, hy = cy - R * 0.25, hw = R * 0.26, hh = R * 0.18;
      shadow(hx, hy + hh * 0.5, hw * 0.7);
      g.fillStyle = "#efe2c4"; g.fillRect(hx - hw / 2, hy - hh / 2, hw, hh);
      g.fillStyle = "#9b3b2a"; g.beginPath(); g.moveTo(hx - hw * 0.62, hy - hh / 2); g.lineTo(hx, hy - hh * 1.25); g.lineTo(hx + hw * 0.62, hy - hh / 2); g.fill();
      g.fillStyle = "#5a3a1c"; g.fillRect(hx - hw * 0.1, hy - hh * 0.05, hw * 0.2, hh * 0.55);
    } else {
      for (const [dx, dy] of [[-0.3, -0.2], [0.25, -0.05], [-0.05, 0.3]]) {
        const x = cx + dx * R, y = cy + dy * R, r = R * 0.18;
        shadow(x, y + r * 0.3, r);
        const dg = g.createRadialGradient(x - r * 0.3, y - r * 0.4, 1, x, y, r);
        dg.addColorStop(0, "rgba(230,255,240,0.95)"); dg.addColorStop(1, "rgba(120,190,170,0.6)");
        g.fillStyle = dg; g.beginPath(); g.arc(x, y, r, Math.PI, 0); g.closePath(); g.fill();
        g.strokeStyle = "rgba(60,110,90,0.8)"; g.lineWidth = Math.max(1, R * 0.02); g.stroke();
      }
    }
    return;
  }
  if (kind === "mine") {
    // a pithead: spoil heaps, a timber headframe with its winding wheel, a shed, rails and an ore cart
    for (const [dx, dy, sz] of [[-0.48, 0.18, 1.1], [0.5, 0.3, 0.9], [-0.15, 0.5, 0.7]]) {
      const x = cx + dx * R, y = cy + dy * R;
      shadow(x, y, R * 0.28 * sz);
      const hg = g.createLinearGradient(x - R * 0.25 * sz, y - R * 0.2 * sz, x + R * 0.2 * sz, y);
      hg.addColorStop(0, "#9a8a76"); hg.addColorStop(1, "#4d4136");
      g.fillStyle = hg; g.beginPath(); g.moveTo(x - R * 0.3 * sz, y); g.quadraticCurveTo(x - R * 0.05 * sz, y - R * 0.36 * sz, x + R * 0.3 * sz, y); g.closePath(); g.fill();
      g.fillStyle = "rgba(40,30,22,0.5)"; for (let q = 0; q < 5; q++) { g.beginPath(); g.arc(x + (rnd() - 0.5) * R * 0.35 * sz, y - rnd() * R * 0.12 * sz, R * 0.02, 0, Math.PI * 2); g.fill(); }
    }
    const x = cx + R * 0.02, y = cy + R * 0.12;
    // shed beside the frame
    g.fillStyle = "rgba(0,0,0,0.3)"; g.fillRect(x + R * 0.12, y - R * 0.02, R * 0.36, R * 0.08);
    g.fillStyle = "#7a4a30"; g.fillRect(x + R * 0.1, y - R * 0.2, R * 0.32, R * 0.2);
    g.fillStyle = "#4d4f55"; g.beginPath(); g.moveTo(x + R * 0.06, y - R * 0.2); g.lineTo(x + R * 0.26, y - R * 0.34); g.lineTo(x + R * 0.46, y - R * 0.2); g.fill();
    g.fillStyle = "#e8c070"; g.fillRect(x + R * 0.16, y - R * 0.13, R * 0.06, R * 0.06);
    // the headframe
    shadow(x - R * 0.1, y, R * 0.2);
    g.strokeStyle = "#5c3d22"; g.lineWidth = Math.max(1.5, R * 0.05); g.lineCap = "round";
    g.beginPath(); g.moveTo(x - R * 0.28, y); g.lineTo(x - R * 0.12, y - R * 0.78); g.lineTo(x + R * 0.04, y); g.moveTo(x - R * 0.12, y - R * 0.78); g.lineTo(x + R * 0.12, y - R * 0.22); g.stroke();
    g.lineWidth = Math.max(1, R * 0.03);
    for (const f of [0.3, 0.55]) { g.beginPath(); g.moveTo(x - R * 0.28 + R * 0.16 * f, y - R * 0.78 * f); g.lineTo(x + R * 0.04 - R * 0.16 * f, y - R * 0.78 * f); g.stroke(); }
    g.strokeStyle = "#2b2622"; g.lineWidth = Math.max(1.2, R * 0.035);
    g.beginPath(); g.arc(x - R * 0.12, y - R * 0.78, R * 0.11, 0, Math.PI * 2); g.stroke();
    g.beginPath(); for (let a = 0; a < 4; a++) { g.moveTo(x - R * 0.12, y - R * 0.78); g.lineTo(x - R * 0.12 + Math.cos(a * Math.PI / 2) * R * 0.11, y - R * 0.78 + Math.sin(a * Math.PI / 2) * R * 0.11); } g.stroke();
    // shaft mouth, rails and a loaded cart
    g.fillStyle = "#14100c"; g.beginPath(); g.ellipse(x - R * 0.12, y + R * 0.02, R * 0.12, R * 0.05, 0, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "#6d6862"; g.lineWidth = Math.max(1, R * 0.025);
    g.beginPath(); g.moveTo(x - R * 0.06, y + R * 0.06); g.lineTo(x + R * 0.1, y + R * 0.62); g.moveTo(x + R * 0.06, y + R * 0.05); g.lineTo(x + R * 0.24, y + R * 0.6); g.stroke();
    g.strokeStyle = "#5c3d22"; for (let q = 0; q < 5; q++) { const f = 0.15 + q * 0.18; g.beginPath(); g.moveTo(x - R * 0.06 + R * 0.16 * f - R * 0.03, y + R * 0.06 + R * 0.56 * f); g.lineTo(x + R * 0.06 + R * 0.18 * f + R * 0.03, y + R * 0.05 + R * 0.55 * f); g.stroke(); }
    const kx = x + R * 0.14, ky = y + R * 0.4;
    g.fillStyle = "#3b3632"; g.fillRect(kx - R * 0.12, ky - R * 0.1, R * 0.24, R * 0.12);
    g.fillStyle = "#c9a35c"; g.beginPath(); g.ellipse(kx, ky - R * 0.1, R * 0.12, R * 0.06, 0, Math.PI, 0); g.fill();
    g.fillStyle = "#1b1612"; for (const d of [-0.08, 0.08]) { g.beginPath(); g.arc(kx + d * R, ky + R * 0.03, R * 0.03, 0, Math.PI * 2); g.fill(); }
    return;
  }
  if (kind === "extractor") {
    // an oil derrick with a pump
    const x = cx, y = cy + R * 0.35;
    shadow(x, y, R * 0.3);
    g.strokeStyle = "#2b2622"; g.lineWidth = Math.max(1.5, R * 0.05);
    g.beginPath(); g.moveTo(x - R * 0.22, y); g.lineTo(x, y - R * 0.85); g.lineTo(x + R * 0.22, y); g.stroke();
    for (const f of [0.25, 0.5, 0.72]) { g.beginPath(); g.moveTo(x - R * 0.22 * (1 - f), y - R * 0.85 * f); g.lineTo(x + R * 0.22 * (1 - f), y - R * 0.85 * f); g.stroke(); }
    g.fillStyle = "#c0392b"; g.fillRect(x + R * 0.18, y - R * 0.22, R * 0.4, R * 0.08);
    g.fillStyle = "#3b3632"; g.beginPath(); g.arc(x + R * 0.38, y - R * 0.12, R * 0.08, 0, Math.PI * 2); g.fill();
    return;
  }
  if (kind === "solar_array") {
    g.save(); g.translate(cx, cy); g.rotate(-0.3);
    for (let r = -1; r <= 1; r++) for (let c = -1; c <= 1; c++) {
      const x = c * R * 0.42, y = r * R * 0.32;
      g.fillStyle = "rgba(0,0,0,0.25)"; g.fillRect(x - R * 0.17, y - R * 0.08, R * 0.38, R * 0.24);
      const pg = g.createLinearGradient(x, y - R * 0.12, x, y + R * 0.12);
      pg.addColorStop(0, "#5aa0d8"); pg.addColorStop(1, "#1d3f73");
      g.fillStyle = pg; g.fillRect(x - R * 0.18, y - R * 0.12, R * 0.36, R * 0.22);
      g.strokeStyle = "rgba(220,240,255,0.6)"; g.lineWidth = 1; g.strokeRect(x - R * 0.18, y - R * 0.12, R * 0.36, R * 0.22);
    }
    g.restore();
    return;
  }
  if (kind === "wind_turbines") {
    for (const [dx, dy, s] of [[-0.3, 0.1, 1], [0.32, 0.25, 0.85], [0.0, -0.25, 0.75]]) {
      const x = cx + dx * R, y = cy + dy * R + R * 0.3, h = R * 0.75 * s;
      shadow(x, y, R * 0.12);
      g.strokeStyle = "#e8ecef"; g.lineWidth = Math.max(1.5, R * 0.045);
      g.beginPath(); g.moveTo(x, y); g.lineTo(x, y - h); g.stroke();
      const a0 = rnd() * Math.PI * 2;
      g.lineWidth = Math.max(1, R * 0.035);
      for (let b = 0; b < 3; b++) { const a = a0 + b * Math.PI * 2 / 3; g.beginPath(); g.moveTo(x, y - h); g.lineTo(x + Math.cos(a) * R * 0.28 * s, y - h + Math.sin(a) * R * 0.28 * s); g.stroke(); }
      g.fillStyle = "#cfd6dc"; g.beginPath(); g.arc(x, y - h, R * 0.04, 0, Math.PI * 2); g.fill();
    }
    return;
  }
  if (kind === "military_base" || kind === "minefield") {
    // sandbag ring and a flag (minefields: warning posts)
    if (kind === "military_base") {
      // a sandbagged compound: barracks, a watchtower, a parked vehicle and a flag
      const ey = cy + R * 0.12;
      g.fillStyle = "rgba(90,80,55,0.35)"; g.beginPath(); g.ellipse(cx, ey, R * 0.66, R * 0.44, 0, 0, Math.PI * 2); g.fill();
      for (let q = 0; q < 26; q++) {  // the sandbag wall, back half first then front
        const a = (q / 26) * Math.PI * 2, bx = cx + Math.cos(a) * R * 0.66, by = ey + Math.sin(a) * R * 0.44;
        if (Math.abs(a - Math.PI * 1.5) < 0.25) continue;  // the gate at the back
        g.fillStyle = q % 2 ? "#c2a878" : "#a88f60"; g.beginPath(); g.ellipse(bx, by, R * 0.09, R * 0.055, a, 0, Math.PI * 2); g.fill();
        g.strokeStyle = "rgba(60,48,30,0.5)"; g.lineWidth = 0.7; g.stroke();
      }
      const hut = (x, y, w, d, roof) => {
        g.fillStyle = "rgba(0,0,0,0.3)"; g.fillRect(x - w / 2 + R * 0.04, y, w, d * 0.4);
        g.fillStyle = "#56603f"; g.fillRect(x - w / 2, y - d, w, d);
        g.fillStyle = roof; g.beginPath(); g.moveTo(x - w / 2 - R * 0.02, y - d); g.quadraticCurveTo(x, y - d - R * 0.14, x + w / 2 + R * 0.02, y - d); g.fill();
        g.strokeStyle = "rgba(20,24,14,0.6)"; g.lineWidth = 0.8; g.strokeRect(x - w / 2, y - d, w, d);
      };
      hut(cx - R * 0.22, ey - R * 0.08, R * 0.42, R * 0.14, "#6b7550");
      hut(cx + R * 0.2, ey + R * 0.16, R * 0.36, R * 0.12, "#5e6847");
      // a parked armoured car
      const vx = cx - R * 0.3, vy = ey + R * 0.22;
      g.fillStyle = "rgba(0,0,0,0.3)"; g.fillRect(vx - R * 0.1, vy, R * 0.24, R * 0.04);
      g.fillStyle = "#4b5536"; g.fillRect(vx - R * 0.12, vy - R * 0.08, R * 0.24, R * 0.08);
      g.fillStyle = "#3a4229"; g.fillRect(vx - R * 0.05, vy - R * 0.13, R * 0.1, R * 0.05);
      g.fillStyle = "#1b1b1b"; for (const d of [-0.08, 0.07]) { g.beginPath(); g.arc(vx + d * R, vy, R * 0.03, 0, Math.PI * 2); g.fill(); }
      // watchtower and flag
      const tx = cx + R * 0.42, ty = ey - R * 0.12;
      g.strokeStyle = "#5c3d22"; g.lineWidth = Math.max(1, R * 0.03);
      g.beginPath(); g.moveTo(tx - R * 0.07, ty); g.lineTo(tx - R * 0.04, ty - R * 0.42); g.moveTo(tx + R * 0.07, ty); g.lineTo(tx + R * 0.04, ty - R * 0.42); g.moveTo(tx - R * 0.07, ty); g.lineTo(tx + R * 0.05, ty - R * 0.2); g.stroke();
      g.fillStyle = "#6b4a2a"; g.fillRect(tx - R * 0.08, ty - R * 0.5, R * 0.16, R * 0.09);
      g.fillStyle = "#4d4f55"; g.beginPath(); g.moveTo(tx - R * 0.1, ty - R * 0.5); g.lineTo(tx, ty - R * 0.58); g.lineTo(tx + R * 0.1, ty - R * 0.5); g.fill();
      g.strokeStyle = "#3a2f22"; g.beginPath(); g.moveTo(cx - R * 0.05, ey - R * 0.22); g.lineTo(cx - R * 0.05, ey - R * 0.7); g.stroke();
      g.fillStyle = "#c0392b"; g.beginPath(); g.moveTo(cx - R * 0.05, ey - R * 0.7); g.quadraticCurveTo(cx + R * 0.1, ey - R * 0.72, cx + R * 0.24, ey - R * 0.62); g.lineTo(cx - R * 0.05, ey - R * 0.54); g.fill();
    } else {
      for (const [dx, dy] of [[-0.45, -0.2], [0.4, -0.3], [-0.2, 0.4], [0.35, 0.35]]) {
        const x = cx + dx * R, y = cy + dy * R;
        g.strokeStyle = "#3a2f22"; g.lineWidth = Math.max(1, R * 0.03); g.beginPath(); g.moveTo(x, y); g.lineTo(x, y - R * 0.25); g.stroke();
        g.fillStyle = "#e6c13a"; g.beginPath(); g.moveTo(x - R * 0.08, y - R * 0.25); g.lineTo(x + R * 0.08, y - R * 0.25); g.lineTo(x, y - R * 0.38); g.fill();
      }
    }
    return;
  }
  if (kind === "radio_beacon" || kind === "sensor_mast") {
    const x = cx, y = cy + R * 0.35, h = R * (kind === "sensor_mast" ? 0.95 : 0.75);
    shadow(x, y, R * 0.14);
    g.strokeStyle = "#9aa4ad"; g.lineWidth = Math.max(1.5, R * 0.04);
    g.beginPath(); g.moveTo(x - R * 0.1, y); g.lineTo(x, y - h); g.lineTo(x + R * 0.1, y); g.stroke();
    g.strokeStyle = "rgba(200,141,242,0.85)"; g.lineWidth = Math.max(1, R * 0.035);
    for (const r of [0.14, 0.26]) { g.beginPath(); g.arc(x, y - h, R * r, Math.PI * 1.15, Math.PI * 1.85); g.stroke(); }
    g.fillStyle = "#e0362c"; g.beginPath(); g.arc(x, y - h, R * 0.04, 0, Math.PI * 2); g.fill();
    return;
  }
  // anything else: a small marker
  g.fillStyle = "#3a5a7a"; g.fillRect(cx - R * 0.15, cy - R * 0.1, R * 0.3, R * 0.2);
}
function drawRouteSegment(x1, y1, x2, y2, R, rail, seed) {
  const bend = (hash(seed, 9) - 0.5) * R * 0.12;
  const mx = (x1 + x2) / 2 + bend, my = (y1 + y2) / 2 - bend;
  if (rail) {
    ctx.strokeStyle = "#4a3a2a"; ctx.lineWidth = Math.max(2, R * 0.16); ctx.lineCap = "butt"; ctx.setLineDash([Math.max(1, R * 0.03), Math.max(2, R * 0.07)]);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(mx, my, x2, y2); ctx.stroke(); ctx.setLineDash([]);
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1, nx = -dy / len * R * 0.05, ny = dx / len * R * 0.05;
    ctx.strokeStyle = "#8d949b"; ctx.lineWidth = Math.max(1, R * 0.03);
    for (const sgn of [-1, 1]) { ctx.beginPath(); ctx.moveTo(x1 + nx * sgn, y1 + ny * sgn); ctx.quadraticCurveTo(mx + nx * sgn, my + ny * sgn, x2 + nx * sgn, y2 + ny * sgn); ctx.stroke(); }
    return;
  }
  ctx.lineCap = "round";
  ctx.strokeStyle = "rgba(70,50,30,0.55)"; ctx.lineWidth = Math.max(2.5, R * 0.17);
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(mx, my, x2, y2); ctx.stroke();
  ctx.strokeStyle = "#b08a58"; ctx.lineWidth = Math.max(1.5, R * 0.11);
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(mx, my, x2, y2); ctx.stroke();
  ctx.strokeStyle = "rgba(240,215,160,0.45)"; ctx.lineWidth = Math.max(1, R * 0.03);
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(mx, my, x2, y2); ctx.stroke();
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

// City renders (visuals round 2): Blender towns from Poly Haven CC0 textures (web/static/cities).
const CITY_IMG = {};
for (let t = 0; t < 4; t++) for (let v = 0; v < 2; v++) CITY_IMG[`city_${t}_${v}`] = null;
for (let v = 0; v < 3; v++) CITY_IMG[`suburb_${v}`] = null;
for (const name of Object.keys(CITY_IMG)) {
  const im = new Image(); im.onload = () => { CITY_SPRITES.clear(); OUTSKIRTS.clear(); if (typeof S !== "undefined") S.dirty = true; };
  im.src = `cities/${name}.png`; CITY_IMG[name] = im;
}
const cityArt = (name) => { const im = CITY_IMG[name]; return im && im.complete && im.naturalWidth ? im : null; };
const CITY_ART_PENDING = () => Object.values(CITY_IMG).some((im) => !im.complete);
// Cities (visuals pass 1): painted once per look and zoom step, drawn scaled. Four modern tiers by
// population (houses, mid-rise town, towers, skyscraper metropolis), a domed capitol and flag for
// capitals, a concrete ring for walls and a dome for plasma shields; alien hives grow organic
// spires; lost cities are greyed or rubble.
const CITY_SPRITES = new Map();
function cityTier(pop) { return pop <= 2 ? 0 : pop <= 5 ? 1 : pop <= 9 ? 2 : 3; }
function drawCity(c, sx, sy, R, i) {
  const Rb = zoomStep(R), tier = cityTier(c.pop || 1);
  const owner = c.owner && c.owner !== "aliens" ? OWNER[c.owner] : "#888";
  const walls = (c.buildings || []).includes("defence_perimeter"), shield = (c.buildings || []).includes("plasma_shield");
  const key = `${c.status}|${tier}|${owner}|${c.is_capital ? 1 : 0}|${walls ? 1 : 0}${shield ? 1 : 0}|${Rb}|${i % 3}`;
  let sp = CITY_SPRITES.get(key);
  if (!sp) {
    if (CITY_SPRITES.size > 400) CITY_SPRITES.clear();
    sp = document.createElement("canvas"); sp.width = Math.ceil(Rb * 3.2); sp.height = Math.ceil(Rb * 3.6);
    const g = sp.getContext("2d"), cx = sp.width / 2, cy = sp.height - Rb * 1.45, rnd = rng(i % 3 * 97 + tier * 13 + 7);
    const art = cityArt(`city_${tier}_${i % 2}`);
    if (c.status === "overrun") paintHive(g, cx, cy, Rb, tier, rnd);
    else if (c.status === "empty") paintRuins(g, cx, cy, Rb, rnd);
    else paintCity(g, cx, cy, Rb, tier, owner, c.is_capital, walls, shield, c.status === "dormant", rnd, art);
    if (art || c.status === "overrun" || c.status === "empty" || !CITY_ART_PENDING()) CITY_SPRITES.set(key, sp);
  }
  const k = R / Rb;
  ctx.drawImage(sp, sx - sp.width * k / 2, sy - (sp.height - Rb * 1.45) * k, sp.width * k, sp.height * k);
  if (c.status === "overrun" && R >= 10) drawHiveLife(sx, sy, R, i, tier);
}
// A hive breathes: a slow pulse of light from its heart and spores drifting up from the spires.
function drawHiveLife(sx, sy, R, i, tier) {
  const t = performance.now(), pulse = 0.5 + 0.5 * Math.sin(t / 700 + i);
  ctx.save(); ctx.globalCompositeOperation = "lighter";
  const gg = ctx.createRadialGradient(sx, sy - R * 0.1, 0, sx, sy - R * 0.1, R * (0.7 + tier * 0.12));
  gg.addColorStop(0, `rgba(255,110,50,${0.18 + pulse * 0.22})`); gg.addColorStop(1, "rgba(255,60,20,0)");
  ctx.fillStyle = gg; ctx.beginPath(); ctx.ellipse(sx, sy - R * 0.1, R * (0.75 + tier * 0.12), R * (0.55 + tier * 0.1), 0, 0, Math.PI * 2); ctx.fill();
  for (let q = 0; q < 4 + tier * 2; q++) {
    const h0 = hash(i, q + 40), ph = (t / 3200 + h0) % 1;
    const x = sx + (hash(i, q + 60) - 0.5) * R * 1.1 + Math.sin(t / 900 + q) * R * 0.06, y = sy - R * 0.2 - ph * R * 1.1;
    ctx.fillStyle = `rgba(255,190,110,${(1 - ph) * 0.8})`; ctx.beginPath(); ctx.arc(x, y, Math.max(1, R * 0.03 * (1 - ph * 0.5)), 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}
// Outskirts (visuals pass 2): towns and cities spill suburbs onto open neighbouring land; a hive's
// creep spreads onto its neighbours instead. Chosen per city from a hash, so they stay put.
const OUTSKIRTS = new Map();
function drawOutskirts(c, i, sx, sy, R) {
  if (R < 9 || c.status === "empty" || c.status === "dormant") return;
  const tier = cityTier(c.pop || 1), hive = c.status === "overrun";
  const want = hive ? [1, 2, 3, 4][tier] : [0, 1, 3, 5][tier];
  if (!want) return;
  const [cx0, cy0] = center(i), z = R / R0;
  const options = neighbourEdges(i).map(([n]) => n).filter((n) => {
    const t = S.tilesByIndex.get(n);
    return t && !isWater(t) && t.elevation !== "mountain" && !t.improvement && !S.citiesByTile.has(n);
  }).sort((a, b) => hash(a, i) - hash(b, i)).slice(0, want);
  const Rb = zoomStep(R), k = R / Rb;
  for (const n of options) {
    const variant = Math.floor(hash(n, 11) * 4), key = `${hive ? "h" : "s"}|${tier}|${variant}|${Rb}`;
    let sp = OUTSKIRTS.get(key);
    if (!sp) {
      if (OUTSKIRTS.size > 300) OUTSKIRTS.clear();
      sp = document.createElement("canvas"); sp.width = Math.ceil(Rb * 2); sp.height = Math.ceil(Rb * 2);
      const g = sp.getContext("2d"), rnd = rng(variant * 71 + tier * 13 + (hive ? 5 : 1));
      const art = hive ? null : cityArt(`suburb_${variant % 3}`);
      if (hive) paintCreep(g, sp.width / 2, sp.height / 2, Rb, rnd);
      else if (art) { const s = Rb * 2.6; g.drawImage(art, sp.width / 2 - s / 2, sp.height / 2 - s * 0.62, s, s); }
      else paintSuburb(g, sp.width / 2, sp.height / 2, Rb, tier, rnd);
      OUTSKIRTS.set(key, sp);
    }
    const [nx, ny] = center(n);
    // sit a little toward the city, so the suburb joins it
    const x = sx + (nx - cx0) * z * 0.72, y = sy + (ny - cy0) * z * 0.72;
    ctx.drawImage(sp, x - sp.width * k / 2, y - sp.height * k / 2, sp.width * k, sp.height * k);
  }
}
function paintSuburb(g, cx, cy, R, tier, rnd) {
  const pg = g.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 0.6);
  pg.addColorStop(0, "rgba(122,112,96,0.85)"); pg.addColorStop(0.65, "rgba(112,102,86,0.6)"); pg.addColorStop(1, "rgba(100,90,74,0)");
  g.fillStyle = pg; g.beginPath(); g.ellipse(cx, cy, R * 0.8, R * 0.58, 0, 0, Math.PI * 2); g.fill();
  const blocks = [];
  for (let q = 0; q < 10 + tier * 3; q++) {
    const a = rnd() * Math.PI * 2, d = Math.sqrt(rnd()) * 0.6;
    blocks.push([cx + Math.cos(a) * R * d, cy + Math.sin(a) * R * d * 0.66, rnd() < 0.2 * tier ? "mid" : rnd() < 0.15 ? "tree" : "house"]);
  }
  blocks.sort((a, b) => a[1] - b[1]);
  for (const [x, y, kind] of blocks) {
    const [front, side, top] = FACADES[Math.floor(rnd() * FACADES.length)];
    if (kind === "tree") { g.fillStyle = "#3e6a32"; g.beginPath(); g.arc(x, y - R * 0.05, R * 0.06, 0, Math.PI * 2); g.fill(); continue; }
    const w = R * (0.14 + rnd() * 0.06), h = kind === "mid" ? R * (0.18 + rnd() * 0.12) : R * (0.08 + rnd() * 0.05);
    box(g, x, y, w, w * 0.8, h, top, front, side);
    if (kind === "house") {
      g.fillStyle = ROOFS[Math.floor(rnd() * ROOFS.length)]; const o = w * 0.28;
      g.beginPath(); g.moveTo(x - w / 2 - 1, y - h); g.lineTo(x - w / 2 + o, y - h - o * 1.6); g.lineTo(x + w / 2 + o, y - h - o * 1.6); g.lineTo(x + w / 2 + 1, y - h); g.closePath(); g.fill();
    } else windows(g, x, y, w, h, "rgba(50,60,75,0.5)", rnd);
  }
}
function paintCreep(g, cx, cy, R, rnd) {
  const cg = g.createRadialGradient(cx, cy, R * 0.05, cx, cy, R * 0.62);
  cg.addColorStop(0, "rgba(80,18,22,0.85)"); cg.addColorStop(0.6, "rgba(60,14,18,0.55)"); cg.addColorStop(1, "rgba(40,8,10,0)");
  g.fillStyle = cg; g.beginPath(); g.ellipse(cx, cy, R * 0.66, R * 0.48, 0, 0, Math.PI * 2); g.fill();
  g.strokeStyle = "rgba(255,120,60,0.45)"; g.lineWidth = Math.max(1, R * 0.02);
  for (let q = 0; q < 6; q++) {
    const a = rnd() * Math.PI * 2, l = R * (0.3 + rnd() * 0.3);
    g.beginPath(); g.moveTo(cx, cy); g.quadraticCurveTo(cx + Math.cos(a + 0.5) * l * 0.5, cy + Math.sin(a + 0.5) * l * 0.35, cx + Math.cos(a) * l, cy + Math.sin(a) * l * 0.65); g.stroke();
  }
  for (let q = 0; q < 4; q++) {  // small spires and pods
    const x = cx + (rnd() - 0.5) * R * 0.7, y = cy + (rnd() - 0.5) * R * 0.4, h = R * (0.15 + rnd() * 0.2), w = R * 0.05;
    const sg = g.createLinearGradient(x - w, 0, x + w, 0); sg.addColorStop(0, "#5a1418"); sg.addColorStop(0.5, "#9b2a2a"); sg.addColorStop(1, "#2e0a0c");
    g.fillStyle = sg; g.beginPath(); g.moveTo(x - w, y); g.quadraticCurveTo(x - w * 0.4, y - h * 0.6, x, y - h); g.quadraticCurveTo(x + w * 0.4, y - h * 0.5, x + w, y); g.fill();
    const eg = g.createRadialGradient(x + R * 0.08, y, 0, x + R * 0.08, y, R * 0.05); eg.addColorStop(0, "#ffb37a"); eg.addColorStop(1, "#7a2a1c");
    g.fillStyle = eg; g.beginPath(); g.ellipse(x + R * 0.08, y, R * 0.04, R * 0.05, 0, 0, Math.PI * 2); g.fill();
  }
}
function box(g, x, y, w, d, h, top, front, side, line = "rgba(30,26,22,0.55)") {
  // an extruded block seen from above-front: footprint w x d at (x, y) (bottom-centre), height h
  const o = d * 0.35;
  g.fillStyle = "rgba(20,16,12,0.32)"; g.beginPath(); g.moveTo(x - w / 2, y); g.lineTo(x + w / 2 + h * 0.45, y - h * 0.1); g.lineTo(x + w / 2 + h * 0.45 + o, y - o - h * 0.1); g.lineTo(x + w / 2 + o, y - o); g.closePath(); g.fill();
  g.fillStyle = front; g.fillRect(x - w / 2, y - h, w, h);
  g.fillStyle = side; g.beginPath(); g.moveTo(x + w / 2, y - h); g.lineTo(x + w / 2 + o, y - h - o); g.lineTo(x + w / 2 + o, y - o); g.lineTo(x + w / 2, y); g.closePath(); g.fill();
  g.fillStyle = top; g.beginPath(); g.moveTo(x - w / 2, y - h); g.lineTo(x - w / 2 + o, y - h - o); g.lineTo(x + w / 2 + o, y - h - o); g.lineTo(x + w / 2, y - h); g.closePath(); g.fill();
  g.strokeStyle = line; g.lineWidth = 0.7; g.beginPath();
  g.moveTo(x - w / 2, y); g.lineTo(x - w / 2, y - h); g.lineTo(x - w / 2 + o, y - h - o); g.lineTo(x + w / 2 + o, y - h - o); g.lineTo(x + w / 2 + o, y - o); g.lineTo(x + w / 2, y); g.closePath();
  g.moveTo(x + w / 2, y); g.lineTo(x + w / 2, y - h); g.lineTo(x - w / 2, y - h); g.moveTo(x + w / 2, y - h); g.lineTo(x + w / 2 + o, y - h - o); g.stroke();
}
function windows(g, x, y, w, h, color, rnd) {
  g.fillStyle = color;
  const rows = Math.max(1, Math.floor(h / Math.max(2.5, w * 0.22))), cols = Math.max(1, Math.floor(w / 3.2));
  for (let r = 0; r < rows; r++) for (let q = 0; q < cols; q++) {
    if (rnd() < 0.25) continue;
    g.fillRect(x - w / 2 + (q + 0.3) * (w / cols), y - h + (r + 0.35) * (h / rows), Math.max(1, w / cols * 0.45), Math.max(1, h / rows * 0.35));
  }
}
const FACADES = [["#e8dcc0", "#cdbf9f", "#f4ead2"], ["#c98e6a", "#a8704f", "#d9a582"], ["#b5654e", "#8f4b38", "#c97c64"],
  ["#c9c4b8", "#a6a195", "#dcd8cd"], ["#d8c08e", "#b49c6c", "#e6d3a8"], ["#9fb0b8", "#7d8f98", "#b7c6cd"]];
const ROOFS = ["#6e3a2c", "#8a4a35", "#5b5f66", "#4f5a4a", "#7a6450", "#3f4650"];
function paintCity(g, cx, cy, R, tier, owner, capital, walls, shield, dormant, rnd, art = null) {
  const spread = [0.8, 0.9, 1.0, 1.1][tier];
  const rx = R * spread * 1.12, ry = R * spread * 0.8;
  if (art) {  // a Blender render (hex centre 62% down a 3.2-hex frame); walls, capitol and shield go over it
    const s = R * 3.2;
    g.filter = dormant ? "grayscale(0.85) brightness(0.8)" : "saturate(1.35) contrast(1.18) brightness(1.12)";
    g.drawImage(art, cx - s / 2, cy - s * 0.62, s, s); g.filter = "none";
    paintCityExtras(g, cx, cy, R, rx, ry, owner, capital, walls, shield, dormant);
    return;
  }
  // the district: worn paving fading into the land, blocks of streets
  const pg = g.createRadialGradient(cx, cy, R * 0.15, cx, cy, rx);
  pg.addColorStop(0, dormant ? "rgba(96,92,86,0.95)" : "rgba(122,112,96,0.95)"); pg.addColorStop(0.55, dormant ? "rgba(84,80,74,0.8)" : "rgba(108,98,82,0.8)"); pg.addColorStop(1, "rgba(100,90,74,0)");
  g.fillStyle = pg; g.beginPath(); g.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2); g.fill();
  g.save(); g.beginPath(); g.ellipse(cx, cy, rx * 0.86, ry * 0.86, 0, 0, Math.PI * 2); g.clip();
  g.strokeStyle = "rgba(205,195,175,0.16)"; g.lineWidth = Math.max(1, R * 0.045);
  for (let k = -2; k <= 2; k++) {
    const wob = (rnd() - 0.5) * R * 0.08;
    g.beginPath(); g.moveTo(cx - rx, cy + k * R * 0.27 + wob); g.quadraticCurveTo(cx, cy + k * R * 0.27 - R * 0.08, cx + rx, cy + k * R * 0.27 - R * 0.12 - wob); g.stroke();
    g.beginPath(); g.moveTo(cx + k * R * 0.36 + wob, cy - ry); g.lineTo(cx + k * R * 0.36 + R * 0.18, cy + ry); g.stroke();
  }
  g.restore();
  if (walls) {  // a concrete perimeter with towers
    g.strokeStyle = "rgba(30,26,22,0.6)"; g.lineWidth = Math.max(3, R * 0.11);
    g.beginPath(); g.ellipse(cx, cy + R * 0.06, rx * 0.98, ry * 0.98, 0, 0, Math.PI * 2); g.stroke();
    g.strokeStyle = "#9b958a"; g.lineWidth = Math.max(2, R * 0.08);
    g.beginPath(); g.ellipse(cx, cy + R * 0.04, rx * 0.98, ry * 0.98, 0, 0, Math.PI * 2); g.stroke();
    g.strokeStyle = "#c8c1b2"; g.lineWidth = Math.max(1, R * 0.025);
    g.beginPath(); g.ellipse(cx, cy + R * 0.01, rx * 0.98, ry * 0.98, 0, Math.PI, 0); g.stroke();
  }
  // buildings, back to front; taller toward the centre and with the tier
  const count = [16, 24, 32, 42][tier];
  const blocks = [];
  for (let k = 0; k < count; k++) {
    const a = rnd() * Math.PI * 2, d = Math.pow(rnd(), 0.6) * spread * 0.86;
    const x = cx + Math.cos(a) * R * d, y = cy + Math.sin(a) * R * d * 0.66 + R * 0.06;
    const central = 1 - d / spread;
    let kind = tier === 0 && rnd() < 0.18 ? "tree" : "house";
    if (tier >= 1 && rnd() < 0.3 + central * 0.6) kind = "mid";
    if (tier >= 2 && central > 0.3 && rnd() < 0.5) kind = "tower";
    if (tier >= 3 && central > 0.45 && rnd() < 0.65) kind = "sky";
    blocks.push([x, y, kind, Math.floor(rnd() * FACADES.length), Math.floor(rnd() * ROOFS.length)]);
  }
  blocks.sort((a, b) => a[1] - b[1]);
  for (const [x, y, kind, fi, ri] of blocks) {
    const [front, side, top] = FACADES[fi];
    if (dormant) { box(g, x, y, R * 0.17, R * 0.13, R * 0.1, "#8d8880", "#a39e96", "#76716a"); continue; }
    if (kind === "tree") {
      g.fillStyle = "#3e6a32"; g.beginPath(); g.arc(x, y - R * 0.06, R * 0.07, 0, Math.PI * 2); g.fill();
      g.fillStyle = "#5c8a45"; g.beginPath(); g.arc(x - R * 0.02, y - R * 0.08, R * 0.04, 0, Math.PI * 2); g.fill();
    } else if (kind === "house") {
      const w = R * ((tier ? 0.14 : 0.17) + rnd() * 0.07), h = R * (0.08 + rnd() * 0.05);
      box(g, x, y, w, w * 0.8, h, top, front, side);
      g.fillStyle = ROOFS[ri]; g.strokeStyle = "rgba(30,20,15,0.6)"; g.lineWidth = 0.7;
      const o = w * 0.28;
      g.beginPath(); g.moveTo(x - w / 2 - 1, y - h); g.lineTo(x - w / 2 + o, y - h - o * 1.6); g.lineTo(x + w / 2 + o, y - h - o * 1.6); g.lineTo(x + w / 2 + 1, y - h); g.closePath(); g.fill(); g.stroke();
    } else if (kind === "mid") {
      const w = R * (0.16 + rnd() * 0.08), h = R * (0.2 + rnd() * 0.16);
      box(g, x, y, w, w * 0.8, h, top, front, side);
      windows(g, x, y, w, h, "rgba(50,60,75,0.55)", rnd);
    } else if (kind === "tower") {
      const w = R * (0.15 + rnd() * 0.05), h = R * (0.42 + rnd() * 0.22);
      box(g, x, y, w, w * 0.8, h, "#c3ccd3", "#8e9eac", "#62717e");
      windows(g, x, y, w, h, "rgba(225,235,245,0.6)", rnd);
    } else {
      const w = R * (0.16 + rnd() * 0.05), h = R * (0.72 + rnd() * 0.4);
      const gl = g.createLinearGradient(x - w / 2, 0, x + w / 2, 0);
      gl.addColorStop(0, "#5f7f98"); gl.addColorStop(0.5, "#9cb8cc"); gl.addColorStop(1, "#4a6479");
      box(g, x, y, w, w * 0.8, h, "#d4e2ec", gl, "#34495b");
      windows(g, x, y, w, h, "rgba(255,240,190,0.5)", rnd);
      g.strokeStyle = "#cfd8df"; g.lineWidth = 1; g.beginPath(); g.moveTo(x, y - h); g.lineTo(x, y - h - R * 0.12); g.stroke();
    }
  }
  paintCityExtras(g, cx, cy, R, rx, ry, owner, capital, false, shield, dormant);
}
function paintCityExtras(g, cx, cy, R, rx, ry, owner, capital, walls, shield, dormant) {
  if (walls) {  // the perimeter, drawn over a render as a low wall ring
    g.strokeStyle = "rgba(30,26,22,0.55)"; g.lineWidth = Math.max(3, R * 0.1);
    g.beginPath(); g.ellipse(cx, cy + R * 0.06, rx * 0.98, ry * 0.98, 0, 0, Math.PI * 2); g.stroke();
    g.strokeStyle = "#a59f93"; g.lineWidth = Math.max(2, R * 0.07);
    g.beginPath(); g.ellipse(cx, cy + R * 0.04, rx * 0.98, ry * 0.98, 0, 0, Math.PI * 2); g.stroke();
  }
  if (capital && !dormant) {  // a domed capitol and a flag in the owner's colour
    const x = cx + R * 0.04, y = cy + R * 0.36, w = R * 0.44;
    box(g, x, y, w, w * 0.55, R * 0.16, "#f2ede2", "#f7f2e6", "#d3ccbc");
    g.fillStyle = "#d9d2c2"; for (let q = 0; q < 6; q++) g.fillRect(x - w / 2 + (q + 0.3) * w / 6, y - R * 0.15, w / 16, R * 0.14);
    g.fillStyle = "#e6e0d2"; g.fillRect(x - R * 0.09, y - R * 0.26, R * 0.18, R * 0.1);
    const dg = g.createRadialGradient(x - R * 0.05, y - R * 0.36, 1, x, y - R * 0.27, R * 0.15);
    dg.addColorStop(0, "#ffffff"); dg.addColorStop(1, "#b9b19d");
    g.fillStyle = dg; g.beginPath(); g.arc(x, y - R * 0.26, R * 0.12, Math.PI, 0); g.fill();
    g.strokeStyle = "rgba(60,50,40,0.6)"; g.lineWidth = 0.8; g.stroke();
    g.strokeStyle = "#4a3c28"; g.lineWidth = Math.max(1, R * 0.022); g.beginPath(); g.moveTo(x, y - R * 0.38); g.lineTo(x, y - R * 0.66); g.stroke();
    g.fillStyle = owner; g.strokeStyle = "rgba(0,0,0,0.5)"; g.lineWidth = 0.8;
    g.beginPath(); g.moveTo(x, y - R * 0.66); g.quadraticCurveTo(x + R * 0.12, y - R * 0.68, x + R * 0.24, y - R * 0.6); g.lineTo(x, y - R * 0.53); g.closePath(); g.fill(); g.stroke();
  }
  if (shield && !dormant) {
    const sg = g.createRadialGradient(cx, cy - R * 0.2, R * 0.3, cx, cy, rx * 1.05);
    sg.addColorStop(0, "rgba(120,200,255,0.04)"); sg.addColorStop(0.85, "rgba(120,200,255,0.16)"); sg.addColorStop(1, "rgba(170,225,255,0.5)");
    g.fillStyle = sg; g.beginPath(); g.ellipse(cx, cy + R * 0.1, rx * 1.02, R * spread * 1.15, 0, Math.PI, 0); g.fill();
    g.strokeStyle = "rgba(190,235,255,0.6)"; g.lineWidth = 1; g.stroke();
  }
}
function paintHive(g, cx, cy, R, tier, rnd) {
  const spread = [0.6, 0.75, 0.9, 1.02][tier];
  const ground = g.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * spread * 1.2);
  ground.addColorStop(0, "rgba(90,20,24,0.95)"); ground.addColorStop(0.6, "rgba(60,14,18,0.8)"); ground.addColorStop(1, "rgba(40,8,10,0)");
  g.fillStyle = ground; g.beginPath(); g.ellipse(cx, cy, R * spread * 1.2, R * spread * 0.85, 0, 0, Math.PI * 2); g.fill();
  // glowing veins across the ground
  g.strokeStyle = "rgba(255,120,60,0.55)"; g.lineWidth = Math.max(1, R * 0.025);
  for (let k = 0; k < 9; k++) {
    const a = rnd() * Math.PI * 2, l = R * spread * (0.6 + rnd() * 0.5);
    g.beginPath(); g.moveTo(cx, cy); g.quadraticCurveTo(cx + Math.cos(a + 0.4) * l * 0.5, cy + Math.sin(a + 0.4) * l * 0.35, cx + Math.cos(a) * l, cy + Math.sin(a) * l * 0.65); g.stroke();
  }
  const spires = [];
  for (let k = 0; k < [5, 7, 10, 13][tier]; k++) {
    const a = rnd() * Math.PI * 2, d = Math.sqrt(rnd()) * spread * 0.8;
    spires.push([cx + Math.cos(a) * R * d, cy + Math.sin(a) * R * d * 0.6 + R * 0.1, (1 - d / spread) * 0.7 + 0.3]);
  }
  spires.sort((a, b) => a[1] - b[1]);
  for (const [x, y, t] of spires) {
    const h = R * (0.35 + t * [0.45, 0.6, 0.8, 1.0][tier]) * (0.8 + rnd() * 0.4), w = R * (0.09 + t * 0.07), lean = (rnd() - 0.5) * R * 0.2;
    g.fillStyle = "rgba(0,0,0,0.35)"; g.beginPath(); g.ellipse(x + w, y, w * 1.6, w * 0.5, 0, 0, Math.PI * 2); g.fill();
    const sg = g.createLinearGradient(x - w, 0, x + w, 0);
    sg.addColorStop(0, "#5a1418"); sg.addColorStop(0.45, "#9b2a2a"); sg.addColorStop(1, "#2e0a0c");
    g.fillStyle = sg; g.beginPath(); g.moveTo(x - w, y); g.quadraticCurveTo(x - w * 0.6 + lean * 0.5, y - h * 0.6, x + lean, y - h); g.quadraticCurveTo(x + w * 0.6 + lean * 0.5, y - h * 0.5, x + w, y); g.closePath(); g.fill();
    g.strokeStyle = "rgba(255,170,90,0.7)"; g.lineWidth = Math.max(1, R * 0.02);
    g.beginPath(); g.moveTo(x - w * 0.2, y - h * 0.1); g.quadraticCurveTo(x + lean * 0.3, y - h * 0.5, x + lean * 0.8, y - h * 0.9); g.stroke();
    g.fillStyle = "rgba(255,210,120,0.9)"; g.beginPath(); g.arc(x + lean, y - h, Math.max(1.2, R * 0.025), 0, Math.PI * 2); g.fill();
  }
  for (let k = 0; k < 4 + tier * 2; k++) {  // egg pods
    const a = rnd() * Math.PI * 2, d = spread * (0.5 + rnd() * 0.45);
    const x = cx + Math.cos(a) * R * d, y = cy + Math.sin(a) * R * d * 0.6 + R * 0.15, r = R * (0.05 + rnd() * 0.04);
    const eg = g.createRadialGradient(x - r * 0.3, y - r * 0.4, 0, x, y, r);
    eg.addColorStop(0, "#ffb37a"); eg.addColorStop(1, "#7a2a1c");
    g.fillStyle = eg; g.beginPath(); g.ellipse(x, y, r, r * 1.25, 0, 0, Math.PI * 2); g.fill();
  }
}
function paintRuins(g, cx, cy, R, rnd) {
  g.fillStyle = "rgba(70,65,60,0.55)"; g.beginPath(); g.ellipse(cx, cy, R * 0.7, R * 0.45, 0, 0, Math.PI * 2); g.fill();
  for (let k = 0; k < 9; k++) {
    const x = cx + (rnd() - 0.5) * R * 1.1, y = cy + (rnd() - 0.4) * R * 0.6, w = R * (0.08 + rnd() * 0.1), h = R * (0.05 + rnd() * 0.15);
    box(g, x, y, w, w * 0.7, h, "#7d776f", "#8f8a82", "#5f5a53");
  }
}

function roundRect(x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
// Civ-style city banner: a dark plate with owner-coloured end caps (population on the left,
// production turns on the right), bevelled ends, a gold rim on your own cities, the capital star,
// and the city's health bar beneath.
function shieldPath(x, y, w, h) {
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + h * 0.5);
  ctx.quadraticCurveTo(x + w, y + h * 0.85, x + w / 2, y + h); ctx.quadraticCurveTo(x, y + h * 0.85, x, y + h * 0.5); ctx.closePath();
}
function drawBanner(c, sx, sy, R) {
  if (S.cam.zoom < 0.42) return;
  const hive = c.status === "overrun";
  const owner = hive ? "#b8322a" : c.owner ? OWNER[c.owner] : "#7e858b";
  const mine = c.owner === S.view.me;
  const status = c.status === "dormant" ? " · dormant" : c.status === "empty" ? " · ruins" : "";
  const label = c.name + status;
  const fs = Math.max(10, Math.round(11 * Math.min(1.35, S.cam.zoom)));
  ctx.font = `600 ${fs}px Roboto, Arial, sans-serif`;
  const tw = ctx.measureText(label).width + (c.is_capital ? fs * 1.1 : 0);
  const info = mine ? S.myCityInfo.get(c.id) : null;
  const prodText = info && info.head ? `${info.turns ?? "–"}` : "";
  const bh = Math.round(fs * 1.7), cap = bh * 1.15, bev = bh * 0.32;
  const bw = cap + tw + fs * 1.2 + (prodText ? cap : bev * 1.4);
  const bx = Math.round(sx - bw / 2), by = Math.round(sy - R * 1.05 - bh);
  const plate = (x, y, w, h) => { ctx.beginPath(); ctx.moveTo(x + bev, y); ctx.lineTo(x + w - bev, y); ctx.lineTo(x + w, y + h / 2); ctx.lineTo(x + w - bev, y + h); ctx.lineTo(x + bev, y + h); ctx.lineTo(x, y + h / 2); ctx.closePath(); };
  ctx.fillStyle = "rgba(0,0,0,0.45)"; plate(bx + 2, by + 3, bw, bh); ctx.fill();
  const bg = ctx.createLinearGradient(0, by, 0, by + bh);
  bg.addColorStop(0, hive ? "#4d1410" : "#2e3d4b"); bg.addColorStop(0.5, hive ? "#33100c" : "#1c2731"); bg.addColorStop(1, hive ? "#200806" : "#111820");
  ctx.fillStyle = bg; plate(bx, by, bw, bh); ctx.fill();
  // owner-coloured caps, clipped to the plate
  ctx.save(); plate(bx, by, bw, bh); ctx.clip();
  const capFill = (x, w) => { const cg = ctx.createLinearGradient(0, by, 0, by + bh); cg.addColorStop(0, shade(owner, 0.25)); cg.addColorStop(1, shade(owner, -0.35)); ctx.fillStyle = cg; ctx.fillRect(x, by, w, bh); };
  capFill(bx, cap);
  if (prodText) capFill(bx + bw - cap, cap);
  ctx.fillStyle = "rgba(255,255,255,0.12)"; ctx.fillRect(bx, by, bw, bh * 0.42);
  ctx.restore();
  ctx.strokeStyle = mine ? "#e9c77a" : "rgba(10,14,18,0.9)"; ctx.lineWidth = mine ? 1.8 : 1.2; plate(bx, by, bw, bh); ctx.stroke();
  if (mine) { ctx.strokeStyle = "rgba(255,240,200,0.35)"; ctx.lineWidth = 0.8; plate(bx + 2, by + 2, bw - 4, bh - 4); ctx.stroke(); }
  // population in a dark disc on the left cap
  const pcx = bx + cap * 0.55, pcy = by + bh / 2;
  ctx.fillStyle = "rgba(8,12,16,0.75)"; ctx.beginPath(); ctx.arc(pcx, pcy, bh * 0.36, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#fff6df"; ctx.font = `700 ${fs}px Roboto, Arial, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(c.pop), pcx, pcy + 0.5);
  // name (with the capital star)
  let nx = bx + cap + fs * 0.55;
  ctx.textAlign = "left";
  if (c.is_capital) {  // a small gold crown for the capital
    const w = fs * 0.95, h = fs * 0.7, x0 = nx, y0 = pcy + h * 0.45;
    ctx.fillStyle = "#f2cf6e"; ctx.strokeStyle = "#6b4d14"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0, y0 - h * 0.75); ctx.lineTo(x0 + w * 0.27, y0 - h * 0.35); ctx.lineTo(x0 + w * 0.5, y0 - h); ctx.lineTo(x0 + w * 0.73, y0 - h * 0.35); ctx.lineTo(x0 + w, y0 - h * 0.75); ctx.lineTo(x0 + w, y0); ctx.closePath(); ctx.fill(); ctx.stroke();
    nx += fs * 1.15;
  }
  ctx.font = `600 ${fs}px Roboto, Arial, sans-serif`;
  ctx.fillStyle = "rgba(0,0,0,0.6)"; ctx.fillText(label, nx + 1, pcy + 1.5);
  ctx.fillStyle = hive ? "#ffc9b8" : "#f6efdc"; ctx.fillText(label, nx, pcy + 0.5);
  if (prodText) {  // production turns on the right cap
    const px = bx + bw - cap * 0.5;
    ctx.fillStyle = "rgba(8,12,16,0.7)"; ctx.beginPath(); ctx.arc(px, pcy, bh * 0.36, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#e69a5c"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = "#ffd9b0"; ctx.font = `700 ${fs - 1}px sans-serif`; ctx.textAlign = "center"; ctx.fillText(prodText, px, pcy + 0.5);
  }
  if (c.strength && fs >= 10) {  // the defence shield above the banner's left end, as in Civ
    const sw = fs * 2.0, sh = fs * 1.9, sxl = bx + cap * 0.55 - sw / 2, syt = by - sh * 0.9;
    ctx.fillStyle = "rgba(0,0,0,0.45)"; shieldPath(sxl + 1.5, syt + 2, sw, sh); ctx.fill();
    const sg = ctx.createLinearGradient(0, syt, 0, syt + sh); sg.addColorStop(0, "#3c4a56"); sg.addColorStop(1, "#1a232b");
    ctx.fillStyle = sg; shieldPath(sxl, syt, sw, sh); ctx.fill();
    ctx.strokeStyle = mine ? "#e9c77a" : "#9aa6b0"; ctx.lineWidth = 1.2; ctx.stroke();
    ctx.fillStyle = "#f6efdc"; ctx.font = `700 ${Math.round(fs * 0.82)}px Roboto, Arial, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(String(Math.round(c.strength / 100)), sxl + sw / 2, syt + sh * 0.42);  // hundredths in the view
  }
  if (c.hp_now != null && c.max_hp) {
    const f = Math.max(0, Math.min(1, c.hp_now / c.max_hp)), hx = bx + bev, hw = bw - bev * 2;
    ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fillRect(hx, by + bh + 1, hw, 4);
    ctx.fillStyle = f > 0.5 ? "#82c873" : f > 0.25 ? "#e6c45c" : "#e5705f"; ctx.fillRect(hx, by + bh + 1, hw * f, 4);
  }
}

function isCivilian(type) { const t = S.view.unit_types[type]; return t && t.role === "civilian"; }
// Unit figures (visuals pass 1): Meshy models rendered in Blender from the map camera angle
// (web/static/units/*.png). Each unit type maps to the nearest model; infantry-like units stand as a
// squad of three. Figures stand on a team-coloured base with a small flag badge; at far zoom, or
// before the art loads, the badge alone is drawn.
const UNIT_MODELS = {
  // model: [size in hex radii, figures in the squad]
  infantry: [0.7, 3], engineer: [0.66, 1], tank: [1.0, 1], artillery: [0.95, 1], walker: [0.95, 1],
  drone: [0.5, 2, 0.35], destroyer: [1.25, 1], hover_tank: [1.0, 1], patrol_boat: [0.95, 1], submarine: [1.2, 1],
  alien_small: [0.55, 3], alien_warrior: [0.72, 2], alien_spitter: [0.8, 1], alien_brute: [0.95, 1], alien_titan: [1.25, 1],
};
const UNIT_ART = {
  infantry: "infantry", militia: "infantry", marines: "infantry", home_guard: "infantry", recon_team: "infantry",
  anti_tank_team: "infantry", exo_infantry: "walker", xeno_trooper: "infantry", plasma_lancer: "infantry",
  engineers: "engineer", survey_team: "engineer", medical_team: "engineer", nanorepair_crew: "engineer",
  tank: "tank", mech_infantry: "tank", armoured_recon: "tank", hover_tank: "hover_tank", trade_convoy: "tank",
  artillery: "artillery", city_artillery: "artillery", railgun_artillery: "artillery", self_propelled_howitzer: "artillery",
  rocket_battery: "artillery", plasma_cannon: "artillery", walker: "walker",
  drone_recon: "drone", swarm_drones: "drone",
  scout_boat: "patrol_boat", destroyer: "destroyer", railgun_cruiser: "destroyer", attack_submarine: "submarine",
  alien_drone: "alien_small", alien_hatchling: "alien_small", alien_warrior: "alien_warrior", alien_pillager: "alien_warrior",
  alien_wraith: "alien_warrior", alien_spitter: "alien_spitter", alien_sporecaster: "alien_spitter",
  alien_hive_guard: "alien_brute", alien_brute: "alien_brute", alien_shieldbearer: "alien_brute",
  alien_titan: "alien_titan", alien_leviathan: "alien_titan",
};
const UNIT_IMG = new Map(), UNIT_SPR = new Map(), SHIPS = new Set(["destroyer", "patrol_boat", "submarine"]);
function unitArt(type, Rb) {
  const model = UNIT_ART[type];
  if (!model || !UNIT_MODELS[model]) return null;
  let img = UNIT_IMG.get(model);
  if (!img) {
    img = new Image();
    img.onload = () => { img.crop = cropToContent(img); img.ready = true; };
    img.onerror = () => { img.failed = true; };
    img.src = `units/${model}.png`; UNIT_IMG.set(model, img);
  }
  if (!img.ready) return null;
  const [size] = UNIT_MODELS[model], px = Math.max(8, Math.round(Rb * size * 2)), key = `${model}|${px}`;
  let sp = UNIT_SPR.get(key);
  if (!sp) {  // downscale once per zoom step (in halves, for a crisp result)
    let src = img.crop, w = src.width;
    while (w / 2 >= px) {
      const c = document.createElement("canvas"); c.width = c.height = Math.round(w / 2);
      c.getContext("2d").drawImage(src, 0, 0, c.width, c.height); src = c; w = c.width;
    }
    sp = document.createElement("canvas"); sp.width = sp.height = px;
    const g = sp.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(src, 0, 0, px, px);
    UNIT_SPR.set(key, sp);
  }
  return [sp, UNIT_MODELS[model]];
}
function cropToContent(img) {
  // trim the transparent margin; return a square canvas with the figure centred and standing on
  // its bottom edge
  const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
  const g = c.getContext("2d"); g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  let x0 = c.width, y0 = c.height, x1 = 0, y1 = 0;
  for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
    if (d[(y * c.width + x) * 4 + 3] > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  }
  if (x1 <= x0) return c;
  const w = x1 - x0 + 1, h = y1 - y0 + 1, n = Math.max(w, h);
  const o = document.createElement("canvas"); o.width = o.height = n;
  o.getContext("2d").drawImage(c, x0, y0, w, h, (n - w) / 2, n - h, w, h);
  return o;
}
function drawFigures(u, x, y, R, scale = 1) {
  const art = R >= 14 ? unitArt(u.type, zoomStep(R)) : null;
  if (!art) return false;
  const [sp, [size, n, lift = 0]] = art, model = UNIT_ART[u.type], side = R * size * 2 * scale / 2;  // sprites are rendered at 2x
  const owner = u.owner === "aliens" ? "#c2362b" : OWNER[u.owner] || "#999";
  // team-coloured base under the squad
  const bw = R * (n > 1 ? 0.5 : Math.min(0.5, size * 0.45)) * scale, bh = bw * 0.4;
  ctx.fillStyle = "rgba(0,0,0,0.3)"; ctx.beginPath(); ctx.ellipse(x, y, bw, bh, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = owner; ctx.lineWidth = Math.max(1.2, R * 0.03 * scale); ctx.globalAlpha = 0.8; ctx.stroke(); ctx.globalAlpha = 1;
  const spots = n === 3 ? [[-0.3, -0.1], [0.3, -0.1], [0, 0.12]] : n === 2 ? [[-0.2, 0], [0.2, 0.04]] : [[0, 0]];
  for (const [dx, dy] of spots) {
    // idle motion: drones and hover tanks bob, ships rock on the swell (drones hover over their base)
    const ph = performance.now() / 650 + (u.id || 0) * 1.7 + dx * 3;
    const bob = model === "drone" ? Math.sin(ph) * 0.05 : model === "hover_tank" ? Math.sin(ph * 0.7) * 0.025 : SHIPS.has(model) ? Math.sin(ph * 0.5) * 0.015 : 0;
    const fx = x + dx * R * scale, fy = y + (dy - lift + bob) * R * scale;
    ctx.drawImage(sp, fx - side / 2, fy - side * 0.94, side, side);
  }
  return true;
}
function drawUnits(us, sx, sy, R, inCity = false) {
  const military = us.filter((u) => !isCivilian(u.type));
  const civil = us.filter((u) => isCivilian(u.type));
  // a garrison stands at the city's front edge so the city itself stays visible
  if (military.length) {
    const m = military[0];
    if (inCity) {
      if (drawFigures(m, sx - 0.42 * R, sy + 0.62 * R, R, 0.7)) drawBadge(m, sx - 0.78 * R, sy + 0.2 * R, 0.2 * R, R);
      else drawBadge(m, sx - 0.42 * R, sy + 0.5 * R, 0.33 * R, R);
    } else if (drawFigures(m, sx, sy + 0.3 * R, R)) drawBadge(m, sx - 0.55 * R, sy - 0.42 * R, 0.22 * R, R);
    else drawBadge(m, sx, sy + 0.05 * R, 0.43 * R, R);
  }
  if (civil.length) {
    const c = civil[0];
    if (drawFigures(c, sx + 0.45 * R, sy + 0.55 * R, R, 0.8)) drawBadge(c, sx + 0.72 * R, sy + 0.05 * R, 0.17 * R, R);
    else drawBadge(c, sx + 0.45 * R, sy + 0.42 * R, 0.27 * R, R);
  }
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
    story_choice: `Event: ${pretty(p.event)}`,
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
  if (p.kind === "story_choice") {
    const ev = S.view.story_pending.find((x) => x.story === p.story);
    if (ev) return showEventCard(ev);
  }
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
    shard_warning: () => `A shard is falling! It lands in ${e.impact_turn - S.view.turn > 0 ? e.impact_turn - S.view.turn : "a few"} turns inside the marked circle.`,
    shard_landed: () => `The ${e.name} shard has landed. Send an engineer or scout to mine it.`,
    shard_claimed: () => e.by === S.view.me ? `You claimed the ${e.name} shard!` : e.by === "aliens" ? `The aliens claimed the ${e.name} shard.` : `${pretty(e.by)} claimed the ${e.name} shard.`,
    shard_faded: () => "An unclaimed shard burnt out.",
    site_found: () => `Your unit found something: ${pretty(e.find)}.`,
    story_event: () => e.pending ? `Event: ${pretty(e.event)} (a choice awaits)` : `${pretty(e.event)}: ${(e.result || []).join(", ") || "nothing"}.`,
    story_chosen: () => `${pretty(e.event)}: ${e.label}. ${(e.result || []).join(", ")}`,
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
  return `<div class="yield y-${k}" title="${esc(parts.join("\n") || "nothing")}">${ICON[k] || ""}<b>${total}</b>${pretty(k)}</div>`;
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
const ACTION_ORDER = ["story_choice", "city_can_attack", "unit_promotion", "choose_research", "choose_production", "unit_needs_orders", "choose_espionage_tech",
  "deal_received", "offer_received", "recruit_unseated"];
const ACTION_LABEL = {
  choose_research: "Choose research", choose_production: "Choose production", unit_needs_orders: "Unit needs orders",
  choose_espionage_tech: "Choose alien tech", deal_received: "Answer a proposal", offer_received: "Answer an offer",
  recruit_unseated: "Seat a recruit", city_can_attack: "City can attack", story_choice: "An event awaits", unit_promotion: "Promote a unit",
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
// Portraits (visuals pass 1): every citizen and recruit gets a painted bust, drawn once from a seed
// (their id) and cached as an image. People are fictional; no real faces. Citizens vary in skin,
// hair, eyes, brows, clothes and accessories; alien recruits get elongated crania, large eyes and
// crests in their own colours.
const PORTRAITS = new Map();
const SKIN = [["#f3d6c1", "#d9a98c"], ["#e8bf9c", "#c9926e"], ["#d6a67c", "#b07c55"], ["#bf8a5e", "#946240"], ["#9c6b45", "#74492b"], ["#7a4f33", "#55341f"], ["#5e3b26", "#3f2617"], ["#efc9a8", "#cf9b78"]];
const HAIR = ["#1d1611", "#3a2618", "#5b3a22", "#8a5a33", "#b98a4e", "#d9b87a", "#9a9a9a", "#e8e3da", "#6b2a1c", "#2a2a33"];
const IRIS = ["#4a3020", "#6b4a2a", "#3d6b8f", "#4f7a4a", "#7a8a99", "#2e2018"];
const CLOTH = ["#3f5a3a", "#2f4560", "#7a3d2c", "#5b5f66", "#2f6b6b", "#6b5a2f", "#4a3a5c", "#8a6a3a"];
const ALIEN_SKIN = [["#7c5bb8", "#3e2a66"], ["#3fa39a", "#1d5650"], ["#b8504a", "#5e2220"], ["#6f9a3e", "#384f1e"], ["#4a6fb8", "#22386b"], ["#a87a3a", "#5a3e1a"]];
const ALIEN_EYE = ["#ffd36b", "#7ef0ff", "#ff7a5c", "#b6ff7a", "#f2a6ff"];
function portraitURL(kind, id, opts = {}) {
  const key = `${kind}:${id}:${opts.child ? 1 : 0}:${opts.legendary ? 1 : 0}`;
  let url = PORTRAITS.get(key);
  if (url) return url;
  const N = 160, c = document.createElement("canvas"); c.width = c.height = N;
  const g = c.getContext("2d"), rnd = rng((kind === "recruit" ? 7919 : 104729) + id * 2654435761);
  if (kind === "recruit") paintAlienBust(g, N, rnd, opts); else paintHumanBust(g, N, rnd, opts);
  url = c.toDataURL("image/png"); PORTRAITS.set(key, url);
  return url;
}
function mixHex(a, b, f) {
  const p = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16)), [x, y] = [p(a), p(b)];
  return "#" + x.map((v, k) => Math.round(v + (y[k] - v) * f).toString(16).padStart(2, "0")).join("");
}
function portraitImg(kind, id, cls = "", opts = {}) {
  return `<img class="portrait ${cls}" alt="" src="${portraitURL(kind, id, opts)}">`;
}
const pickOf = (rnd, a) => a[Math.floor(rnd() * a.length)];
function bustBackground(g, N, inner, outer) {
  const bg = g.createRadialGradient(N * 0.45, N * 0.35, N * 0.05, N * 0.5, N * 0.5, N * 0.75);
  bg.addColorStop(0, inner); bg.addColorStop(1, outer);
  g.fillStyle = bg; g.fillRect(0, 0, N, N);
  g.fillStyle = "rgba(255,255,255,0.05)"; for (let k = 0; k < 14; k++) { g.beginPath(); g.arc((k * 53) % N, (k * 37) % N, 6 + (k % 4) * 5, 0, Math.PI * 2); g.fill(); }
}
function shaded(g, x, y, rx, ry, light, dark, rot = 0) {
  const gr = g.createRadialGradient(x - rx * 0.35, y - ry * 0.4, rx * 0.1, x, y, Math.max(rx, ry) * 1.1);
  gr.addColorStop(0, light); gr.addColorStop(0.7, dark); gr.addColorStop(1, shade(dark.startsWith("#") ? dark : "#555555", -0.25));
  g.fillStyle = gr; g.beginPath(); g.ellipse(x, y, rx, ry, rot, 0, Math.PI * 2); g.fill();
}
function paintHumanBust(g, N, rnd, opts) {
  bustBackground(g, N, "#4b6170", "#141c24");
  g.save(); g.translate(N / 2, N * 0.8); g.scale(1.26, 1.26); g.translate(-N / 2, -N * 0.74);  // a close bust crop
  const [skin, skinD] = pickOf(rnd, SKIN), hair0 = pickOf(rnd, HAIR), cloth = pickOf(rnd, CLOTH);
  const kid = !!opts.child, cx = N / 2, hy = kid ? N * 0.5 : N * 0.44, hw = kid ? N * 0.2 : N * (0.19 + rnd() * 0.03), hh = kid ? N * 0.22 : N * (0.24 + rnd() * 0.03);
  const style = Math.floor(rnd() * 7), beard = !kid && rnd() < 0.22, glasses = rnd() < 0.15, scarf = rnd() < 0.12;
  // age (young, grown, older: lines and greying hair) and mood (calm, warm, stern, wry)
  const age = kid ? 0 : rnd() < 0.28 ? 2 : rnd() < 0.4 ? 0 : 1, mood = Math.floor(rnd() * 4);
  const hair = age === 2 && rnd() < 0.8 ? mixHex(hair0, "#cfcac2", 0.6 + rnd() * 0.3) : hair0;
  // shoulders and clothes
  const sy = hy + hh * 1.05;
  const cg = g.createLinearGradient(0, sy, 0, N); cg.addColorStop(0, shade(cloth, 0.15)); cg.addColorStop(1, shade(cloth, -0.45));
  g.fillStyle = cg; g.beginPath(); g.moveTo(cx - N * (kid ? 0.3 : 0.42), N); g.quadraticCurveTo(cx - N * 0.38, sy + N * 0.02, cx - hw * 0.5, sy - N * 0.02);
  g.lineTo(cx + hw * 0.5, sy - N * 0.02); g.quadraticCurveTo(cx + N * 0.38, sy + N * 0.02, cx + N * (kid ? 0.3 : 0.42), N); g.closePath(); g.fill();
  // long hair falls behind the shoulders
  if (style === 2 || style === 5) { g.fillStyle = shade(hair, -0.15); g.beginPath(); g.ellipse(cx, hy + hh * 0.5, hw * 1.25, hh * 1.25, 0, 0, Math.PI * 2); g.fill(); }
  // neck
  g.fillStyle = skinD; g.fillRect(cx - hw * 0.42, hy + hh * 0.6, hw * 0.84, hh * 0.6);
  g.fillStyle = "rgba(0,0,0,0.18)"; g.fillRect(cx - hw * 0.42, hy + hh * 0.6, hw * 0.84, hh * 0.18);
  // collar
  g.fillStyle = scarf ? pickOf(rnd, ["#c9a24a", "#8a2f2f", "#e3dccf", "#2f6b6b"]) : shade(cloth, 0.3);
  g.beginPath(); g.moveTo(cx - hw * 0.7, sy - N * 0.01); g.lineTo(cx, sy + N * (scarf ? 0.06 : 0.1)); g.lineTo(cx + hw * 0.7, sy - N * 0.01); g.lineTo(cx + hw * 0.45, sy - N * 0.04); g.lineTo(cx, sy + N * 0.02); g.lineTo(cx - hw * 0.45, sy - N * 0.04); g.closePath(); g.fill();
  // ears and head
  shaded(g, cx - hw * 0.98, hy + hh * 0.05, hw * 0.16, hh * 0.18, skin, skinD);
  shaded(g, cx + hw * 0.98, hy + hh * 0.05, hw * 0.16, hh * 0.18, skin, skinD);
  shaded(g, cx, hy, hw, hh, skin, skinD);
  // jaw shadow and cheeks
  g.fillStyle = "rgba(60,30,20,0.12)"; g.beginPath(); g.ellipse(cx + hw * 0.1, hy + hh * 0.62, hw * 0.75, hh * 0.3, 0, 0, Math.PI); g.fill();
  g.fillStyle = "rgba(220,100,90,0.12)"; g.beginPath(); g.arc(cx - hw * 0.5, hy + hh * 0.25, hw * 0.2, 0, Math.PI * 2); g.arc(cx + hw * 0.5, hy + hh * 0.25, hw * 0.2, 0, Math.PI * 2); g.fill();
  // eyes
  const ey = hy - hh * 0.02, ex = hw * 0.4, iris = pickOf(rnd, IRIS), er = hw * 0.13;
  for (const s of [-1, 1]) {
    g.fillStyle = "#f4efe6"; g.beginPath(); g.ellipse(cx + s * ex, ey, er * 1.45, er * 0.85, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = iris; g.beginPath(); g.arc(cx + s * ex, ey, er * 0.75, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#120c08"; g.beginPath(); g.arc(cx + s * ex, ey, er * 0.36, 0, Math.PI * 2); g.fill();
    g.fillStyle = "rgba(255,255,255,0.85)"; g.beginPath(); g.arc(cx + s * ex - er * 0.25, ey - er * 0.25, er * 0.18, 0, Math.PI * 2); g.fill();
    g.strokeStyle = shade(skinD, -0.35); g.lineWidth = 1.2; g.beginPath(); g.ellipse(cx + s * ex, ey, er * 1.45, er * 0.85, 0, Math.PI * 1.05, Math.PI * 1.95); g.stroke();
    // brows: a stern face lowers the inner ends, a warm one lifts them
    const inner = mood === 2 ? 0.5 : mood === 1 ? -0.2 : mood === 3 && s === 1 ? -0.35 : 0;
    const xo = cx + s * ex + s * er * 1.4, xi = cx + s * ex - s * er * 1.4;  // outer and inner ends
    g.strokeStyle = shade(hair, -0.1); g.lineWidth = Math.max(2, hw * (0.07 + rnd() * 0.05)); g.lineCap = "round";
    g.beginPath(); g.moveTo(xo, ey - er * 1.55); g.quadraticCurveTo(cx + s * ex, ey - er * 2.3, xi, ey - er * (1.75 - inner)); g.stroke();
  }
  // nose and mouth
  g.strokeStyle = shade(skinD, -0.25); g.lineWidth = 1.4;
  g.beginPath(); g.moveTo(cx + hw * 0.02, ey + er * 0.6); g.quadraticCurveTo(cx + hw * 0.16, hy + hh * 0.28, cx - hw * 0.02, hy + hh * 0.32); g.stroke();
  const mw = hw * (0.28 + rnd() * 0.12), my = hy + hh * 0.52;
  const smile = mood === 1 ? hh * 0.1 : mood === 2 ? -hh * 0.025 : hh * 0.02, lift = mood === 3 ? hh * 0.05 : mood === 1 ? hh * 0.025 : 0;
  g.strokeStyle = "#7a3a30"; g.lineWidth = 2; g.beginPath(); g.moveTo(cx - mw, my - (mood === 1 ? lift : 0)); g.quadraticCurveTo(cx, my + smile + 2, cx + mw, my - lift); g.stroke();
  if (age === 2) {  // lines of a long life: forehead, crow's feet, smile folds
    g.strokeStyle = "rgba(90,45,30,0.28)"; g.lineWidth = 1.1;
    for (const f of [0.55, 0.68]) { g.beginPath(); g.moveTo(cx - hw * 0.45, hy - hh * f); g.quadraticCurveTo(cx, hy - hh * (f + 0.04), cx + hw * 0.45, hy - hh * f); g.stroke(); }
    for (const s of [-1, 1]) {
      for (const d of [-0.12, 0.05]) { g.beginPath(); g.moveTo(cx + s * hw * 0.68, ey + er * d * 4); g.lineTo(cx + s * hw * 0.82, ey + er * d * 6); g.stroke(); }
      g.beginPath(); g.moveTo(cx + s * hw * 0.22, hy + hh * 0.3); g.quadraticCurveTo(cx + s * hw * 0.38, hy + hh * 0.48, cx + s * hw * 0.3, hy + hh * 0.62); g.stroke();
    }
  } else if (mood === 1) {  // dimples on a warm face
    g.fillStyle = "rgba(120,55,40,0.25)"; for (const s of [-1, 1]) { g.beginPath(); g.arc(cx + s * (mw + 2), my - lift, 1.4, 0, Math.PI * 2); g.fill(); }
  }
  g.fillStyle = "rgba(150,70,60,0.35)"; g.beginPath(); g.ellipse(cx, my + 3, mw * 0.7, hh * 0.05, 0, 0, Math.PI); g.fill();
  if (beard) {
    g.fillStyle = shade(hair, 0.05); g.globalAlpha = 0.9;
    g.beginPath(); g.moveTo(cx - hw * 0.95, hy + hh * 0.1); g.quadraticCurveTo(cx - hw * 0.9, hy + hh * 1.05, cx, hy + hh * 1.1); g.quadraticCurveTo(cx + hw * 0.9, hy + hh * 1.05, cx + hw * 0.95, hy + hh * 0.1);
    g.quadraticCurveTo(cx + hw * 0.6, hy + hh * 0.55, cx, my + hh * 0.06); g.quadraticCurveTo(cx - hw * 0.6, hy + hh * 0.55, cx - hw * 0.95, hy + hh * 0.1); g.fill(); g.globalAlpha = 1;
    g.strokeStyle = "#5a2a22"; g.lineWidth = 2; g.beginPath(); g.moveTo(cx - mw * 0.8, my); g.quadraticCurveTo(cx, my + 2, cx + mw * 0.8, my); g.stroke();
  }
  // hair on top
  g.fillStyle = hair;
  const top = hy - hh;
  if (style === 0) { g.beginPath(); g.ellipse(cx, hy - hh * 0.45, hw * 1.04, hh * 0.62, 0, Math.PI, 0); g.fill(); }  // short
  else if (style === 1) { g.beginPath(); g.moveTo(cx - hw * 1.02, hy - hh * 0.1); g.quadraticCurveTo(cx - hw * 1.1, top - hh * 0.1, cx + hw * 0.2, top - hh * 0.05); g.quadraticCurveTo(cx + hw * 1.15, top + hh * 0.1, cx + hw * 1.02, hy - hh * 0.1); g.quadraticCurveTo(cx + hw * 0.4, hy - hh * 0.65, cx - hw * 1.02, hy - hh * 0.1); g.fill(); }  // swept
  else if (style === 2 || style === 5) {  // long: a parted cap with locks framing the face
    g.beginPath(); g.ellipse(cx, hy - hh * 0.42, hw * 1.1, hh * 0.68, 0, Math.PI, 0); g.fill();
    for (const s of [-1, 1]) {
      g.beginPath(); g.moveTo(cx + s * hw * 1.1, hy - hh * 0.45); g.quadraticCurveTo(cx + s * hw * 1.25, hy + hh * 0.5, cx + s * hw * 1.05, hy + hh * 1.15);
      g.quadraticCurveTo(cx + s * hw * 0.9, hy + hh * 0.5, cx + s * hw * 0.82, hy - hh * 0.2); g.quadraticCurveTo(cx + s * hw * 0.3, hy - hh * 0.75, cx, hy - hh * 0.62); g.closePath(); g.fill();
    }
  }
  else if (style === 3) { for (let k = 0; k < 16; k++) { const a = Math.PI + (k / 15) * Math.PI; g.beginPath(); g.arc(cx + Math.cos(a) * hw * 0.95, hy - hh * 0.3 + Math.sin(a) * hh * 0.75, hw * 0.24, 0, Math.PI * 2); g.fill(); } }  // curls
  else if (style === 4) { g.globalAlpha = 0.55; g.beginPath(); g.ellipse(cx, hy - hh * 0.5, hw * 1.0, hh * 0.55, 0, Math.PI, 0); g.fill(); g.globalAlpha = 1; }  // buzz
  else { g.beginPath(); g.ellipse(cx, hy - hh * 0.45, hw * 1.04, hh * 0.6, 0, Math.PI, 0); g.fill(); g.beginPath(); g.arc(cx, top - hh * 0.05, hw * 0.38, 0, Math.PI * 2); g.fill(); }  // bun
  g.fillStyle = "rgba(255,255,255,0.12)"; g.beginPath(); g.ellipse(cx - hw * 0.3, top + hh * 0.2, hw * 0.4, hh * 0.12, -0.3, 0, Math.PI * 2); g.fill();
  if (glasses) {
    g.strokeStyle = "#1e1e22"; g.lineWidth = 2;
    for (const s of [-1, 1]) { g.beginPath(); g.ellipse(cx + s * ex, ey, er * 1.9, er * 1.4, 0, 0, Math.PI * 2); g.stroke(); }
    g.beginPath(); g.moveTo(cx - ex + er * 1.9, ey); g.lineTo(cx + ex - er * 1.9, ey); g.stroke();
  }
  // hair strands catch the light
  if (style !== 4) {
    g.strokeStyle = shade(hair, 0.25); g.globalAlpha = 0.35; g.lineWidth = 1;
    for (let q = 0; q < 14; q++) { const a = Math.PI * (1.1 + rnd() * 0.8), r0 = hw * (0.55 + rnd() * 0.4); g.beginPath(); g.moveTo(cx + Math.cos(a) * r0 * 0.5, hy - hh * 0.5 + Math.sin(a) * hh * 0.3); g.quadraticCurveTo(cx + Math.cos(a) * r0, hy - hh * 0.6 + Math.sin(a) * hh * 0.55, cx + Math.cos(a) * r0 * 1.05, hy - hh * 0.35 + Math.sin(a) * hh * 0.5); g.stroke(); }
    g.globalAlpha = 1;
  }
  // a cool rim light on the shadow side, and a painted brush texture over everything
  g.strokeStyle = "rgba(150,210,230,0.35)"; g.lineWidth = 2.2; g.beginPath(); g.ellipse(cx, hy, hw * 0.98, hh * 0.98, 0, -Math.PI * 0.35, Math.PI * 0.3); g.stroke();
  g.globalCompositeOperation = "overlay";
  for (let q = 0; q < 160; q++) {
    const x = rnd() * N, y = rnd() * N, l = 2 + rnd() * 5, a = -0.6 + rnd() * 0.5;
    g.strokeStyle = rnd() < 0.5 ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.12)"; g.lineWidth = 1 + rnd() * 1.5;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke();
  }
  g.globalCompositeOperation = "source-over";
  g.restore();
  // vignette
  const vg = g.createRadialGradient(N / 2, N / 2, N * 0.35, N / 2, N / 2, N * 0.72);
  vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, "rgba(0,0,0,0.45)"); g.fillStyle = vg; g.fillRect(0, 0, N, N);
}
function paintAlienBust(g, N, rnd, opts) {
  bustBackground(g, N, opts.legendary ? "#6a4a8c" : "#3d3358", "#0d0a16");
  g.save(); g.translate(N / 2, N * 0.72); g.scale(1.15, 1.15); g.translate(-N / 2, -N * 0.72);
  const [skin, skinD] = pickOf(rnd, ALIEN_SKIN), eye = pickOf(rnd, ALIEN_EYE), cx = N / 2, hy = N * 0.42;
  const hw = N * (0.17 + rnd() * 0.04), hh = N * (0.27 + rnd() * 0.05), eyes = rnd() < 0.25 ? 4 : 2, crest = Math.floor(rnd() * 4);
  // robed shoulders with a glowing clasp
  const sy = hy + hh * 0.95, robe = pickOf(rnd, ["#2a2238", "#1f3036", "#3a2420", "#26301f"]);
  const cg = g.createLinearGradient(0, sy, 0, N); cg.addColorStop(0, shade(robe, 0.25)); cg.addColorStop(1, shade(robe, -0.4));
  g.fillStyle = cg; g.beginPath(); g.moveTo(cx - N * 0.45, N); g.quadraticCurveTo(cx - N * 0.36, sy, cx - hw * 0.4, sy - N * 0.03); g.lineTo(cx + hw * 0.4, sy - N * 0.03); g.quadraticCurveTo(cx + N * 0.36, sy, cx + N * 0.45, N); g.closePath(); g.fill();
  g.fillStyle = eye; g.shadowColor = eye; g.shadowBlur = 8; g.beginPath(); g.arc(cx, sy + N * 0.08, N * 0.025, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
  // long thin neck
  g.fillStyle = skinD; g.fillRect(cx - hw * 0.28, hy + hh * 0.5, hw * 0.56, hh * 0.55);
  // crest behind the head
  g.fillStyle = shade(skinD, -0.1);
  if (crest === 1) { for (const s of [-1, 1]) { g.beginPath(); g.moveTo(cx + s * hw * 0.5, hy - hh * 0.6); g.quadraticCurveTo(cx + s * hw * 1.8, hy - hh * 1.3, cx + s * hw * 1.6, hy - hh * 1.6); g.quadraticCurveTo(cx + s * hw * 1.1, hy - hh * 0.9, cx + s * hw * 0.3, hy - hh * 0.75); g.fill(); } }
  else if (crest === 2) { g.beginPath(); g.ellipse(cx, hy - hh * 0.25, hw * 1.7, hh * 0.75, 0, 0, Math.PI * 2); g.fill(); for (let k = 0; k < 7; k++) { const a = Math.PI * (1.05 + k * 0.15); g.strokeStyle = shade(skin, 0.1); g.lineWidth = 1.5; g.beginPath(); g.moveTo(cx, hy - hh * 0.2); g.lineTo(cx + Math.cos(a) * hw * 1.7, hy - hh * 0.25 + Math.sin(a) * hh * 0.75); g.stroke(); } }
  else if (crest === 3) { g.beginPath(); g.moveTo(cx - hw * 0.25, hy - hh * 0.8); g.lineTo(cx, hy - hh * 1.55); g.lineTo(cx + hw * 0.25, hy - hh * 0.8); g.fill(); }
  // elongated cranium narrowing to a small jaw
  const hg = g.createRadialGradient(cx - hw * 0.4, hy - hh * 0.5, hw * 0.1, cx, hy, hh * 1.1);
  hg.addColorStop(0, shade(skin, 0.35)); hg.addColorStop(0.6, skin); hg.addColorStop(1, skinD);
  g.fillStyle = hg; g.beginPath();
  g.moveTo(cx, hy + hh * 0.75); g.bezierCurveTo(cx - hw * 0.7, hy + hh * 0.7, cx - hw * 1.15, hy, cx - hw * 1.0, hy - hh * 0.55);
  g.bezierCurveTo(cx - hw * 0.8, hy - hh * 1.15, cx + hw * 0.8, hy - hh * 1.15, cx + hw * 1.0, hy - hh * 0.55);
  g.bezierCurveTo(cx + hw * 1.15, hy, cx + hw * 0.7, hy + hh * 0.7, cx, hy + hh * 0.75); g.fill();
  // ridges
  g.strokeStyle = "rgba(0,0,0,0.25)"; g.lineWidth = 1.5;
  for (let k = 0; k < 3; k++) { g.beginPath(); g.moveTo(cx - hw * 0.6, hy - hh * (0.6 + k * 0.12)); g.quadraticCurveTo(cx, hy - hh * (0.75 + k * 0.12), cx + hw * 0.6, hy - hh * (0.6 + k * 0.12)); g.stroke(); }
  // glowing eyes
  const rows = eyes === 4 ? [[0, 1], [0.22, 0.6]] : [[0, 1]];
  for (const [dy, sz] of rows) for (const s of [-1, 1]) {
    const x = cx + s * hw * (0.45 - dy * 0.3), y = hy - hh * 0.05 + dy * hh;
    g.fillStyle = "#0a0610"; g.beginPath(); g.ellipse(x, y, hw * 0.34 * sz, hh * 0.13 * sz, s * 0.35, 0, Math.PI * 2); g.fill();
    g.fillStyle = eye; g.shadowColor = eye; g.shadowBlur = 10; g.beginPath(); g.ellipse(x, y, hw * 0.26 * sz, hh * 0.08 * sz, s * 0.35, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
    g.fillStyle = "#0a0610"; g.beginPath(); g.ellipse(x, y, hw * 0.04 * sz, hh * 0.07 * sz, 0, 0, Math.PI * 2); g.fill();
  }
  // slit nostrils and a thin mouth or mandibles
  g.fillStyle = "rgba(0,0,0,0.45)"; for (const s of [-1, 1]) { g.beginPath(); g.ellipse(cx + s * hw * 0.09, hy + hh * 0.3, hw * 0.03, hh * 0.04, 0, 0, Math.PI * 2); g.fill(); }
  if (rnd() < 0.5) { g.strokeStyle = shade(skinD, -0.4); g.lineWidth = 1.6; g.beginPath(); g.moveTo(cx - hw * 0.22, hy + hh * 0.5); g.quadraticCurveTo(cx, hy + hh * 0.54, cx + hw * 0.22, hy + hh * 0.5); g.stroke(); }
  else { g.fillStyle = shade(skinD, -0.2); for (const s of [-1, 1]) { g.beginPath(); g.moveTo(cx + s * hw * 0.15, hy + hh * 0.42); g.quadraticCurveTo(cx + s * hw * 0.45, hy + hh * 0.6, cx + s * hw * 0.12, hy + hh * 0.78); g.lineTo(cx + s * hw * 0.06, hy + hh * 0.5); g.fill(); } }
  // markings
  g.fillStyle = shade(eye.length === 7 ? eye : "#ffd36b", -0.2); g.globalAlpha = 0.45;
  for (const s of [-1, 1]) { g.beginPath(); g.ellipse(cx + s * hw * 0.62, hy + hh * 0.22, hw * 0.06, hh * 0.12, s * 0.4, 0, Math.PI * 2); g.fill(); }
  g.globalAlpha = 1;
  if (opts.legendary) { g.strokeStyle = "rgba(255,215,120,0.8)"; g.lineWidth = 2; g.beginPath(); g.ellipse(cx, hy - hh * 1.1, hw * 0.9, hh * 0.12, 0, 0, Math.PI * 2); g.stroke(); }
  g.restore();
  const vg = g.createRadialGradient(N / 2, N / 2, N * 0.35, N / 2, N / 2, N * 0.72);
  vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, "rgba(0,0,0,0.5)"); g.fillStyle = vg; g.fillRect(0, 0, N, N);
}
function scoreChips(scores) { return Object.entries(scores).map(([d, v]) => `<span class="chip ${d}">${pretty(d)} +${v}%</span>`).join(""); }
// The council (designer 2026-11-14, after a reference layout): three general seats on top, the
// two seats of each domain in a row below, and every possible member (alien recruits and grown
// citizens) underneath. Click a member, then a seat; click x to free a seat.
function memberCard(m, picked) {
  const chips = Object.entries(m.scores).map(([k, v]) => `<span class="tag ${k}">${v} ${k}</span>`).join("");
  return `<div class="member ${m.kind}${picked ? " picked" : ""}" data-member="${m.kind}:${m.id}">
    ${portraitImg(m.kind, m.id, "avatar", { legendary: /legendary/.test(m.where) })}<div class="mname">${esc(m.name)}${m.seats.length && !m.pinned ? ' <span class="autotag" title="Placed by Auto: it gives way to recruits; click it and a seat to fix it here">auto</span>' : ""}</div>
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
  return `<div class="citizen">${portraitImg("citizen", p.id, "face", { child: !p.adult })}<div class="cbody"><div class="row"><b>${esc(p.name)}</b> ${traits} ${pick}</div><div>${stats}</div><div class="muted small">${where}</div></div></div>`;
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

// Turrets: a concrete emplacement with an armoured gun house; one barrel per level, gold pips.
const TURRETS = new Map();
function drawTurret(t, sx, sy, R) {
  const Rb = zoomStep(R), lvl = Math.max(1, Math.min(3, t.turret)), key = `${lvl}|${Rb}`;
  let c = TURRETS.get(key);
  if (!c) {
    c = document.createElement("canvas"); c.width = Math.ceil(Rb * 0.9); c.height = Math.ceil(Rb * 0.9);
    const g = c.getContext("2d"), x = c.width / 2, y = c.height * 0.62, s = Rb * 0.3;
    g.fillStyle = "rgba(0,0,0,0.35)"; g.beginPath(); g.ellipse(x + s * 0.15, y + s * 0.35, s * 1.15, s * 0.45, 0, 0, Math.PI * 2); g.fill();
    // octagonal concrete pad
    g.beginPath(); for (let q = 0; q < 8; q++) { const a = (q + 0.5) * Math.PI / 4; g[q ? "lineTo" : "moveTo"](x + Math.cos(a) * s * 1.05, y + Math.sin(a) * s * 0.55); } g.closePath();
    const pg = g.createLinearGradient(0, y - s * 0.5, 0, y + s * 0.6); pg.addColorStop(0, "#b8b2a6"); pg.addColorStop(1, "#7d776c");
    g.fillStyle = pg; g.fill(); g.strokeStyle = "rgba(40,36,30,0.7)"; g.lineWidth = 1; g.stroke();
    // barrels (behind the dome), pointing up-right
    g.strokeStyle = "#2c3238"; g.lineCap = "round"; g.lineWidth = Math.max(1.5, s * 0.16);
    for (let b = 0; b < lvl; b++) { const off = (b - (lvl - 1) / 2) * s * 0.22; g.beginPath(); g.moveTo(x + off, y - s * 0.35); g.lineTo(x + off + s * 1.0, y - s * 0.95); g.stroke(); }
    // armoured gun house
    const dg = g.createRadialGradient(x - s * 0.25, y - s * 0.55, s * 0.05, x, y - s * 0.3, s * 0.7);
    dg.addColorStop(0, "#9aa8b4"); dg.addColorStop(1, "#3c4752");
    g.fillStyle = dg; g.beginPath(); g.ellipse(x, y - s * 0.25, s * 0.62, s * 0.5, 0, Math.PI, 0); g.lineTo(x + s * 0.62, y - s * 0.1); g.lineTo(x - s * 0.62, y - s * 0.1); g.closePath(); g.fill();
    g.strokeStyle = "rgba(15,20,25,0.7)"; g.lineWidth = 1; g.stroke();
    g.fillStyle = "#1b2026"; g.fillRect(x - s * 0.25, y - s * 0.42, s * 0.5, s * 0.08);
    // level pips
    for (let p = 0; p < lvl; p++) {
      const px = x - (lvl - 1) * s * 0.2 + p * s * 0.4, py = y + s * 0.22;
      g.fillStyle = "#f2d38a"; g.strokeStyle = "#5e4419"; g.lineWidth = 0.8;
      g.beginPath(); g.moveTo(px, py - s * 0.13); g.lineTo(px + s * 0.12, py); g.lineTo(px, py + s * 0.13); g.lineTo(px - s * 0.12, py); g.closePath(); g.fill(); g.stroke();
    }
    TURRETS.set(key, c);
  }
  const k = R / Rb, x = sx + R * 0.42, y = sy + R * 0.28;
  ctx.drawImage(c, x - c.width * k / 2, y - c.height * k * 0.62, c.width * k, c.height * k);
  if (t.turret_hp != null && t.turret_max_hp && t.turret_hp < t.turret_max_hp) {
    const f = Math.max(0, t.turret_hp / t.turret_max_hp), w = R * 0.4;
    ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fillRect(x - w / 2, y + R * 0.2, w, 3);
    ctx.fillStyle = f > 0.5 ? "#82c873" : f > 0.25 ? "#e6c45c" : "#e5705f"; ctx.fillRect(x - w / 2, y + R * 0.2, w * f, 3);
  }
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
const YIELD_ICON = { food: ICON.food, production: ICON.production, science: ICON.science, gold: ICON.gold, beacon: ICON.beacon };
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
  ["Starfall & finds", ["shard_warning", "shard_landed", "shard_claimed", "shard_faded", "site_found", "story_event", "story_chosen"]],
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

// -- story events, exploration finds and Starfall (docs/SPEC_M9.md) ---------------------------

const PICTURE = {
  survivors: ["#3b4a5c", "#c98b4a", "🔥"], outcast: ["#2a1d3d", "#8f5bd6", "◈"], wreckage: ["#1d2a33", "#6cbbec", "✦"],
  cache: ["#2b2a1d", "#f2d15c", "▣"], armoury: ["#2a2320", "#c0644a", "⚔"], ambush: ["#2a0d0d", "#e0362c", "!"],
  preserving_compound: ["#123020", "#93d46b", "✺"], starmetal: ["#1d2128", "#e6c45c", "✦"], new_elements: ["#0f2238", "#6cbbec", "⚛"],
  exotic_matter: ["#24123a", "#c88df2", "◈"], living_alloy: ["#1f2a2a", "#7fe0c8", "⬢"],
};
// Event and Starfall pictures (visuals pass 2): small painted scenes, drawn once per picture and
// size and cached as images. They reuse the unit renders (web/static/units) for the aliens, so the
// art matches the map; if those are not loaded yet the scene waits for them and is not cached.
const SCENES = new Map(), SCENE_IMG = {};
for (const n of ["alien_warrior", "alien_small", "engineer", "infantry"]) { const im = new Image(); im.src = `units/${n}.png`; SCENE_IMG[n] = im; }
function pictureSvg(key, big) {  // (name kept for its callers; it now returns a painted image)
  return `<img class="evart" alt="" src="${sceneURL(key, big)}">`;
}
function sceneURL(key, big) {
  const id = `${key}|${big ? 1 : 0}`;
  if (SCENES.has(id)) return SCENES.get(id);
  const W = 600, H = big ? 300 : 170, c = document.createElement("canvas"); c.width = W; c.height = H;
  const g = c.getContext("2d"), rnd = rng(key.length * 131 + key.charCodeAt(0) * 7);
  const [bg, glow] = PICTURE[key] || ["#1d2733", "#d9ae55"];
  const ready = paintScene(g, key, W, H, bg, glow, rnd);
  const url = c.toDataURL("image/png");
  if (ready) SCENES.set(id, url);
  return url;
}
function sprite(g, name, x, y, h, flip = false) {  // a unit render standing at (x, y), h tall
  const im = SCENE_IMG[name];
  if (!im || !im.complete || !im.naturalWidth) return false;
  const cr = im.crop || (im.crop = cropToContent(im)), w = h * cr.width / cr.height;
  g.save(); g.translate(x, y); if (flip) g.scale(-1, 1); g.drawImage(cr, -w / 2, -h, w, h); g.restore();
  return true;
}
function paintScene(g, key, W, H, bg, glow, rnd) {
  const horizon = H * 0.62, shard = !!(PICTURE[key] && ["preserving_compound", "starmetal", "new_elements", "exotic_matter", "living_alloy"].includes(key));
  // sky: dark at the top, the scene's light low on the horizon
  const sky = g.createLinearGradient(0, 0, 0, horizon);
  sky.addColorStop(0, "#05080d"); sky.addColorStop(0.55, bg); sky.addColorStop(1, glow);
  g.fillStyle = sky; g.fillRect(0, 0, W, horizon + 2);
  for (let q = 0; q < 70; q++) { g.fillStyle = `rgba(255,255,255,${0.2 + rnd() * 0.6})`; g.fillRect(rnd() * W, rnd() * horizon * 0.6, rnd() < 0.15 ? 2 : 1, rnd() < 0.15 ? 2 : 1); }
  // the alien wormhole, faint in every sky
  const wh = g.createRadialGradient(W * 0.8, H * 0.18, 2, W * 0.8, H * 0.18, H * 0.25);
  wh.addColorStop(0, "rgba(200,140,255,0.55)"); wh.addColorStop(0.4, "rgba(120,60,200,0.18)"); wh.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = wh; g.beginPath(); g.arc(W * 0.8, H * 0.18, H * 0.25, 0, Math.PI * 2); g.fill();
  // far hills, then the ground
  const far = (y0, amp, col) => { g.fillStyle = col; g.beginPath(); g.moveTo(0, H); for (let x = 0; x <= W; x += 20) g.lineTo(x, y0 - Math.abs(Math.sin(x * 0.013 + rnd())) * amp - rnd() * amp * 0.3); g.lineTo(W, H); g.fill(); };
  far(horizon, H * 0.12, "rgba(20,26,34,0.85)");
  const gr = g.createLinearGradient(0, horizon, 0, H); gr.addColorStop(0, "#2a2a26"); gr.addColorStop(1, "#14130f");
  g.fillStyle = gr; g.fillRect(0, horizon, W, H - horizon);
  let ready = true;
  const smoke = (x, y, n, col) => { for (let q = 0; q < n; q++) { const r = 8 + q * 4; g.fillStyle = col.replace("A", String(0.35 - q * 0.025)); g.beginPath(); g.arc(x + Math.sin(q * 0.9) * q * 3, y - q * 11, r, 0, Math.PI * 2); g.fill(); } };
  if (key === "survivors") {
    // a gutted school with one lit window and a chimney that should not be smoking
    const bx = W * 0.32, by = horizon + H * 0.06;
    g.fillStyle = "#2e2c2a"; g.beginPath(); g.moveTo(bx, by); g.lineTo(bx, by - H * 0.34); g.lineTo(bx + 120, by - H * 0.34); g.lineTo(bx + 140, by - H * 0.24); g.lineTo(bx + 170, by - H * 0.3); g.lineTo(bx + 200, by - H * 0.18); g.lineTo(bx + 200, by); g.fill();
    for (let r = 0; r < 2; r++) for (let q = 0; q < 6; q++) { g.fillStyle = r === 1 && q === 2 ? "#ffcc77" : "#121212"; g.fillRect(bx + 12 + q * 30, by - H * 0.28 + r * H * 0.12, 14, H * 0.07); }
    const lw = g.createRadialGradient(bx + 79, by - H * 0.13, 2, bx + 79, by - H * 0.13, 60); lw.addColorStop(0, "rgba(255,190,100,0.35)"); lw.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = lw; g.fillRect(bx, by - H * 0.4, 200, H * 0.4);
    g.fillStyle = "#3a3633"; g.fillRect(bx + 90, by - H * 0.44, 14, H * 0.12);
    smoke(bx + 97, by - H * 0.46, 9, "rgba(190,190,195,A)");
  } else if (key === "outcast") {
    // a crater ringed with warning marks, and one alien sitting alone in it
    g.fillStyle = "#0f0c10"; g.beginPath(); g.ellipse(W * 0.5, horizon + H * 0.2, W * 0.28, H * 0.12, 0, 0, Math.PI * 2); g.fill();
    g.strokeStyle = "#4a4038"; g.lineWidth = 4; g.beginPath(); g.ellipse(W * 0.5, horizon + H * 0.2, W * 0.28, H * 0.12, 0, Math.PI, 0); g.stroke();
    for (let q = 0; q < 7; q++) { const a = Math.PI + (q / 6) * Math.PI, x = W * 0.5 + Math.cos(a) * W * 0.3, y = horizon + H * 0.2 + Math.sin(a) * H * 0.13; g.strokeStyle = "#5a3a30"; g.lineWidth = 2; g.beginPath(); g.moveTo(x, y); g.lineTo(x, y - 20); g.stroke(); g.fillStyle = "#e0362c"; g.beginPath(); g.arc(x, y - 22, 3.5, 0, Math.PI * 2); g.fill(); }
    const halo = g.createRadialGradient(W * 0.5, horizon + H * 0.12, 4, W * 0.5, horizon + H * 0.12, 70); halo.addColorStop(0, "rgba(200,140,255,0.35)"); halo.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = halo; g.fillRect(0, 0, W, H);
    ready = sprite(g, "alien_warrior", W * 0.5, horizon + H * 0.24, H * 0.42) && ready;
  } else if (key === "wreckage") {
    // a scout ship split along its spine, still glowing at the seams
    for (const [dx, rot] of [[-70, -0.12], [70, 0.16]]) {
      g.save(); g.translate(W * 0.5 + dx, horizon + H * 0.12); g.rotate(rot);
      const hg = g.createLinearGradient(0, -24, 0, 18); hg.addColorStop(0, "#5d6b78"); hg.addColorStop(1, "#1d242b");
      g.fillStyle = hg; g.beginPath(); g.ellipse(0, 0, 80, 20, 0, 0, Math.PI * 2); g.fill();
      g.strokeStyle = "rgba(110,220,255,0.85)"; g.lineWidth = 2; g.beginPath(); g.moveTo(dx < 0 ? 70 : -70, -12); g.lineTo(dx < 0 ? 78 : -78, 10); g.stroke();
      for (let q = 0; q < 4; q++) { g.fillStyle = "rgba(110,220,255,0.6)"; g.fillRect(-50 + q * 26, -6, 8, 3); }
      g.restore();
    }
    smoke(W * 0.5, horizon + H * 0.02, 10, "rgba(120,140,150,A)");
    for (let q = 0; q < 20; q++) { g.fillStyle = "rgba(160,235,255,0.8)"; g.fillRect(W * 0.5 + (rnd() - 0.5) * 60, horizon - rnd() * H * 0.25, 2, 2); }
  } else if (key === "cache") {
    // a collapsed overpass with crates sheltered underneath, lit by a lamp
    g.fillStyle = "#4a4844"; g.fillRect(W * 0.2, horizon - H * 0.2, 26, H * 0.32); g.fillRect(W * 0.75, horizon - H * 0.2, 26, H * 0.32);
    g.save(); g.translate(W * 0.2, horizon - H * 0.22); g.rotate(0.12); g.fillStyle = "#5a5853"; g.fillRect(0, 0, W * 0.6, 20); g.fillStyle = "#3b3936"; g.fillRect(0, 20, W * 0.6, 6); g.restore();
    const lamp = g.createRadialGradient(W * 0.5, horizon + H * 0.05, 4, W * 0.5, horizon + H * 0.05, 120); lamp.addColorStop(0, "rgba(255,220,120,0.45)"); lamp.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = lamp; g.fillRect(0, 0, W, H);
    for (const [x, y, w] of [[0.42, 0.14, 40], [0.5, 0.16, 46], [0.47, 0.06, 34], [0.58, 0.15, 36]]) { g.fillStyle = "#5b5131"; g.fillRect(W * x, horizon + H * y - w * 0.7, w, w * 0.7); g.strokeStyle = "#2d2818"; g.lineWidth = 2; g.strokeRect(W * x, horizon + H * y - w * 0.7, w, w * 0.7); g.beginPath(); g.moveTo(W * x, horizon + H * y - w * 0.35); g.lineTo(W * x + w, horizon + H * y - w * 0.35); g.stroke(); }
    g.fillStyle = "#8a6a32"; g.fillRect(W * 0.53, horizon + H * 0.04 - 10, 22, 14);
  } else if (key === "armoury") {
    // a bunker door in the hillside, cut open, racks inside catching the torchlight
    g.fillStyle = "#24231f"; g.beginPath(); g.moveTo(W * 0.2, horizon + 10); g.quadraticCurveTo(W * 0.5, horizon - H * 0.45, W * 0.8, horizon + 10); g.fill();
    g.fillStyle = "#0c0b09"; g.fillRect(W * 0.42, horizon - H * 0.2, W * 0.16, H * 0.22);
    const inside = g.createLinearGradient(0, horizon - H * 0.2, 0, horizon); inside.addColorStop(0, "rgba(255,170,90,0.45)"); inside.addColorStop(1, "rgba(255,120,60,0.1)"); g.fillStyle = inside; g.fillRect(W * 0.42, horizon - H * 0.2, W * 0.16, H * 0.22);
    g.strokeStyle = "#2a1c12"; g.lineWidth = 2; for (let q = 0; q < 6; q++) { g.beginPath(); g.moveTo(W * 0.44 + q * 14, horizon - H * 0.16); g.lineTo(W * 0.44 + q * 14, horizon - H * 0.02); g.stroke(); }
    g.fillStyle = "#4b4a46"; g.save(); g.translate(W * 0.58, horizon + 2); g.rotate(-0.5); g.fillRect(0, -H * 0.22, 12, H * 0.22); g.restore();
    g.strokeStyle = "rgba(255,200,120,0.9)"; g.lineWidth = 1.5; g.beginPath(); g.moveTo(W * 0.42, horizon - H * 0.2); g.lineTo(W * 0.42, horizon); g.stroke();
    ready = sprite(g, "engineer", W * 0.33, horizon + H * 0.2, H * 0.36) && ready;
  } else if (key === "ambush") {
    // the ground opens: red eyes in the cracks, and the brood climbing out
    g.fillStyle = "rgba(120,10,10,0.35)"; g.fillRect(0, 0, W, H);
    g.strokeStyle = "#ff5a3c"; g.lineWidth = 2;
    for (let q = 0; q < 6; q++) { let x = W * (0.15 + q * 0.14), y = horizon + 6; g.beginPath(); g.moveTo(x, y); for (let k = 0; k < 4; k++) { x += (rnd() - 0.5) * 30; y += 10 + rnd() * 10; g.lineTo(x, y); } g.stroke(); }
    for (let q = 0; q < 10; q++) { const x = rnd() * W, y = horizon + 10 + rnd() * (H - horizon - 20); g.fillStyle = "#ff3b2a"; g.beginPath(); g.arc(x, y, 2, 0, Math.PI * 2); g.arc(x + 7, y, 2, 0, Math.PI * 2); g.fill(); }
    for (const [x, h, f] of [[0.3, 0.3, false], [0.52, 0.38, true], [0.72, 0.28, false]]) ready = sprite(g, "alien_small", W * x, horizon + H * 0.22, H * h, f) && ready;
  } else if (shard) {
    // a shard from deep space, still burning in its crater
    const cx = W * 0.5, cy = horizon + H * 0.14;
    const burn = g.createRadialGradient(cx, cy - H * 0.1, 4, cx, cy - H * 0.1, H * 0.6); burn.addColorStop(0, glow); burn.addColorStop(0.25, glow.length === 7 ? glow + "66" : glow); burn.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = burn; g.fillRect(0, 0, W, H);
    g.fillStyle = "#0d0c0b"; g.beginPath(); g.ellipse(cx, cy, W * 0.2, H * 0.08, 0, 0, Math.PI * 2); g.fill();
    for (let q = 0; q < 5; q++) {  // a cluster of crystal spars
      const a = -Math.PI / 2 + (q - 2) * 0.32, len = H * (0.25 + (q === 2 ? 0.22 : rnd() * 0.12)), w = 10 + rnd() * 8;
      const tx = cx + Math.cos(a) * len, ty = cy + Math.sin(a) * len;
      const cg = g.createLinearGradient(cx, cy, tx, ty); cg.addColorStop(0, shade(glow, -0.5)); cg.addColorStop(1, shade(glow, 0.5));
      g.fillStyle = cg; g.beginPath(); g.moveTo(cx - w / 2, cy); g.lineTo(tx, ty); g.lineTo(cx + w / 2, cy); g.closePath(); g.fill();
      g.strokeStyle = "rgba(255,255,255,0.5)"; g.lineWidth = 1; g.beginPath(); g.moveTo(cx, cy); g.lineTo(tx, ty); g.stroke();
    }
    for (let q = 0; q < 30; q++) { const a = rnd() * Math.PI * 2, r = 20 + rnd() * H * 0.4; g.fillStyle = shade(glow, 0.4); g.globalAlpha = 0.6; g.fillRect(cx + Math.cos(a) * r, cy - H * 0.1 + Math.sin(a) * r * 0.6, 2, 2); }
    g.globalAlpha = 1;
  }
  // a soft vignette, as on an old painted card
  const v = g.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, W * 0.6);
  v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(0,0,0,0.55)"); g.fillStyle = v; g.fillRect(0, 0, W, H);
  return ready;
}
function showEventCard(ev) {
  const body = $("modal-body");
  const choices = ev.choices ? `<div class="evchoices">${ev.choices.map((c, k) => `<button class="${k ? "" : "primary"}" data-choice="${k}"><b>${esc(c.label)}</b>${c.detail ? `<span class="muted"> ${esc(c.detail)}</span>` : ""}</button>`).join("")}</div>` : "";
  const result = ev.result && ev.result.length ? `<div class="evresult">${ev.result.map((r) => `<span class="tag">${esc(r)}</span>`).join(" ")}</div>` : "";
  // faces on the people events: three survivors, or the outcast (its seed is the event's id)
  const seed = ev.story || ev.tile || 1;
  const faces = ev.picture === "survivors" ? `<div class="evfaces">${[0, 1, 2].map((k) => portraitImg("citizen", 50000 + seed * 3 + k)).join("")}</div>`
    : ev.picture === "outcast" ? `<div class="evfaces">${portraitImg("recruit", 50000 + seed, "alien")}</div>` : "";
  body.innerHTML = `<div class="evcard">${pictureSvg(ev.picture, false)}${faces}<h2>${esc(ev.title)}</h2><p class="evbody">${esc(ev.body)}</p>${result}${choices}
    ${ev.choices ? "" : '<div class="row"><button class="primary" id="ev-ok">Continue</button></div>'}</div>`;
  document.querySelector(".modal-box").classList.add("narrow");
  $("modal").classList.remove("hidden"); S.screen = "event";
  body.querySelectorAll("[data-choice]").forEach((el) => el.onclick = async () => {
    closeModal(); await send({ kind: "choose_story", story: ev.story, choice: Number(el.dataset.choice) });
  });
  if ($("ev-ok")) $("ev-ok").onclick = () => { closeModal(); showNewStory(); };
}
// The wonder-style screen for a claimed shard (Civ's wonder splash).
function showShardScreen(c) {
  const body = $("modal-body");
  const mine = c.by === S.view.me;
  const who = mine ? "Your miners have claimed it." : c.by === "aliens" ? "The aliens got there first." : `${esc(pretty(c.by))} claimed it.`;
  body.innerHTML = `<div class="wonder"><div class="wtitle">${esc(c.name)}</div>${pictureSvg(c.find, true)}
    <div class="wfoot"><div class="wquote">"${esc(c.quote)}"</div>
    <div class="weffect"><b>${esc(c.name)}</b><div class="muted">${who}</div>${mine ? c.reward.map((r) => `<div>• ${esc(r)}</div>`).join("") : ""}</div></div>
    <div class="row center"><button class="primary" id="ev-ok">Continue</button></div></div>`;
  document.querySelector(".modal-box").classList.remove("narrow");
  $("modal").classList.remove("hidden"); S.screen = "wonder";
  $("ev-ok").onclick = () => { closeModal(); showNewStory(); };
}
// Show each new event card or shard screen once (claims by others are just a toast).
function showNewStory() {
  if (!S.view || !$("modal").classList.contains("hidden")) return;
  S.seenStory = S.seenStory || new Set();
  for (const c of S.view.shards_claimed || []) {
    if (S.seenStory.has(c.key)) continue;
    S.seenStory.add(c.key);
    if (c.by === S.view.me) return showShardScreen(c);
    toast(c.by === "aliens" ? `The aliens claimed the ${c.name} shard.` : `${pretty(c.by)} claimed the ${c.name} shard.`);
  }
  for (const c of S.view.story_cards || []) {
    if (S.seenStory.has(c.key)) continue;
    S.seenStory.add(c.key);
    return showEventCard(c);
  }
}
function drawSite(sx, sy, R, t) {
  const r = Math.max(6, R * 0.28), y = sy - R * 0.1;
  ctx.fillStyle = "rgba(20,16,8,0.75)"; ctx.beginPath(); ctx.arc(sx, y, r, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = `rgba(242,211,138,${0.6 + 0.4 * Math.sin(t / 300)})`; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = "#f2d38a"; ctx.font = `700 ${Math.round(r * 1.2)}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("?", sx, y + 1);
}
function drawStarfall(R, t) {
  const W = canvas.clientWidth, H = canvas.clientHeight;
  for (const sh of S.view.shards || []) {
    if (!sh.landed) {
      // the warned landing circle and a falling streak
      const [cx, cy] = toScreen(...center(sh.center));
      const rad = sh.radius * R * 1.75;
      ctx.save(); ctx.setLineDash([R * 0.4, R * 0.3]); ctx.lineWidth = 3;
      ctx.strokeStyle = `rgba(200,141,242,${0.55 + 0.35 * Math.sin(t / 250)})`;
      ctx.beginPath(); ctx.arc(cx, cy, rad, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
      ctx.fillStyle = "rgba(200,141,242,0.07)"; ctx.beginPath(); ctx.arc(cx, cy, rad, 0, Math.PI * 2); ctx.fill();
      const k = (t / 1600) % 1, x0 = cx - rad * 1.6, y0 = cy - rad * 1.6;
      const hx = x0 + (cx - x0) * k, hy = y0 + (cy - y0) * k;
      const g = ctx.createLinearGradient(x0, y0, hx, hy); g.addColorStop(0, "rgba(255,255,255,0)"); g.addColorStop(1, "rgba(255,236,190,0.95)");
      ctx.strokeStyle = g; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(hx, hy); ctx.stroke();
      ctx.font = `700 ${Math.max(11, R * 0.35)}px Roboto Mono, monospace`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const wl = `✦ Shard lands in ${Math.max(0, sh.impact_turn - S.view.turn)} turns`, ww = ctx.measureText(wl).width + 16;
      ctx.fillStyle = "rgba(22,12,36,0.88)"; roundRect(cx - ww / 2, cy - rad - 26, ww, 22, 11); ctx.fill();
      ctx.fillStyle = "#fff4d6"; ctx.fillText(wl, cx, cy - rad - 15);
      continue;
    }
    const [sx, sy] = toScreen(...center(sh.tile));
    if (sx < -R * 4 || sy < -R * 4 || sx > W + R * 4 || sy > H + R * 4) continue;
    const pulse = 0.5 + 0.5 * Math.sin(t / 200), gr = Math.max(28, R * 2);
    // a beam of light to the sky, visible through the fog
    const beam = ctx.createLinearGradient(sx, sy - gr * 4, sx, sy);
    beam.addColorStop(0, "rgba(200,141,242,0)"); beam.addColorStop(1, `rgba(220,170,255,${0.45 + 0.25 * pulse})`);
    ctx.fillStyle = beam; ctx.fillRect(sx - gr * 0.18, sy - gr * 4, gr * 0.36, gr * 4);
    const rg = ctx.createRadialGradient(sx, sy, 0, sx, sy, gr);
    rg.addColorStop(0, `rgba(255,240,200,${0.85 + 0.15 * pulse})`); rg.addColorStop(0.35, "rgba(170,90,240,0.7)"); rg.addColorStop(1, "rgba(120,60,200,0)");
    ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(sx, sy, gr, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.font = `700 ${Math.max(14, R * 0.6)}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("✦", sx, sy);
    const best = Object.entries(sh.progress).sort((a, b) => b[1] - a[1]);
    const label = `✦ ${sh.name}${best.length ? ` · ${best.map(([k, v]) => `${k === S.view.me ? "you" : pretty(k)} ${v}/${sh.needed}`).join(", ")}` : " · unclaimed"}`;
    ctx.font = `600 ${Math.max(11, R * 0.3)}px Roboto, sans-serif`;
    const tw = ctx.measureText(label).width + 14, ly = sy + gr + 4;
    ctx.fillStyle = "rgba(22,12,36,0.88)"; roundRect(sx - tw / 2, ly, tw, 20, 10); ctx.fill();
    ctx.strokeStyle = "#c88df2"; ctx.lineWidth = 1.2; ctx.stroke();
    ctx.fillStyle = "#f6efdc"; ctx.fillText(label, sx, ly + 10.5);
  }
}
