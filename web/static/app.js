// Beacon web client (docs/SPEC_M8.md). Plain JavaScript, no build step.
// The server owns the game; this file only draws the fog-safe view and sends commands.
"use strict";

// ---------------------------------------------------------------------------------------------
// constants and small helpers

const TERRAIN = {
  grassland: "#5f8f45", plains: "#a39a52", desert: "#cdb47c", tundra: "#87938a",
  snow: "#dfe7ea", coast: "#3a78a0", ocean: "#20496e",
};
const OWNER = {
  north_america: "#3b78e0", south_america: "#38b072", europe: "#e0b03a", asia: "#d1503f",
  africa: "#e0843a", oceania: "#36bfcc", aliens: "#a347c9",
};
const YIELD_KEYS = ["food", "production", "science", "gold", "beacon"];
const FOG_EXPLORED = "#1b2531";
const FOG_UNKNOWN = "#0a0f15";

const $ = (id) => document.getElementById(id);
const pretty = (id) => String(id).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const code = (type) => {
  const special = { infantry: "INF", artillery: "ART", recon_team: "RCN", engineers: "ENG",
    restoration_team: "RST", tank: "TNK", mech_infantry: "MEC", trade_convoy: "CVY" };
  if (special[type]) return special[type];
  const words = type.replace(/^alien_/, "").split("_");
  return (words.length > 1 ? words.map((w) => w[0]).join("") : words[0].slice(0, 3)).toUpperCase().slice(0, 3);
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

// ---------------------------------------------------------------------------------------------
// state

const S = {
  view: null,
  explored: new Set(),
  tilesByIndex: new Map(),
  unitsByTile: new Map(),
  citiesByTile: new Map(),
  selected: null,          // {kind:'unit'|'city', id}
  options: null,           // unit options from the server
  city: null,              // city detail
  targetMode: null,        // 'bombard'
  cam: { x: 0, y: 0, zoom: 1 },
  hover: null,
  busy: false,
};
const R0 = 22;             // hex radius at zoom 1
const SQ3 = Math.sqrt(3);

// ---------------------------------------------------------------------------------------------
// hex geometry (pointy-top, odd rows shifted right)

function colRow(i) { return [i % S.view.width, Math.floor(i / S.view.width)]; }
function center(i) {
  const [c, r] = colRow(i);
  const R = R0;
  return [c * SQ3 * R + (r & 1) * SQ3 * R / 2 + SQ3 * R / 2, r * 1.5 * R + R];
}
function toScreen(wx, wy) { return [(wx - S.cam.x) * S.cam.zoom, (wy - S.cam.y) * S.cam.zoom]; }
function toWorld(sx, sy) { return [sx / S.cam.zoom + S.cam.x, sy / S.cam.zoom + S.cam.y]; }
function pick(sx, sy) {
  const [wx, wy] = toWorld(sx, sy);
  const R = R0;
  const x = wx - SQ3 * R / 2, y = wy - R;
  let q = (SQ3 / 3 * x - y / 3) / R, r = (2 / 3 * y) / R, s = -q - r;
  let rq = Math.round(q), rr = Math.round(r), rs = Math.round(s);
  const dq = Math.abs(rq - q), dr = Math.abs(rr - r), ds = Math.abs(rs - s);
  if (dq > dr && dq > ds) rq = -rr - rs; else if (dr > ds) rr = -rq - rs;
  const col = rq + (rr - (rr & 1)) / 2, row = rr;
  if (col < 0 || row < 0 || col >= S.view.width || row >= S.view.height) return null;
  return row * S.view.width + col;
}
function neighbours(i) {
  const [c, r] = colRow(i);
  const offs = r & 1 ? [[1, 0], [1, -1], [0, -1], [-1, 0], [0, 1], [1, 1]] : [[1, 0], [0, -1], [-1, -1], [-1, 0], [-1, 1], [0, 1]];
  const out = [];
  for (const [dc, dr] of offs) {
    const cc = c + dc, rr = r + dr;
    if (cc >= 0 && rr >= 0 && cc < S.view.width && rr < S.view.height) out.push(rr * S.view.width + cc);
  }
  return out;
}

// ---------------------------------------------------------------------------------------------
// loading

async function refresh(keepSelection = true) {
  const v = await api("/api/view");
  S.view = v;
  S.explored = new Set(v.explored);
  S.tilesByIndex = new Map(Object.entries(v.tiles).map(([k, t]) => [Number(k), t]));
  S.unitsByTile = new Map();
  for (const u of v.units) {
    if (!S.unitsByTile.has(u.tile)) S.unitsByTile.set(u.tile, []);
    S.unitsByTile.get(u.tile).push(u);
  }
  S.citiesByTile = new Map();
  for (const [id, c] of Object.entries(v.cities)) S.citiesByTile.set(c.tile, { ...c, id: Number(id) });
  if (keepSelection && S.selected) await reselect(); else clearSelection();
  renderChrome();
  draw();
}

async function reselect() {
  const sel = S.selected;
  if (sel.kind === "unit") {
    const still = S.view.units.find((u) => u.id === sel.id && u.owner === S.view.me);
    if (still) { await selectUnit(sel.id, false); return; }
  } else if (sel.kind === "city") {
    const c = S.view.cities[sel.id];
    if (c && c.owner === S.view.me) { await selectCity(sel.id, false); return; }
  }
  clearSelection();
}

// ---------------------------------------------------------------------------------------------
// drawing

const canvas = $("map");
const ctx = canvas.getContext("2d");

function resize() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

function hexPath(cx, cy, r) {
  ctx.beginPath();
  for (let k = 0; k < 6; k++) {
    const a = Math.PI / 180 * (60 * k - 30);
    const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
    if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.closePath();
}

function draw() {
  if (!S.view) return;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  ctx.fillStyle = FOG_UNKNOWN;
  ctx.fillRect(0, 0, W, H);
  const z = S.cam.zoom, R = R0 * z;
  const reach = new Set(S.options ? S.options.reachable : []);
  const attackable = new Map((S.options ? S.options.attacks : []).map((a) => [a.tile, a]));
  const bombard = new Set(S.targetMode === "bombard" && S.city ? S.city.bombard : []);
  const total = S.view.width * S.view.height;
  const visible = [];
  for (let i = 0; i < total; i++) {
    const [wx, wy] = center(i);
    const [sx, sy] = toScreen(wx, wy);
    if (sx < -R * 2 || sy < -R * 2 || sx > W + R * 2 || sy > H + R * 2) continue;
    visible.push([i, sx, sy]);
  }
  // terrain and fog
  for (const [i, sx, sy] of visible) {
    const t = S.tilesByIndex.get(i);
    hexPath(sx, sy, R + 0.6);
    if (t) {
      ctx.fillStyle = TERRAIN[t.terrain] || "#555";
      ctx.fill();
      drawTerrainDetail(t, sx, sy, R);
      if (!t.visible) { ctx.fillStyle = "rgba(10,15,21,0.45)"; hexPath(sx, sy, R + 0.6); ctx.fill(); }
    } else if (S.explored.has(i)) {
      ctx.fillStyle = FOG_EXPLORED;
      ctx.fill();
      ctx.strokeStyle = "rgba(120,140,160,0.12)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }
  // routes
  for (const [i, sx, sy] of visible) {
    const t = S.tilesByIndex.get(i);
    if (!t || !(t.route || S.citiesByTile.has(i))) continue;
    for (const n of neighbours(i)) {
      if (n < i) continue;
      const tn = S.tilesByIndex.get(n);
      if (!tn || !(tn.route || S.citiesByTile.has(n))) continue;
      const [nx, ny] = toScreen(...center(n));
      const rail = t.route === "railway" && tn.route === "railway";
      ctx.strokeStyle = rail ? "#2b2b2b" : "#7a5a36";
      ctx.lineWidth = Math.max(1, (rail ? 3 : 2) * z);
      ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(nx, ny); ctx.stroke();
    }
  }
  // grid, highlights
  for (const [i, sx, sy] of visible) {
    const shown = S.tilesByIndex.has(i);
    if (shown && z > 0.55) {
      hexPath(sx, sy, R);
      ctx.strokeStyle = "rgba(0,0,0,0.18)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    if (reach.has(i)) { hexPath(sx, sy, R - 1); ctx.fillStyle = "rgba(255,255,255,0.18)"; ctx.fill(); }
    if (attackable.has(i) || bombard.has(i)) {
      hexPath(sx, sy, R - 1); ctx.fillStyle = "rgba(224,70,60,0.35)"; ctx.fill();
      ctx.strokeStyle = "#ff6b5a"; ctx.lineWidth = 2; ctx.stroke();
    }
    if (S.hover === i) { hexPath(sx, sy, R - 1); ctx.strokeStyle = "rgba(255,244,214,0.7)"; ctx.lineWidth = 1.5; ctx.stroke(); }
  }
  // cities, units, then city banners on top so names stay readable
  for (const [i, sx, sy] of visible) {
    const c = S.citiesByTile.get(i);
    if (c) drawCity(c, sx, sy, R);
  }
  for (const [i, sx, sy] of visible) {
    const us = S.unitsByTile.get(i);
    if (us) drawUnits(us, sx, sy, R);
  }
  for (const [i, sx, sy] of visible) {
    const c = S.citiesByTile.get(i);
    if (c) drawBanner(c, sx, sy, R);
  }
  // selection ring
  if (S.selected && S.selected.kind === "unit") {
    const u = S.view.units.find((x) => x.id === S.selected.id);
    if (u) { const [sx, sy] = toScreen(...center(u.tile)); hexPath(sx, sy, R - 1); ctx.strokeStyle = "#ffd76a"; ctx.lineWidth = 3; ctx.stroke(); }
  }
  drawMinimap();
}

function drawTerrainDetail(t, sx, sy, R) {
  const z = S.cam.zoom;
  if (t.elevation === "hills") {
    ctx.fillStyle = "rgba(60,45,25,0.35)";
    for (const dx of [-0.35, 0.3]) {
      ctx.beginPath(); ctx.ellipse(sx + dx * R, sy + 0.25 * R, 0.32 * R, 0.2 * R, 0, Math.PI, 0); ctx.fill();
    }
  }
  if (t.elevation === "mountain") {
    ctx.fillStyle = "#7d776f";
    ctx.beginPath(); ctx.moveTo(sx - 0.7 * R, sy + 0.45 * R); ctx.lineTo(sx - 0.1 * R, sy - 0.55 * R); ctx.lineTo(sx + 0.5 * R, sy + 0.45 * R); ctx.fill();
    ctx.fillStyle = "#e9eef0";
    ctx.beginPath(); ctx.moveTo(sx - 0.28 * R, sy - 0.25 * R); ctx.lineTo(sx - 0.1 * R, sy - 0.55 * R); ctx.lineTo(sx + 0.08 * R, sy - 0.25 * R); ctx.fill();
  }
  if (t.feature === "forest" || t.feature === "jungle") {
    ctx.fillStyle = t.feature === "forest" ? "#2f5a2a" : "#1f4a2a";
    const pts = [[-0.4, 0.05], [0.05, -0.25], [0.35, 0.15], [-0.05, 0.35]];
    for (const [dx, dy] of pts) {
      const x = sx + dx * R, y = sy + dy * R;
      if (t.feature === "forest") { ctx.beginPath(); ctx.moveTo(x, y - 0.22 * R); ctx.lineTo(x - 0.14 * R, y + 0.12 * R); ctx.lineTo(x + 0.14 * R, y + 0.12 * R); ctx.fill(); }
      else { ctx.beginPath(); ctx.arc(x, y, 0.15 * R, 0, Math.PI * 2); ctx.fill(); }
    }
  }
  if (t.feature === "marsh") {
    ctx.strokeStyle = "rgba(60,110,120,0.8)"; ctx.lineWidth = Math.max(1, 1.2 * z);
    for (const dy of [-0.2, 0.1, 0.35]) { ctx.beginPath(); ctx.moveTo(sx - 0.4 * R, sy + dy * R); ctx.lineTo(sx + 0.3 * R, sy + dy * R); ctx.stroke(); }
  }
  if (t.improvement && z > 0.5) {
    ctx.fillStyle = { farm: "#e8d36a", mine: "#3a3026", extractor: "#151515", radio_beacon: "#c58bf0", military_base: "#c0392b" }[t.improvement] || "#ddd";
    ctx.fillRect(sx + 0.25 * R, sy - 0.55 * R, 0.22 * R, 0.22 * R);
  }
  if (t.resource && t.visible && z > 0.7) {
    ctx.fillStyle = "rgba(10,12,14,0.75)";
    ctx.beginPath(); ctx.arc(sx - 0.45 * R, sy - 0.4 * R, 0.2 * R, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff4d6"; ctx.font = `${Math.round(0.24 * R)}px sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(t.resource[0].toUpperCase(), sx - 0.45 * R, sy - 0.4 * R);
  }
}

function drawCity(c, sx, sy, R) {
  const color = c.owner ? OWNER[c.owner] || "#999" : "#8a8f94";
  ctx.fillStyle = "#1b1b1b";
  ctx.beginPath(); ctx.arc(sx, sy, 0.55 * R, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = c.status === "empty" ? "#5a5f63" : color;
  ctx.beginPath(); ctx.arc(sx, sy, 0.46 * R, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,0.65)";
  for (const [dx, dy] of [[-0.18, -0.08], [0.12, -0.18], [0.02, 0.14], [-0.2, 0.18]]) ctx.fillRect(sx + dx * R, sy + dy * R, 0.12 * R, 0.12 * R);
}

function drawBanner(c, sx, sy, R) {
  if (S.cam.zoom < 0.45) return;
  const color = c.owner ? OWNER[c.owner] || "#999" : "#8a8f94";
  const label = c.name + (c.status === "dormant" ? " (dormant)" : c.status === "empty" ? " (ruins)" : "");
  const fs = Math.max(10, Math.round(11 * Math.min(1.3, S.cam.zoom)));
  ctx.font = `600 ${fs}px sans-serif`;
  const tw = ctx.measureText(label).width;
  const bw = tw + fs * 2.4, bh = fs * 1.6, bx = sx - bw / 2, by = sy - R * 1.25 - bh;
  ctx.fillStyle = "rgba(10,14,18,0.85)"; ctx.fillRect(bx, by, bw, bh);
  ctx.fillStyle = color; ctx.fillRect(bx, by, fs * 1.6, bh);
  ctx.strokeStyle = c.owner === S.view.me ? "#ffd76a" : "rgba(255,255,255,0.25)"; ctx.lineWidth = 1; ctx.strokeRect(bx, by, bw, bh);
  ctx.fillStyle = "#0b0f13"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(c.pop), bx + fs * 0.8, by + bh / 2);
  ctx.fillStyle = "#f3efe2"; ctx.textAlign = "left";
  ctx.fillText(label, bx + fs * 2, by + bh / 2);
  const hp = c.hp_now ?? null;
  if (hp !== null && c.max_hp) {
    ctx.fillStyle = "#300"; ctx.fillRect(bx, by + bh, bw, 3);
    ctx.fillStyle = hp / c.max_hp > 0.5 ? "#7cc46f" : "#e06a5a"; ctx.fillRect(bx, by + bh, bw * hp / c.max_hp, 3);
  }
}

function drawUnits(us, sx, sy, R) {
  const military = us.filter((u) => !isCivilian(u.type));
  const civil = us.filter((u) => isCivilian(u.type));
  if (military.length) drawBadge(military[0], sx, sy + 0.08 * R, 0.42 * R);
  if (civil.length) drawBadge(civil[0], sx + 0.42 * R, sy + 0.42 * R, 0.26 * R);
}
function isCivilian(type) { const t = S.view.unit_types[type]; return t && t.role === "civilian"; }

function drawBadge(u, x, y, r) {
  const color = OWNER[u.owner] || "#999";
  ctx.fillStyle = "#0b0f13"; ctx.beginPath(); ctx.arc(x, y, r + 2, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  if (u.owner === "aliens") { ctx.strokeStyle = "#7dff8f"; ctx.lineWidth = 1.5; ctx.stroke(); }
  ctx.fillStyle = "#0b0f13"; ctx.font = `700 ${Math.max(8, Math.round(r * 0.75))}px sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(code(u.type), x, y + 0.5);
  if (u.count > 1) {
    ctx.fillStyle = "#ffd76a"; ctx.beginPath(); ctx.arc(x + r * 0.85, y - r * 0.85, r * 0.42, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#0b0f13"; ctx.font = `700 ${Math.max(7, Math.round(r * 0.5))}px sans-serif`; ctx.fillText("×2", x + r * 0.85, y - r * 0.85);
  }
  if (u.fortified) { ctx.strokeStyle = "#e6e2d6"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r + 3.5, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); }
  const frac = Math.max(0, Math.min(1, u.hp / (u.max_hp || 100)));
  ctx.fillStyle = "#300"; ctx.fillRect(x - r, y + r + 2, 2 * r, 3);
  ctx.fillStyle = frac > 0.5 ? "#7cc46f" : "#e06a5a"; ctx.fillRect(x - r, y + r + 2, 2 * r * frac, 3);
}

// ---------------------------------------------------------------------------------------------
// minimap

const mini = $("minimap");
const mctx = mini.getContext("2d");
function drawMinimap() {
  const v = S.view, sx = mini.width / v.width, sy = mini.height / v.height;
  mctx.fillStyle = FOG_UNKNOWN; mctx.fillRect(0, 0, mini.width, mini.height);
  for (const i of S.explored) {
    const [c, r] = colRow(i);
    mctx.fillStyle = FOG_EXPLORED; mctx.fillRect(c * sx, r * sy, sx + 0.5, sy + 0.5);
  }
  for (const [i, t] of S.tilesByIndex) {
    const [c, r] = colRow(i);
    mctx.fillStyle = TERRAIN[t.terrain]; mctx.fillRect(c * sx, r * sy, sx + 0.5, sy + 0.5);
  }
  for (const c of S.citiesByTile.values()) {
    const [cc, rr] = colRow(c.tile);
    mctx.fillStyle = c.owner ? OWNER[c.owner] : "#aaa"; mctx.fillRect(cc * sx - 1.5, rr * sy - 1.5, 4, 4);
  }
  const [x0, y0] = toWorld(0, 0), [x1, y1] = toWorld(canvas.clientWidth, canvas.clientHeight);
  const ww = SQ3 * R0 * v.width, wh = 1.5 * R0 * v.height;
  mctx.strokeStyle = "#ffd76a"; mctx.lineWidth = 1;
  mctx.strokeRect(x0 / ww * mini.width, y0 / wh * mini.height, (x1 - x0) / ww * mini.width, (y1 - y0) / wh * mini.height);
}
mini.addEventListener("click", (e) => {
  const rect = mini.getBoundingClientRect();
  const fx = (e.clientX - rect.left) / mini.width, fy = (e.clientY - rect.top) / mini.height;
  const ww = SQ3 * R0 * S.view.width, wh = 1.5 * R0 * S.view.height;
  centerOnWorld(fx * ww, fy * wh);
});
function centerOnWorld(wx, wy) {
  S.cam.x = wx - canvas.clientWidth / 2 / S.cam.zoom;
  S.cam.y = wy - canvas.clientHeight / 2 / S.cam.zoom;
  draw();
}
function centerOnTile(i) { centerOnWorld(...center(i)); }

// ---------------------------------------------------------------------------------------------
// chrome: top bar, pending, log

function renderChrome() {
  const v = S.view, e = v.economy;
  $("turninfo").innerHTML = `Turn <b>${v.turn}</b> · ${v.year}`;
  const gd = e.gold_per_turn;
  $("gold").innerHTML = `Gold <b style="color:var(--gold)">${e.gold}</b> <span class="${gd >= 0 ? "good" : "bad"}">(${gd >= 0 ? "+" : ""}${gd})</span>`;
  const rs = v.research;
  $("science").innerHTML = `Science <b style="color:var(--science)">+${e.science_per_turn}</b> · ${rs ? `${esc(pretty(rs.tech))} <span class="muted">(${rs.turns ?? "–"})</span>` : '<span class="bad">no research</span>'}`;
  $("beacon").innerHTML = `Beacon <b style="color:var(--beacon)">${e.beacon_points}</b>${e.arrival_cost ? `/${e.arrival_cost}` : ""} <span class="muted">rarity ${e.rarity}</span>`;
  const knownAlien = Object.values(v.cities).filter((c) => c.status === "overrun").length;
  $("threat").innerHTML = `${v.mothership_alive ? "Mothership <b class='bad'>active</b>" : "Mothership <b class='good'>destroyed</b>"} · alien cities known <b>${knownAlien}</b>`;
  const ul = $("pending");
  ul.innerHTML = "";
  const pend = v.pending;
  for (const p of pend.slice(0, 14)) {
    const li = document.createElement("li");
    li.textContent = describePending(p);
    li.onclick = () => resolvePending(p);
    ul.appendChild(li);
  }
  if (pend.length > 14) { const li = document.createElement("li"); li.className = "muted"; li.textContent = `…and ${pend.length - 14} more`; ul.appendChild(li); }
  if (!pend.length) { const li = document.createElement("li"); li.className = "muted"; li.textContent = "Nothing. Ready for the next turn."; ul.appendChild(li); }
  const log = $("log");
  log.innerHTML = "";
  for (const ev of v.events.slice(-40).reverse()) {
    const li = document.createElement("li");
    li.textContent = describeEvent(ev);
    log.appendChild(li);
  }
  const btn = $("endturn");
  btn.textContent = v.outcome ? pretty(v.outcome) : pend.length ? `Next turn (${pend.length})` : "Next turn";
  btn.classList.toggle("waiting", pend.length > 0);
  btn.disabled = !!v.outcome;
  if (v.outcome && !S.shownOutcome) { S.shownOutcome = true; openScreen("scores"); }
}

function cityName(id) { const c = S.view.cities[id]; return c ? c.name : `city ${id}`; }
function unitLabel(id) { const u = S.view.units.find((x) => x.id === id); return u ? pretty(u.type) : `unit ${id}`; }
function describePending(p) {
  switch (p.kind) {
    case "choose_research": return "Choose research";
    case "choose_production": return `${cityName(p.city)}: choose production`;
    case "unit_needs_orders": return `${unitLabel(p.unit)} needs orders`;
    case "recruit_unseated": return "A recruit has no council seat";
    case "offer_received": return "A recruit is offered to you";
    case "deal_received": return "A deal is proposed to you";
    case "choose_espionage_tech": return "Choose your alien technology";
    default: return pretty(p.kind);
  }
}
async function resolvePending(p) {
  if (p.kind === "choose_research") return openScreen("techs");
  if (p.kind === "choose_production") { centerOnTile(S.view.cities[p.city].tile); return selectCity(p.city); }
  if (p.kind === "unit_needs_orders") { const u = S.view.units.find((x) => x.id === p.unit); if (u) centerOnTile(u.tile); return selectUnit(p.unit); }
  if (p.kind === "recruit_unseated" || p.kind === "offer_received") return openScreen("council");
  if (p.kind === "deal_received") return openScreen("diplomacy");
  if (p.kind === "choose_espionage_tech") return openScreen("projects");
}
function describeEvent(e) {
  const k = e.kind;
  const m = {
    turn_started: () => `Turn ${e.turn} begins (${e.year}).`,
    city_grew: () => `${cityName(e.city)} grew to ${e.pop}.`,
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
  return m[k] ? m[k]() : pretty(k);
}

// ---------------------------------------------------------------------------------------------
// selection panels

function clearSelection() {
  S.selected = null; S.options = null; S.city = null; S.targetMode = null;
  $("side").classList.add("hidden");
  draw();
}

async function selectUnit(id, center = false) {
  try {
    S.options = await api(`/api/unit/${id}`);
  } catch (err) { clearSelection(); return; }
  S.selected = { kind: "unit", id }; S.city = null; S.targetMode = null;
  if (center) centerOnTile(S.options.unit.tile);
  renderUnitPanel();
  draw();
}

function renderUnitPanel() {
  const o = S.options, u = o.unit, spec = o.spec, side = $("side");
  const moves = (u.moves_left / 30).toFixed(1).replace(/\.0$/, "");
  const ranged = spec.ranged_strength ? ` · ranged ${spec.ranged_strength} (range ${spec.range})` : "";
  side.innerHTML = `
    <div class="title">${esc(pretty(u.type))}${u.count > 1 ? " ×2" : ""}</div>
    <div class="muted">${esc(spec.role)} · strength ${spec.strength * u.count}${ranged}</div>
    <div class="row">HP ${u.hp}/${100 * u.count} · moves ${moves}/${spec.moves}${u.fortified ? " · fortified" : ""}${u.job ? ` · building ${pretty(u.job.improvement)} (${u.job.turns_left})` : ""}</div>
    <div class="bar"><i style="width:${Math.round(100 * u.hp / (100 * u.count))}%"></i></div>
    <div class="actions" id="uactions"></div>
    <div class="muted" style="font-size:12px">Click a highlighted hex to move; red hexes can be attacked (hover for the preview).</div>`;
  const a = $("uactions");
  const add = (label, fn, title = "") => { const b = document.createElement("button"); b.textContent = label; b.title = title; b.onclick = fn; a.appendChild(b); };
  if (spec.role !== "civilian" && !u.job) add("Fortify (F)", () => send({ kind: "fortify", unit: u.id }));
  add("Skip (S)", () => send({ kind: "skip_unit", unit: u.id }));
  for (const imp of o.builds) add(`Build ${pretty(imp)}`, () => send({ kind: "build_improvement", unit: u.id, improvement: imp }));
  if (o.refound) add("Refound city", () => send({ kind: "refound_city", unit: u.id }));
  for (const other of o.merges) add(`Merge with #${other}`, () => send({ kind: "merge_units", unit: u.id, into: other }), "Two units of one type become one stack");
  if (o.splits.length) add("Split stack", () => send({ kind: "split_unit", unit: u.id, target: o.splits[0] }));
  if (o.ships.length) {
    const sel = document.createElement("select");
    for (const s of o.ships) { const opt = document.createElement("option"); opt.value = s.city; opt.textContent = `${s.name} (${s.price} gold)`; sel.appendChild(opt); }
    a.appendChild(sel);
    add("Ship abroad", () => send({ kind: "ship_unit", unit: u.id, city: Number(sel.value) }));
  }
  side.classList.remove("hidden");
}

async function selectCity(id, center = false) {
  try { S.city = await api(`/api/city/${id}`); } catch (err) { clearSelection(); return; }
  S.selected = { kind: "city", id }; S.options = null; S.targetMode = null;
  if (center) centerOnTile(S.city.city.tile);
  renderCityPanel();
  draw();
}

function yieldBox(k, total, lines) {
  const parts = lines.filter((l) => l[1] === k).map((l) => `${pretty(l[0].replace(/^\w+:/, ""))}: ${l[2] >= 0 ? "+" : ""}${l[2]}`);
  return `<div class="yield y-${k}" title="${esc(parts.join("\n") || "nothing")}"><b>${total}</b>${pretty(k)}</div>`;
}

function renderCityPanel() {
  const d = S.city, c = d.city, side = $("side");
  const surplus = d.totals.food - d.food_eaten;
  const head = c.queue[0];
  const headOpt = head ? d.options.find((o) => o.item === head) : null;
  const groups = { building: [], unit: [], project: [] };
  for (const o of d.options) groups[o.kind].push(o);
  const list = Object.entries(groups).filter(([, v]) => v.length).map(([k, v]) =>
    `<div class="group">${k}s</div>` + v.map((o) => `<div class="item" data-item="${esc(o.item)}" title="${esc(o.note || "")}"><span>${esc(pretty(o.id))}</span><span class="muted">${o.cost ?? ""}${o.turns != null ? ` · ${o.turns}t` : ""}</span></div>`).join("")).join("");
  side.innerHTML = `
    <div class="title">${esc(c.name)}${c.is_capital ? " ★" : ""}</div>
    <div class="row muted">Population ${c.pop} · food ${c.food_store}/${d.growth_threshold} (${surplus >= 0 ? "+" : ""}${surplus}) · ${c.connected ? "connected" : '<span class="bad">not connected: produces nothing</span>'}</div>
    <div class="row muted">HP ${c.hp}/${d.max_hp} · strength ${Math.round(d.strength / 100)}</div>
    <div class="yields">${YIELD_KEYS.map((k) => yieldBox(k, d.totals[k], d.lines)).join("")}</div>
    <div class="row">Focus <select id="focus">${d.focuses.map((f) => `<option ${f === c.focus ? "selected" : ""}>${f}</option>`).join("")}</select></div>
    <h3>Producing</h3>
    <div class="row">${head ? `${esc(pretty(head.split(":")[1]))} <span class="muted">${c.production_store}/${headOpt?.cost ?? "–"}${headOpt?.turns != null ? ` · ${headOpt.turns} turns` : ""}</span>` : '<span class="bad">nothing</span>'}
      ${headOpt?.price ? `<button class="small" id="buy" ${S.view.economy.gold < headOpt.price ? "disabled" : ""}>Buy ${headOpt.price}g</button>` : ""}</div>
    <h3>Change production</h3>
    <div class="list" id="prodlist">${list}</div>
    <h3>Buildings</h3>
    <div class="muted">${c.buildings.map(pretty).join(", ") || "none"}</div>
    ${d.bombard.length ? '<div class="actions"><button id="bombard">Bombard…</button></div>' : ""}`;
  side.querySelectorAll("#prodlist .item").forEach((el) => el.onclick = () => send({ kind: "set_production", city: c.id, items: [el.dataset.item] }));
  $("focus").onchange = (e) => send({ kind: "set_focus", city: c.id, focus: e.target.value });
  if ($("buy")) $("buy").onclick = () => send({ kind: "purchase", city: c.id });
  if ($("bombard")) $("bombard").onclick = () => { S.targetMode = "bombard"; draw(); toast("Click a red hex to bombard."); };
  side.classList.remove("hidden");
}

// ---------------------------------------------------------------------------------------------
// commands

async function send(cmd) {
  if (S.busy) return;
  S.busy = true;
  try {
    const res = await api("/api/command", cmd);
    if (res.ok === false) toast(res.error);
  } catch (err) { toast(err.message); }
  S.busy = false;
  await refresh(true);
}

async function endTurn() {
  if (S.busy || S.view.outcome) return;
  const units = S.view.pending.filter((p) => p.kind === "unit_needs_orders").length;
  const other = S.view.pending.length - units;
  const now = Date.now();
  if (other && !(S.confirmUntil && now < S.confirmUntil)) {
    S.confirmUntil = now + 5000;
    toast(`${other} decision(s) still open. Press Next turn again to end the turn anyway.`);
    return;
  }
  S.confirmUntil = 0;
  S.busy = true;
  $("endturn").textContent = "Aliens moving…";
  try { await api("/api/end_turn", {}); } catch (err) { toast(err.message); }
  S.busy = false;
  await refresh(true);
}
$("endturn").onclick = endTurn;

// ---------------------------------------------------------------------------------------------
// map input

let drag = null;
canvas.addEventListener("mousedown", (e) => { drag = { x: e.clientX, y: e.clientY, cx: S.cam.x, cy: S.cam.y, moved: false }; });
window.addEventListener("mouseup", (e) => {
  if (drag && !drag.moved && e.target === canvas && e.button === 0) onClick(e);
  drag = null; canvas.classList.remove("dragging");
});
canvas.addEventListener("mousemove", (e) => {
  if (drag) {
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; canvas.classList.add("dragging"); }
    if (drag.moved) { S.cam.x = drag.cx - dx / S.cam.zoom; S.cam.y = drag.cy - dy / S.cam.zoom; draw(); }
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const i = pick(e.clientX - rect.left, e.clientY - rect.top);
  if (i !== S.hover) { S.hover = i; draw(); }
  showTooltip(i, e.clientX - rect.left, e.clientY - rect.top);
});
canvas.addEventListener("mouseleave", () => { S.hover = null; $("tooltip").classList.add("hidden"); draw(); });
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const [wx, wy] = toWorld(mx, my);
  S.cam.zoom = Math.max(0.25, Math.min(2.5, S.cam.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
  S.cam.x = wx - mx / S.cam.zoom; S.cam.y = wy - my / S.cam.zoom;
  draw();
}, { passive: false });
canvas.addEventListener("contextmenu", (e) => { e.preventDefault(); clearSelection(); });

async function onClick(e) {
  const rect = canvas.getBoundingClientRect();
  const i = pick(e.clientX - rect.left, e.clientY - rect.top);
  if (i === null) return;
  if (S.targetMode === "bombard" && S.city) {
    if (S.city.bombard.includes(i)) return send({ kind: "city_attack", city: S.city.city.id, target: i });
    S.targetMode = null; draw();
  }
  if (S.options) {
    const u = S.options.unit;
    if (S.options.attacks.some((a) => a.tile === i)) return send({ kind: "attack", unit: u.id, target: i });
    if (S.options.reachable.includes(i)) return send({ kind: "move_unit", unit: u.id, target: i });
  }
  const mine = (S.unitsByTile.get(i) || []).filter((u) => u.owner === S.view.me);
  const city = S.citiesByTile.get(i);
  if (mine.length) {
    let next = mine[0];
    if (S.selected && S.selected.kind === "unit") {
      const k = mine.findIndex((u) => u.id === S.selected.id);
      if (k >= 0) next = mine[(k + 1) % mine.length];
      if (k >= 0 && k === mine.length - 1 && city && city.owner === S.view.me) return selectCity(city.id);
    }
    return selectUnit(next.id);
  }
  if (city && city.owner === S.view.me) return selectCity(city.id);
  clearSelection();
}

function showTooltip(i, x, y) {
  const tip = $("tooltip");
  if (i === null) { tip.classList.add("hidden"); return; }
  let html = "";
  const attack = S.options && S.options.attacks.find((a) => a.tile === i);
  if (attack) html = previewHtml(attack.preview);
  else {
    const t = S.tilesByIndex.get(i);
    const c = S.citiesByTile.get(i);
    const us = S.unitsByTile.get(i) || [];
    if (t) {
      html += `<b>${pretty(t.terrain)}</b>${t.elevation !== "flat" ? ` · ${t.elevation}` : ""}${t.feature ? ` · ${t.feature}` : ""}`;
      if (t.resource && t.visible) html += `<br>Resource: ${pretty(t.resource)}`;
      if (t.improvement || t.route) html += `<br>${[t.improvement, t.route].filter(Boolean).map(pretty).join(", ")}`;
      if (!t.visible) html += '<br><span class="muted">not currently seen</span>';
    } else if (S.explored.has(i)) html = '<span class="muted">Fog: explored, not seen now</span>';
    else html = '<span class="muted">Unexplored</span>';
    if (c) html += `<br><b>${esc(c.name)}</b> · ${c.status}${c.owner ? ` · ${pretty(c.owner)}` : ""} · pop ${c.pop}`;
    for (const u of us) html += `<br>${pretty(u.owner)}: ${pretty(u.type)}${u.count > 1 ? " ×2" : ""} (${u.hp} HP)`;
  }
  tip.innerHTML = html;
  tip.classList.remove("hidden");
  tip.style.left = `${Math.min(x + 16, canvas.clientWidth - 330)}px`;
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
function previewHtml(p) {
  if (p.kind === "capture") return "<b>Capture</b><br>Only civilians stand here.";
  const dd = p.damage_to_defender, da = p.damage_to_attacker;
  return `<b>${p.kind === "ranged" ? "Ranged attack" : "Melee attack"}</b>
    <table><tr><th>You</th><th>Defender</th></tr>
    <tr><td>${(p.attacker.strength / 100).toFixed(1)}</td><td>${(p.defender.strength / 100).toFixed(1)}</td></tr>
    <tr><td class="muted">${strengthLines(p.attacker)}</td><td class="muted">${strengthLines(p.defender)}</td></tr>
    <tr><td>takes <b class="bad">${da.expected}</b> <span class="muted">(${da.min}-${da.max})</span><br>HP ${p.attacker.hp}</td>
        <td>takes <b class="good">${dd.expected}</b> <span class="muted">(${dd.min}-${dd.max})</span><br>HP ${p.defender.hp}</td></tr></table>`;
}

window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.key === "Escape") { if (!$("modal").classList.contains("hidden")) closeModal(); else clearSelection(); }
  else if (e.key === "Enter") endTurn();
  else if (e.key === " " || e.key === "n") { e.preventDefault(); const p = S.view.pending.find((x) => x.kind === "unit_needs_orders"); if (p) resolvePending(p); }
  else if (e.key === "f" && S.options) send({ kind: "fortify", unit: S.options.unit.id });
  else if (e.key === "s" && S.options) send({ kind: "skip_unit", unit: S.options.unit.id });
  else if (e.key === "t") openScreen("techs");
  else if (e.key === "c") openScreen("council");
  else if (e.key === "d") openScreen("diplomacy");
  else if (e.key === "p") openScreen("projects");
  else if (e.key.startsWith("Arrow")) {
    const d = 120 / S.cam.zoom;
    if (e.key === "ArrowLeft") S.cam.x -= d; if (e.key === "ArrowRight") S.cam.x += d;
    if (e.key === "ArrowUp") S.cam.y -= d; if (e.key === "ArrowDown") S.cam.y += d;
    draw();
  }
});

// ---------------------------------------------------------------------------------------------
// screens (modal)

document.querySelectorAll("#topbar nav button").forEach((b) => b.onclick = () => openScreen(b.dataset.screen));
document.querySelector("#modal .close").onclick = closeModal;
$("modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
function closeModal() { $("modal").classList.add("hidden"); S.screen = null; }

async function openScreen(name) {
  S.screen = name;
  const body = $("modal-body");
  try {
    if (name === "techs") body.innerHTML = techScreen(await api("/api/techs"));
    else if (name === "council") body.innerHTML = councilScreen(await api("/api/council"));
    else if (name === "diplomacy") body.innerHTML = diplomacyScreen(await api("/api/diplomacy"));
    else if (name === "projects") body.innerHTML = projectsScreen(await api("/api/projects"));
    else if (name === "scores") body.innerHTML = scoresScreen(await api("/api/scores"));
    else if (name === "menu") body.innerHTML = menuScreen(await api("/api/saves"));
  } catch (err) { toast(err.message); return; }
  $("modal").classList.remove("hidden");
  wireScreen(name);
}
async function act(cmd, screen) {
  try { const r = await api("/api/command", cmd); if (r.ok === false) toast(r.error); } catch (err) { toast(err.message); }
  await refresh(true);
  if (screen) openScreen(screen);
}

function techScreen(d) {
  const trees = ["economic", "production", "military", "beacon", "alien"];
  const cols = trees.map((tree) => {
    const rows = d.techs.filter((t) => t.tree === tree);
    const tiers = [...new Set(rows.map((t) => t.tier))].sort((a, b) => a - b);
    return `<div class="techcol"><h3>${pretty(tree)}${tree === "alien" ? " (espionage)" : ""}</h3>` + tiers.map((tier) =>
      `<div class="tier">${tree === "alien" ? "" : `Tier ${tier}`}</div>` + rows.filter((t) => t.tier === tier).map((t) =>
        `<div class="tech ${t.status}" data-tech="${t.id}" title="${esc(t.note)}">
          <div class="name">${esc(pretty(t.id))}</div>
          <div class="meta">${t.status === "known" ? "known" : t.cost ? `${t.cost} science` : ""}${t.status === "researching" ? ` · ${d.progress}/${t.cost}` : ""}</div>
          ${t.prereqs.length ? `<div class="meta">needs ${t.prereqs.map(pretty).join(", ")}</div>` : ""}
          ${t.unlocks.length ? `<div class="meta">unlocks ${t.unlocks.map((u) => pretty(u.split(":")[1])).join(", ")}</div>` : ""}
        </div>`).join("")).join("") + "</div>";
  }).join("");
  return `<h2>Technology</h2><div class="techgrid">${cols}</div>`;
}

function scoreChips(scores) {
  return Object.entries(scores).map(([d, v]) => `<span class="chip ${d}">${pretty(d)} +${v}%</span>`).join("");
}
function councilScreen(d) {
  const seatInfo = d.domains.map((x) => `<span class="chip ${x}">${pretty(x)} ${d.seats_used[x]}/${d.seats_per_domain} (+${d.bonus[x]}%)</span>`).join("") +
    `<span class="chip">General ${d.seats_used.general}/${d.general_seats}</span>`;
  const others = S.view.players.filter((p) => p.id !== S.view.me);
  const cards = d.recruits.map((r) => `<div class="card ${r.legendary ? "legendary" : ""}">
      <div class="title">${esc(r.name)}${r.legendary ? " ★" : ""}</div>
      <div class="muted">${pretty(r.kind)} · ${r.traits.map(pretty).join(", ")} · ${r.lifespan ? `age ${r.age}/${r.lifespan}` : "immortal"}${r.betrayal ? ` · <span class="bad">betrayal ${r.betrayal / 10}%/turn</span>` : ""}</div>
      <div>${scoreChips(r.scores)}</div>
      <div class="muted">Seats: ${r.seats.length ? r.seats.map(pretty).join(", ") : "none"}</div>
      <div class="actions">
        <button class="small" data-seat="${r.id}" data-seats="general">General seat</button>
        <button class="small" data-seat="${r.id}" data-seats="${Object.keys(r.scores).join(",")}">Domain seats</button>
        ${r.seats.length ? `<button class="small" data-unseat="${r.id}">Unseat</button>` : ""}
        <select data-giftto="${r.id}">${others.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select>
        <button class="small" data-gift="${r.id}">Gift</button>
      </div></div>`).join("");
  const offers = d.offers.map((o) => `<div class="row">${pretty(o.from_player)} offers recruit #${o.recruit} for ${o.price} gold
      <button class="small" data-accept-offer="${o.id}">Accept</button><button class="small" data-decline-offer="${o.id}">Decline</button></div>`).join("");
  return `<h2>Council</h2><div class="row">${seatInfo}</div>
    <p class="muted">A recruit on a domain seat adds its score there; one recruit may hold one seat in several domains. On a general seat it adds every score. Recruits arrive when beacon points reach the arrival cost.</p>
    ${offers ? `<h3>Offers</h3>${offers}` : ""}
    <div class="cards">${cards || '<p class="muted">No recruits yet. Research Beacon Theory and build a Beacon.</p>'}</div>`;
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
  const rows = d.players.map((p) => `<tr>
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
    <table><tr><th>Continent</th><th>Status</th><th>Actions</th></tr>${rows}</table>
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

function menuScreen(saves) {
  const players = S.view.players.map((p) => `<option value="${p.id}" ${p.id === S.view.me ? "selected" : ""}>${esc(p.name)}</option>`).join("");
  return `<h2>Menu</h2>
    <h3>New game</h3><div class="actions">Seed <input type="number" id="newseed" value="${S.view.seed}" style="width:80px"> Play as <select id="newhuman">${players}</select><button class="primary" id="newgame">Start</button></div>
    <h3>Save</h3><div class="actions"><input id="savename" value="turn${S.view.turn}"><button id="save">Save</button></div>
    <h3>Load</h3><div class="actions">${saves.length ? `<select id="loadname">${saves.map((s) => `<option>${esc(s)}</option>`).join("")}</select><button id="load">Load</button>` : '<span class="muted">No saves yet.</span>'}</div>
    <h3>Keys</h3><p class="muted">Enter: next turn · Space: next unit · F: fortify · S: skip · T/C/D/P: screens · arrows or drag: pan · wheel: zoom · right click: deselect</p>`;
}

function wireScreen(name) {
  const body = $("modal-body");
  const on = (sel, fn) => body.querySelectorAll(sel).forEach((el) => el.onclick = () => fn(el));
  if (name === "techs") on(".tech.available", (el) => act({ kind: "set_research", tech: el.dataset.tech }, null).then(closeModal));
  if (name === "council") {
    on("[data-seat]", (el) => act({ kind: "seat_recruit", recruit: Number(el.dataset.seat), seats: el.dataset.seats.split(",") }, "council"));
    on("[data-unseat]", (el) => act({ kind: "unseat_recruit", recruit: Number(el.dataset.unseat) }, "council"));
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
    $("newgame").onclick = async () => { await api("/api/new", { seed: Number($("newseed").value), human: $("newhuman").value }); closeModal(); S.shownOutcome = false; await start(); };
    $("save").onclick = async () => { try { await api("/api/save", { name: $("savename").value }); toast("Saved."); closeModal(); } catch (err) { toast(err.message); } };
    if ($("load")) $("load").onclick = async () => { try { await api("/api/load", { name: $("loadname").value }); closeModal(); await start(); } catch (err) { toast(err.message); } };
  }
}

// ---------------------------------------------------------------------------------------------
// start

async function start() {
  await refresh(false);
  const capital = Object.values(S.view.cities).find((c) => c.owner === S.view.me && c.is_capital);
  if (capital) { S.cam.zoom = 1.6; centerOnTile(capital.tile); }
}
window.addEventListener("resize", resize);
resize();
start().catch((err) => toast(err.message));
