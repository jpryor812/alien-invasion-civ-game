// The settlement sandbox (docs/SPEC_M15.md): one city, close up, in a tilted "Clash of Clans" view.
// Hexes are raised ground tiles; buildings stand in their slots; walls run along the outer edges.
"use strict";

const $ = (id) => document.getElementById(id);
const canvas = $("view"), ctx = canvas.getContext("2d");
const SQ3 = Math.sqrt(3), TILT = 0.58;
const DIRS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
const DIR_ANGLE = [0, -60, -120, 180, 120, 60];  // screen angle of each direction (pointy-top)
const G = { grain: { icon: "🌾", col: "#f3cf55" }, timber: { icon: "🪵", col: "#c58a4a" }, stone: { icon: "🪨", col: "#b9c0c8" }, iron: { icon: "⚙️", col: "#8fa7c4" } };
const S = { v: null, sel: null, hover: null, raid: null, t0: performance.now() };

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  return res.json();
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const pretty = (s) => String(s).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const costText = (c) => Object.entries(c || {}).map(([g, n]) => `${G[g] ? G[g].icon : ""}${n}`).join(" ");
function toast(msg) {
  const b = $("banner"); b.innerHTML = esc(msg); b.classList.remove("hidden");
  clearTimeout(toast.t); toast.t = setTimeout(() => b.classList.add("hidden"), 1600);
}

// -- images: photo ground textures and the painted features of the main game ------------------
const IMG = {};
for (const [k, src] of Object.entries({ grass: "terrain/grass.jpg", rock: "terrain/rock.jpg", tundra: "terrain/tundra.jpg",
  forest0: "features/forest_0.png", forest1: "features/forest_1.png", forest2: "features/forest_2.png", hills0: "features/hills_0.png", hills1: "features/hills_1.png" })) {
  const im = new Image(); im.src = src; im.onload = () => { IMG[k] = im; };
}
// Building sprites rendered in Blender (web/static/settlement/); drawn shapes stand in until loaded.
const SPRITE = {};
for (const k of ["city_hall", "farm", "lumber_camp", "quarry", "iron_mine", "granary", "warehouse", "house", "workshop", "watchtower"]) {
  const im = new Image(); im.src = `settlement/${k}.webp`; im.onload = () => { SPRITE[k] = im; };
}

// -- geometry -------------------------------------------------------------------------------
let R = 100, CX = 0, CY = 0;
function layout() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * devicePixelRatio; canvas.height = h * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  R = Math.min((w - 400) / (3.3 * SQ3), (h - 90) / (5 * TILT + 0.7));
  R = Math.max(60, R);
  CX = (w - 340) / 2 + 30; CY = h / 2 + R * 0.12;
}
function centre(h) { return [CX + R * SQ3 * (h.q + h.r / 2), CY + R * 1.5 * h.r * TILT]; }
function corner(x, y, k, r = R) { const a = (60 * k - 30) * Math.PI / 180; return [x + r * Math.cos(a), y + r * Math.sin(a) * TILT]; }
function edgeCorners(x, y, d) {  // the two corners of the edge facing direction d
  const a = DIR_ANGLE[d];
  const c1 = (((a - 30) % 360) + 360) % 360, c2 = (((a + 30) % 360) + 360) % 360;
  const k1 = Math.round((c1 + 30) / 60) % 6, k2 = Math.round((c2 + 30) / 60) % 6;
  return [corner(x, y, k1), corner(x, y, k2)];
}
function hexPath(x, y, r = R) { ctx.beginPath(); for (let k = 0; k < 6; k++) { const [px, py] = corner(x, y, k, r); k ? ctx.lineTo(px, py) : ctx.moveTo(px, py); } ctx.closePath(); }
function inHex(mx, my, x, y) {
  const dx = (mx - x) / R, dy = (my - y) / (R * TILT);
  const ax = Math.abs(dx), ay = Math.abs(dy);
  return ay <= 1 && ax <= SQ3 / 2 && ax * 0.5 + ay * SQ3 / 2 <= SQ3 / 2 + 1e-6 || (ax <= SQ3 / 2 && ay <= 0.5);
}
function slotPos(h, i, n) {
  const [x, y] = centre(h);
  if (h.q === 0 && h.r === 0) {
    if (i === 0) return [x, y + R * 0.05];
    const a = (-90 + (i - 1) * 72) * Math.PI / 180;
    return [x + Math.cos(a) * R * 0.66, y + Math.sin(a) * R * 0.66 * TILT + R * 0.08];
  }
  const sets = { 1: [[0, 0.1]], 2: [[-0.32, 0.05], [0.32, 0.12]], 3: [[-0.38, 0.12], [0.38, 0.12], [0, -0.32]] };
  const [ox, oy] = (sets[n] || sets[3])[i] || [0, 0];
  return [x + ox * R, y + oy * R * TILT * 1.6];
}

// -- drawing helpers ----------------------------------------------------------------------------
function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16), c = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return `rgb(${c.map((v) => Math.max(0, Math.min(255, Math.round(f >= 0 ? v + (255 - v) * f : v * (1 + f))))).join(",")})`;
}
// An oblique box: front face w x h standing on (x, y), depth going up-right.
function box(x, y, w, h, d, col, out = "#2a1b0c") {
  const dx = d * 0.45, dy = -d * TILT * 0.75;
  ctx.lineJoin = "round"; ctx.lineWidth = Math.max(1, R * 0.018); ctx.strokeStyle = out;
  ctx.fillStyle = shade(col, -0.32);  // side
  ctx.beginPath(); ctx.moveTo(x + w / 2, y); ctx.lineTo(x + w / 2 + dx, y + dy); ctx.lineTo(x + w / 2 + dx, y + dy - h); ctx.lineTo(x + w / 2, y - h); ctx.closePath(); ctx.fill(); ctx.stroke();
  ctx.fillStyle = shade(col, 0.22);  // top
  ctx.beginPath(); ctx.moveTo(x - w / 2, y - h); ctx.lineTo(x + w / 2, y - h); ctx.lineTo(x + w / 2 + dx, y + dy - h); ctx.lineTo(x - w / 2 + dx, y + dy - h); ctx.closePath(); ctx.fill(); ctx.stroke();
  ctx.fillStyle = col;  // front
  ctx.fillRect(x - w / 2, y - h, w, h); ctx.strokeRect(x - w / 2, y - h, w, h);
  return { dx, dy };
}
function gable(x, y, w, d, rise, col) {  // a pitched roof over a box of width w (top at y)
  const dx = d * 0.45, dy = -d * TILT * 0.75, o = "#2a1b0c";
  ctx.lineWidth = Math.max(1, R * 0.018); ctx.strokeStyle = o;
  ctx.fillStyle = shade(col, -0.25);
  ctx.beginPath(); ctx.moveTo(x + w / 2 + 2, y); ctx.lineTo(x + w / 2 + dx + 2, y + dy); ctx.lineTo(x + dx, y + dy - rise); ctx.lineTo(x, y - rise); ctx.closePath(); ctx.fill(); ctx.stroke();
  ctx.fillStyle = col;
  ctx.beginPath(); ctx.moveTo(x - w / 2 - 3, y); ctx.lineTo(x + w / 2 + 3, y); ctx.lineTo(x, y - rise); ctx.closePath(); ctx.fill(); ctx.stroke();
  ctx.fillStyle = shade(col, 0.25);
  ctx.beginPath(); ctx.moveTo(x - w / 2 - 3, y); ctx.lineTo(x, y - rise); ctx.lineTo(x + dx, y + dy - rise); ctx.lineTo(x - w / 2 - 3 + dx, y + dy); ctx.closePath(); ctx.fill(); ctx.stroke();
}
function shadow(x, y, rx) { ctx.fillStyle = "rgba(0,0,0,0.28)"; ctx.beginPath(); ctx.ellipse(x + rx * 0.15, y + rx * 0.05, rx, rx * TILT * 0.55, 0, 0, Math.PI * 2); ctx.fill(); }
function door(x, y, w, h) { ctx.fillStyle = "#3a2410"; ctx.fillRect(x - w / 2, y - h, w, h); }
function windowAt(x, y, s) { ctx.fillStyle = "#ffe9a6"; ctx.fillRect(x - s / 2, y - s / 2, s, s); ctx.strokeStyle = "#3a2410"; ctx.lineWidth = 1; ctx.strokeRect(x - s / 2, y - s / 2, s, s); }

// The buildings, drawn in code (a Blender sprite replaces each once rendered).
const DRAW = {
  city_hall(x, y, s, t) {
    shadow(x, y, s * 0.75);
    box(x, y, s * 1.0, s * 0.45, s * 0.6, "#c9b28a");
    gable(x, y - s * 0.45, s * 1.0, s * 0.6, s * 0.38, "#b63a2c");
    box(x - s * 0.05, y - s * 0.45 - s * 0.05, s * 0.28, s * 0.62, s * 0.25, "#d8c39b");
    gable(x - s * 0.05, y - s * 1.07 - s * 0.05, s * 0.28, s * 0.25, s * 0.22, "#8e2a20");
    door(x, y, s * 0.16, s * 0.24); windowAt(x - s * 0.3, y - s * 0.26, s * 0.1); windowAt(x + s * 0.3, y - s * 0.26, s * 0.1);
    const fx = x - s * 0.05, fy = y - s * 1.35;  // the flag
    ctx.strokeStyle = "#3a2410"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(fx, fy + s * 0.12); ctx.lineTo(fx, fy - s * 0.3); ctx.stroke();
    const wv = Math.sin(t / 300) * s * 0.03;
    ctx.fillStyle = "#3f7fe0"; ctx.beginPath(); ctx.moveTo(fx, fy - s * 0.3); ctx.quadraticCurveTo(fx + s * 0.12, fy - s * 0.3 + wv, fx + s * 0.25, fy - s * 0.26); ctx.lineTo(fx + s * 0.25, fy - s * 0.12); ctx.quadraticCurveTo(fx + s * 0.12, fy - s * 0.16 + wv, fx, fy - s * 0.16); ctx.fill();
  },
  farm(x, y, s) {
    ctx.fillStyle = "#c79a3a"; ctx.beginPath(); ctx.ellipse(x - s * 0.1, y - s * 0.02, s * 0.62, s * 0.32 * TILT * 1.4, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#f1d16a"; ctx.lineWidth = Math.max(1.5, s * 0.04);
    for (let k = -3; k <= 3; k++) { ctx.beginPath(); ctx.moveTo(x - s * 0.62 + s * 0.04, y + k * s * 0.05); ctx.lineTo(x + s * 0.4, y + k * s * 0.05 - s * 0.04); ctx.stroke(); }
    shadow(x + s * 0.35, y - s * 0.05, s * 0.28);
    box(x + s * 0.35, y - s * 0.05, s * 0.36, s * 0.28, s * 0.3, "#b8452f");
    gable(x + s * 0.35, y - s * 0.33, s * 0.36, s * 0.3, s * 0.2, "#6b3a22");
    door(x + s * 0.35, y - s * 0.05, s * 0.12, s * 0.16);
  },
  lumber_camp(x, y, s) {
    shadow(x, y, s * 0.55);
    for (let k = 0; k < 3; k++) for (let j = 0; j < 3 - k; j++) {
      const lx = x - s * 0.35 + j * s * 0.15 + k * s * 0.075, ly = y - k * s * 0.12;
      ctx.fillStyle = "#9a6331"; ctx.strokeStyle = "#3a2410"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.ellipse(lx, ly - s * 0.06, s * 0.07, s * 0.07, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#e7c08a"; ctx.beginPath(); ctx.ellipse(lx, ly - s * 0.06, s * 0.04, s * 0.04, 0, 0, Math.PI * 2); ctx.fill();
    }
    box(x + s * 0.3, y, s * 0.32, s * 0.24, s * 0.26, "#8a5a2b");
    gable(x + s * 0.3, y - s * 0.24, s * 0.32, s * 0.26, s * 0.18, "#4f6b2c");
  },
  quarry(x, y, s) {
    shadow(x, y, s * 0.6);
    ctx.fillStyle = "#6f6a63"; ctx.beginPath(); ctx.ellipse(x, y - s * 0.02, s * 0.55, s * 0.3 * TILT * 1.3, 0, 0, Math.PI * 2); ctx.fill();
    box(x - s * 0.2, y + s * 0.02, s * 0.3, s * 0.18, s * 0.25, "#a9a49b");
    box(x + s * 0.18, y - s * 0.02, s * 0.26, s * 0.3, s * 0.22, "#c3beb4");
    box(x, y - s * 0.12, s * 0.22, s * 0.14, s * 0.2, "#b3aea4");
    ctx.strokeStyle = "#5a3a1a"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x + s * 0.42, y); ctx.lineTo(x + s * 0.5, y - s * 0.55); ctx.lineTo(x + s * 0.25, y - s * 0.62); ctx.stroke();
  },
  iron_mine(x, y, s) {
    shadow(x, y, s * 0.6);
    ctx.fillStyle = "#7c746a"; ctx.strokeStyle = "#2a1b0c"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x - s * 0.55, y); ctx.quadraticCurveTo(x - s * 0.3, y - s * 0.7, x + s * 0.05, y - s * 0.62); ctx.quadraticCurveTo(x + s * 0.45, y - s * 0.55, x + s * 0.55, y); ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#1c140c"; ctx.beginPath(); ctx.moveTo(x - s * 0.16, y); ctx.lineTo(x - s * 0.16, y - s * 0.24); ctx.quadraticCurveTo(x, y - s * 0.38, x + s * 0.16, y - s * 0.24); ctx.lineTo(x + s * 0.16, y); ctx.fill();
    ctx.strokeStyle = "#8a5a2b"; ctx.lineWidth = Math.max(2, s * 0.05); ctx.beginPath(); ctx.moveTo(x - s * 0.18, y); ctx.lineTo(x - s * 0.18, y - s * 0.26); ctx.quadraticCurveTo(x, y - s * 0.4, x + s * 0.18, y - s * 0.26); ctx.lineTo(x + s * 0.18, y); ctx.stroke();
    box(x + s * 0.36, y + s * 0.02, s * 0.2, s * 0.12, s * 0.14, "#5d6b78");
    ctx.fillStyle = "#3b4550"; ctx.beginPath(); ctx.arc(x + s * 0.3, y + s * 0.03, s * 0.035, 0, 7); ctx.arc(x + s * 0.43, y + s * 0.03, s * 0.035, 0, 7); ctx.fill();
  },
  granary(x, y, s) {
    shadow(x, y, s * 0.4);
    const w = s * 0.42, h = s * 0.62;
    const g = ctx.createLinearGradient(x - w / 2, 0, x + w / 2, 0); g.addColorStop(0, "#d9c08e"); g.addColorStop(0.6, "#bfa06a"); g.addColorStop(1, "#8b7144");
    ctx.fillStyle = g; ctx.strokeStyle = "#2a1b0c"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x - w / 2, y - h); ctx.lineTo(x - w / 2, y); ctx.ellipse(x, y, w / 2, w * 0.22, 0, Math.PI, 0, true); ctx.lineTo(x + w / 2, y - h); ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#b5462f"; ctx.beginPath(); ctx.moveTo(x - w / 2 - 3, y - h); ctx.lineTo(x, y - h - s * 0.32); ctx.lineTo(x + w / 2 + 3, y - h); ctx.ellipse(x, y - h, w / 2 + 3, w * 0.2, 0, 0, Math.PI); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = "rgba(60,40,20,0.5)"; for (let k = 1; k < 4; k++) { ctx.beginPath(); ctx.ellipse(x, y - h * k / 4, w / 2, w * 0.2, 0, 0, Math.PI); ctx.stroke(); }
  },
  warehouse(x, y, s) {
    shadow(x, y, s * 0.6);
    box(x, y, s * 0.78, s * 0.36, s * 0.42, "#8f7a5e");
    gable(x, y - s * 0.36, s * 0.78, s * 0.42, s * 0.14, "#56606a");
    ctx.fillStyle = "#4a3418"; ctx.fillRect(x - s * 0.17, y - s * 0.28, s * 0.34, s * 0.28);
    ctx.strokeStyle = "#c9a76a"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(x - s * 0.17, y - s * 0.28); ctx.lineTo(x + s * 0.17, y); ctx.moveTo(x + s * 0.17, y - s * 0.28); ctx.lineTo(x - s * 0.17, y); ctx.stroke();
  },
  house(x, y, s) {
    shadow(x, y, s * 0.4);
    box(x, y, s * 0.46, s * 0.3, s * 0.34, "#e6d3a8");
    gable(x, y - s * 0.3, s * 0.46, s * 0.34, s * 0.24, "#3f6fc0");
    door(x - s * 0.08, y, s * 0.1, s * 0.16); windowAt(x + s * 0.1, y - s * 0.15, s * 0.08);
  },
  workshop(x, y, s, t) {
    shadow(x, y, s * 0.5);
    box(x, y, s * 0.6, s * 0.34, s * 0.38, "#9a6a3e");
    gable(x, y - s * 0.34, s * 0.6, s * 0.38, s * 0.18, "#7a3524");
    box(x + s * 0.2, y - s * 0.42, s * 0.1, s * 0.3, s * 0.1, "#6b6b6b");
    for (let k = 0; k < 3; k++) {  // smoke
      const p = ((t / 1600) + k / 3) % 1;
      ctx.fillStyle = `rgba(230,230,230,${0.5 * (1 - p)})`; ctx.beginPath(); ctx.arc(x + s * 0.24 + p * s * 0.2, y - s * 0.8 - p * s * 0.5, s * (0.05 + p * 0.08), 0, 7); ctx.fill();
    }
    door(x - s * 0.12, y, s * 0.14, s * 0.2);
  },
  watchtower(x, y, s) {
    shadow(x, y, s * 0.3);
    ctx.strokeStyle = "#5a3a1a"; ctx.lineWidth = Math.max(2, s * 0.05);
    ctx.beginPath(); ctx.moveTo(x - s * 0.16, y); ctx.lineTo(x - s * 0.1, y - s * 0.85); ctx.moveTo(x + s * 0.16, y); ctx.lineTo(x + s * 0.1, y - s * 0.85); ctx.moveTo(x - s * 0.15, y - s * 0.2); ctx.lineTo(x + s * 0.13, y - s * 0.5); ctx.moveTo(x + s * 0.15, y - s * 0.2); ctx.lineTo(x - s * 0.13, y - s * 0.5); ctx.stroke();
    box(x, y - s * 0.85, s * 0.34, s * 0.14, s * 0.25, "#8a5a2b");
    gable(x, y - s * 0.99, s * 0.34, s * 0.25, s * 0.18, "#a33a2a");
  },
};
function drawBuilding(kind, x, y, s, t) {
  const sp = SPRITE[kind];
  // the render's ground point (the model's origin) sits 65.4% down the image (camera 35 degrees up)
  if (sp) { const w = s * 2.1, h = w * sp.height / sp.width; ctx.drawImage(sp, x - w / 2, y - h * 0.654, w, h); return; }
  (DRAW[kind] || DRAW.house)(x, y, s, t);
}
function drawScaffold(x, y, s, frac) {
  shadow(x, y, s * 0.35);
  ctx.strokeStyle = "#b07a3a"; ctx.lineWidth = Math.max(1.5, s * 0.03);
  const w = s * 0.5, h = s * 0.5;
  ctx.strokeRect(x - w / 2, y - h, w, h);
  ctx.beginPath(); ctx.moveTo(x - w / 2, y); ctx.lineTo(x + w / 2, y - h); ctx.moveTo(x + w / 2, y); ctx.lineTo(x - w / 2, y - h); ctx.stroke();
  ctx.fillStyle = "rgba(0,0,0,0.55)"; ctx.fillRect(x - w / 2, y + 4, w, 6);
  ctx.fillStyle = "#6fb5ff"; ctx.fillRect(x - w / 2, y + 4, w * frac, 6);
}

// Walls: posts, blocks or plates along an outer edge, rising toward the viewer.
const WALL_COL = { wood: ["#8a5a2b", "#5a3a1a"], stone: ["#a9a49b", "#6a655e"], iron: ["#4f5d6b", "#2b333b"] };
function drawWall(a, b, material, hpFrac, hot) {
  const n = 9, hgt = R * (material === "wood" ? 0.22 : material === "stone" ? 0.2 : 0.24);
  const [c1, c2] = WALL_COL[material];
  for (let k = 0; k < n; k++) {
    const f = (k + 0.5) / n, x = a[0] + (b[0] - a[0]) * f, y = a[1] + (b[1] - a[1]) * f;
    const w = Math.hypot(b[0] - a[0], b[1] - a[1]) / n;
    ctx.fillStyle = k % 2 ? c1 : shade(c1, 0.1); ctx.strokeStyle = c2; ctx.lineWidth = 1;
    if (material === "wood") {
      ctx.beginPath(); ctx.moveTo(x - w * 0.42, y); ctx.lineTo(x - w * 0.42, y - hgt); ctx.lineTo(x, y - hgt - w * 0.5); ctx.lineTo(x + w * 0.42, y - hgt); ctx.lineTo(x + w * 0.42, y); ctx.closePath(); ctx.fill(); ctx.stroke();
    } else {
      ctx.fillRect(x - w * 0.52, y - hgt, w * 1.04, hgt); ctx.strokeRect(x - w * 0.52, y - hgt, w * 1.04, hgt);
      ctx.fillStyle = shade(c1, 0.3); ctx.fillRect(x - w * 0.52, y - hgt - 3, w * 1.04, 3);
      if (material === "iron") { ctx.fillStyle = "#9fe6ff"; ctx.fillRect(x - w * 0.52, y - hgt * 0.55, w * 1.04, 2); }
      if (material === "stone" && k % 2 === 0) { ctx.fillStyle = shade(c1, 0.3); ctx.fillRect(x - w * 0.3, y - hgt - 9, w * 0.6, 6); }
    }
  }
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2 - hgt - 12;  // HP bar
  ctx.fillStyle = "rgba(0,0,0,0.6)"; ctx.fillRect(mx - 18, my, 36, 5);
  ctx.fillStyle = hpFrac > 0.5 ? "#8ee06a" : hpFrac > 0.25 ? "#ffd24a" : "#ff7a66"; ctx.fillRect(mx - 18, my, 36 * hpFrac, 5);
  if (hot) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.strokeRect(mx - 19, my - 1, 38, 7); }
}

// -- the frame --------------------------------------------------------------------------------
function terrainFill(h) {
  const img = h.terrain === "hills" ? IMG.rock || IMG.grass : IMG.grass;
  if (!img) return h.terrain === "hills" ? "#8a8070" : "#5d9a3a";
  return ctx.createPattern(img, "repeat");
}
const TINT = { plains: "rgba(225,205,90,0.30)", grassland: "rgba(110,215,70,0.30)", forest: "rgba(40,120,40,0.30)", hills: "rgba(170,140,90,0.30)" };

function frame(t) {
  const v = S.v;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  // sky-ish ground beyond the territory: wild land, darker toward the edges
  const bg = ctx.createRadialGradient(CX, CY, R, CX, CY, Math.max(W, H));
  bg.addColorStop(0, "#4d7d36"); bg.addColorStop(0.55, "#355a26"); bg.addColorStop(1, "#1b2e14");
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  if (!v) { requestAnimationFrame(frame); return; }
  // wild hexes around (the land beyond the territory), faint
  for (let q = -4; q <= 4; q++) for (let r = -4; r <= 4; r++) {
    if (Math.abs(q + r) > 4 || (Math.abs(q) + Math.abs(r) + Math.abs(q + r)) / 2 <= 1) continue;
    const [x, y] = centre({ q, r }); hexPath(x, y, R * 0.98); ctx.strokeStyle = "rgba(255,255,255,0.05)"; ctx.lineWidth = 1; ctx.stroke();
  }
  const order = v.hexes.map((h, i) => [i, ...centre(h)]).sort((a, b) => a[2] - b[2]);
  // 1. the slabs: raised ground tiles
  const slab = R * 0.2;
  for (const [i, x, y] of order) {
    const h = v.hexes[i];
    ctx.fillStyle = "#6b4a2a";
    for (const k of [0, 1, 2]) {  // the three faces toward the viewer
      const [a1, b1] = corner(x, y, k), [a2, b2] = corner(x, y, k + 1);
      ctx.beginPath(); ctx.moveTo(a1, b1); ctx.lineTo(a2, b2); ctx.lineTo(a2, b2 + slab); ctx.lineTo(a1, b1 + slab); ctx.closePath();
      ctx.fillStyle = k === 1 ? "#7a5530" : "#5e4024"; ctx.fill();
    }
    hexPath(x, y); ctx.save(); ctx.clip();
    ctx.fillStyle = terrainFill(h); ctx.fillRect(x - R, y - R, 2 * R, 2 * R);
    ctx.fillStyle = TINT[h.terrain] || "transparent"; ctx.fillRect(x - R, y - R, 2 * R, 2 * R);
    const ig = ctx.createRadialGradient(x, y - R * 0.2, R * 0.2, x, y, R); ig.addColorStop(0, "rgba(255,250,210,0.18)"); ig.addColorStop(1, "rgba(0,0,0,0.18)");
    ctx.fillStyle = ig; ctx.fillRect(x - R, y - R, 2 * R, 2 * R);
    ctx.restore();
    hexPath(x, y, R * 0.97); ctx.strokeStyle = "rgba(255,250,200,0.35)"; ctx.lineWidth = 2; ctx.stroke();  // a bright rim, as on a game board
    hexPath(x, y); ctx.strokeStyle = S.sel && S.sel.hex === i && S.sel.edge == null ? "#ffe27a" : "rgba(40,25,10,0.55)"; ctx.lineWidth = S.sel && S.sel.hex === i && S.sel.edge == null ? 4 : 2; ctx.stroke();
    if (S.hover && S.hover.hex === i && S.hover.edge == null) { hexPath(x, y); ctx.fillStyle = "rgba(255,240,180,0.12)"; ctx.fill(); }
  }
  // 2. what grows or lies on each hex, behind the buildings
  for (const [i, x, y] of order) {
    const h = v.hexes[i];
    if (h.terrain === "forest") {
      const f = [IMG.forest0, IMG.forest1, IMG.forest2].filter(Boolean);
      for (let k = 0; k < 8; k++) {
        const a = k * 0.8 + i, rr = R * (0.6 + (k % 2) * 0.12);
        const fx = x + Math.cos(a) * rr * 0.85, fy = y + Math.sin(a) * rr * TILT * 0.8;
        if (f.length) { const im = f[k % f.length], w = R * 0.42; ctx.drawImage(im, fx - w / 2, fy - w * 0.85, w, w * im.height / im.width); }
        else { ctx.fillStyle = "#2f6b2a"; ctx.beginPath(); ctx.arc(fx, fy - R * 0.1, R * 0.1, 0, 7); ctx.fill(); }
      }
    }
    if (h.terrain === "hills") {  // rocky knolls around the edge of the hex
      for (const [ox, oy, sz] of [[-0.62, -0.25, 0.2], [0.6, -0.3, 0.17], [-0.15, -0.62, 0.15], [0.55, 0.45, 0.13], [-0.6, 0.4, 0.12]]) {
        const rx = x + ox * R, ry = y + oy * R * TILT, rr = sz * R;
        ctx.fillStyle = "rgba(0,0,0,0.25)"; ctx.beginPath(); ctx.ellipse(rx + rr * 0.2, ry + rr * 0.15, rr, rr * 0.45, 0, 0, 7); ctx.fill();
        const g = ctx.createLinearGradient(rx - rr, ry - rr, rx + rr, ry); g.addColorStop(0, "#cfc4ae"); g.addColorStop(1, "#7d7262");
        ctx.fillStyle = g; ctx.strokeStyle = "#4a4034"; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(rx - rr, ry); ctx.quadraticCurveTo(rx - rr * 0.6, ry - rr * 1.1, rx, ry - rr * 0.95); ctx.quadraticCurveTo(rx + rr * 0.7, ry - rr * 0.9, rx + rr, ry); ctx.closePath(); ctx.fill(); ctx.stroke();
      }
    }
    if (h.resource === "iron") { ctx.fillStyle = "#4a5a6a"; for (const [ox, oy] of [[-0.2, 0.5], [0.15, 0.55], [0, 0.45]]) { ctx.beginPath(); ctx.arc(x + ox * R, y + oy * R * TILT, R * 0.04, 0, 7); ctx.fill(); } }
    if (h.resource === "grain" && !h.buildings.includes("farm")) {  // wild grain
      ctx.strokeStyle = "rgba(240,210,110,0.55)"; ctx.lineWidth = 2;
      for (let k = 0; k < 9; k++) { const gx = x + (hash(i, k) - 0.5) * R * 1.1, gy = y + (hash(i, k + 9) - 0.2) * R * 0.6 * TILT; ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(gx + 2, gy - R * 0.08); ctx.stroke(); }
    }
  }
  // 3. walls on the back edges, then buildings by depth, then walls on the front edges
  const walls = [];
  for (const [i, x, y] of order) {
    const h = v.hexes[i];
    for (const d of h.outer) {
      const [a, b] = edgeCorners(x, y, d), key = `${i}:${d}`;
      walls.push({ i, d, a, b, y: (a[1] + b[1]) / 2, w: v.walls[key], key });
    }
  }
  const items = [];
  for (const w of walls) items.push({ y: w.y - (w.y > CY ? 0 : 1000), draw: () => drawEdge(w) });
  for (const [i] of order) {
    const h = v.hexes[i], all = [...h.buildings.map((b) => [b, false]), ...h.queued.map((b) => [b, true])];
    const n = h.slots;
    for (let k = 0; k < n; k++) {
      const [sx, sy] = slotPos(h, k, n);
      const it = all[k];
      items.push({ y: sy, draw: () => {
        const s = R * (h.q === 0 && h.r === 0 && k === 0 ? 0.78 : h.q === 0 && h.r === 0 ? 0.4 : 0.5);
        if (!it) { if (S.sel && S.sel.hex === i && S.sel.edge == null) { ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(255,240,180,0.8)"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.ellipse(sx, sy, R * 0.16, R * 0.16 * TILT, 0, 0, 7); ctx.stroke(); ctx.setLineDash([]); } return; }
        const [kind, queued] = it;
        if (queued) { const q = v.queue.find((o) => o.kind === "building" && o.hex === i && o.what === kind); const tot = (v.buildings[kind] || {}).labour || 1; drawScaffold(sx, sy, s, q ? 1 - q.labour_left / tot : 0); }
        else drawBuilding(kind, sx, sy, s, t);
      } });
    }
  }
  items.sort((p, q) => p.y - q.y).forEach((it) => it.draw());
  // 4. the raid: arrows toward the struck hex and its strength against the defence
  if (v.raid.seen && v.raid.hex != null) drawRaidWarning(v.hexes[v.raid.hex], v.raid, t);
  if (S.raid) drawRaidScene(t);
  requestAnimationFrame(frame);
}
function hash(a, b) { const x = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return x - Math.floor(x); }
function drawEdge(w) {
  const hot = S.hover && S.hover.hex === w.i && S.hover.edge === w.d, sel = S.sel && S.sel.hex === w.i && S.sel.edge === w.d;
  if (w.w) { drawWall(w.a, w.b, w.w.material, w.w.hp / S.v.wall_types[w.w.material].hp, hot || sel); return; }
  const q = S.v.queue.find((o) => o.kind === "wall" && o.hex === w.i && o.edge === w.d);
  ctx.setLineDash([6, 5]); ctx.lineWidth = hot || sel ? 4 : 2;
  ctx.strokeStyle = q ? "#6fb5ff" : hot || sel ? "rgba(255,230,140,0.95)" : "rgba(255,230,160,0.28)";
  ctx.beginPath(); ctx.moveTo(w.a[0], w.a[1]); ctx.lineTo(w.b[0], w.b[1]); ctx.stroke(); ctx.setLineDash([]);
}
function drawRaidWarning(h, raid, t) {
  const [x, y] = centre(h), d = Math.atan2(y - CY, x - CX) || 0, pulse = 0.6 + 0.4 * Math.sin(t / 220);
  for (const off of [-0.35, 0, 0.35]) {
    const a = d + off, fx = x + Math.cos(a) * R * 2.1, fy = y + Math.sin(a) * R * 2.1 * TILT, tx = x + Math.cos(a) * R * 1.05, ty = y + Math.sin(a) * R * 1.05 * TILT;
    ctx.strokeStyle = `rgba(230,50,40,${0.8 * pulse})`; ctx.lineWidth = 6; ctx.setLineDash([12, 8]);
    ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(tx, ty); ctx.stroke(); ctx.setLineDash([]);
    const ang = Math.atan2(ty - fy, tx - fx); ctx.fillStyle = `rgba(230,50,40,${pulse})`;
    ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx - Math.cos(ang - 0.45) * 18, ty - Math.sin(ang - 0.45) * 18); ctx.lineTo(tx - Math.cos(ang + 0.45) * 18, ty - Math.sin(ang + 0.45) * 18); ctx.fill();
  }
  const bx = x + Math.cos(d) * R * 2.25, by = y + Math.sin(d) * R * 2.25 * TILT;
  ctx.fillStyle = "#5a0f0a"; ctx.strokeStyle = `rgba(255,140,110,${pulse})`; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.arc(bx, by, 26, 0, 7); ctx.fill(); ctx.stroke();
  ctx.fillStyle = "#ffe2dc"; ctx.font = "700 20px Roboto, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(raid.turns ? String(raid.turns) : "!", bx, by - 2);
  ctx.font = "700 11px Roboto, sans-serif"; ctx.fillText(raid.turns ? "turns" : "now", bx, by + 14);
}
// The raid scene (SPEC_M15): raiders march to the struck hex, hit the wall, the result shows.
function drawRaidScene(t) {
  const r = S.raid, h = S.v.hexes[r.hex], [x, y] = centre(h), d = Math.atan2(y - CY, x - CX) || 0;
  const p = Math.min(1, (t - r.start) / 2200);
  const march = Math.min(1, p / 0.6), hit = p > 0.6;
  for (let k = 0; k < 9; k++) {
    const a = d + (hash(k, 3) - 0.5) * 0.9, dist = R * (2.6 - 1.55 * march) + hash(k, 7) * R * 0.3;
    const ux = x + Math.cos(a) * dist, uy = y + Math.sin(a) * dist * TILT;
    const bob = Math.sin(t / 90 + k) * 2;
    ctx.fillStyle = "rgba(0,0,0,0.3)"; ctx.beginPath(); ctx.ellipse(ux, uy + 2, 8, 3, 0, 0, 7); ctx.fill();
    ctx.fillStyle = "#7a1f3a"; ctx.beginPath(); ctx.ellipse(ux, uy - 9 + bob, 6, 9, 0, 0, 7); ctx.fill();
    ctx.fillStyle = "#c0ff6a"; ctx.beginPath(); ctx.arc(ux - 2, uy - 13 + bob, 1.6, 0, 7); ctx.arc(ux + 2, uy - 13 + bob, 1.6, 0, 7); ctx.fill();
  }
  if (hit) {
    const f = (p - 0.6) / 0.4, ex = x + Math.cos(d) * R * 0.95, ey = y + Math.sin(d) * R * 0.95 * TILT;
    for (let k = 0; k < 6; k++) {
      const a = k * 1.05 + t / 120, rr = R * 0.12 + f * R * 0.35;
      ctx.fillStyle = `rgba(255,${180 - k * 20},60,${0.8 * (1 - f)})`; ctx.beginPath(); ctx.arc(ex + Math.cos(a) * rr, ey + Math.sin(a) * rr * TILT, 6 + f * 8, 0, 7); ctx.fill();
    }
    if (!r.held) { ctx.fillStyle = `rgba(255,90,40,${0.35 * (1 - f)})`; hexPath(x, y); ctx.fill(); }
  }
  if (p >= 1 && !r.shown) {
    r.shown = true;
    const b = $("banner");
    b.innerHTML = r.held ? `The walls held!<small>Raid ${r.strength} against your defence ${r.defence}. The walls took the blows.</small>`
      : `The raiders broke through<small>Raid ${r.strength} against defence ${r.defence}.${r.wrecked ? ` They wrecked your ${pretty(r.wrecked).toLowerCase()}` : ""}${Object.keys(r.burned || {}).length ? `${r.wrecked ? " and" : " They"} burned ${Object.entries(r.burned).map(([g, n]) => `${n} ${g}`).join(", ")}` : ""}.</small>`;
    b.style.borderColor = r.held ? "#8ee06a" : "#ff7a66";
    b.classList.remove("hidden");
    setTimeout(() => { b.classList.add("hidden"); b.style.borderColor = ""; S.raid = null; }, 2600);
  }
}

// -- input -------------------------------------------------------------------------------------
function pickAt(mx, my) {
  const v = S.v; if (!v) return null;
  let best = null;
  v.hexes.forEach((h, i) => {
    const [x, y] = centre(h);
    for (const d of h.outer) {
      const [a, b] = edgeCorners(x, y, d), ex = (a[0] + b[0]) / 2, ey = (a[1] + b[1]) / 2;
      const dist = Math.hypot(mx - ex, (my - ey) / TILT);
      if (dist < R * 0.28 && (!best || dist < best.dist)) best = { hex: i, edge: d, dist };
    }
  });
  if (best) return { hex: best.hex, edge: best.edge };
  for (let i = 0; i < v.hexes.length; i++) { const [x, y] = centre(v.hexes[i]); if (inHex(mx, my, x, y)) return { hex: i, edge: null }; }
  return null;
}
canvas.addEventListener("mousemove", (e) => { const r = canvas.getBoundingClientRect(); S.hover = pickAt(e.clientX - r.left, e.clientY - r.top); });
canvas.addEventListener("click", (e) => { const r = canvas.getBoundingClientRect(); S.sel = pickAt(e.clientX - r.left, e.clientY - r.top); renderPanel(); });
document.addEventListener("mouseover", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]"), tip = $("tip");
  if (!el) { tip.classList.add("hidden"); return; }
  tip.innerHTML = el.dataset.tip; tip.classList.remove("hidden");
  const r = el.getBoundingClientRect(); tip.style.left = `${Math.min(innerWidth - 290, r.left)}px`; tip.style.top = `${r.bottom + 6}px`;
});

// -- panels ------------------------------------------------------------------------------------
const HEX_NAME = { plains: "Plains", grassland: "Grassland", forest: "Forest", hills: "Hills" };
function renderBar() {
  const v = S.v;
  $("goods").innerHTML = Object.keys(G).map((g) => {
    const net = (v.harvest[g] || 0) - (g === "grain" ? v.eats : 0), pct = Math.min(100, 100 * v.goods[g] / v.caps[g]);
    const tip = `<b>${v.goods_info[g].name}</b><div>${v.goods[g]} stored of ${v.caps[g]} room</div><div>+${v.harvest[g]} a turn from staffed buildings${g === "grain" ? `, -${v.eats} eaten` : ""}</div><div class="muted">More than the room is lost at the turn's end: build granaries and warehouses.</div>`;
    return `<div class="good-chip" data-tip="${esc(tip)}"><i style="background:${G[g].col}">${G[g].icon}</i><div style="flex:1"><div><span class="num">${v.goods[g]}</span><span class="muted">/${v.caps[g]}</span> <span class="delta ${net >= 0 ? "good" : "bad"}">${net >= 0 ? "+" : ""}${net}</span></div><div class="bar"><b style="width:${pct}%;background:${G[g].col}"></b></div></div></div>`;
  }).join("");
  $("stats").innerHTML = `<span data-tip="Gold: from selling at the Exchange.">🪙 ${v.gold}</span>
    <span data-tip="${esc(`People ${v.pop} of ${v.room} room. Each eats 2 grain a turn; with room and ${v.grow_cost} spare grain the city grows.${v.idle_buildings ? ` ${v.idle_buildings} building(s) have no worker.` : ""}`)}">👥 ${v.pop}/${v.room}${v.idle_buildings ? ` <b class="bad">(${v.idle_buildings} idle)</b>` : ""}</span>
    <span data-tip="Labour each turn for construction (workshops add more).">🔨 ${v.labour}</span>
    <span data-tip="City strength: every building adds some; walls add more on their hex.">🛡 ${v.strength}</span>
    <span>Turn ${v.turn}</span>`;
  const raid = $("raid");
  if (v.raid.seen) { raid.classList.remove("hidden"); const def = v.hexes[v.raid.hex].defence; raid.innerHTML = `⚠ Raid on the ${HEX_NAME[v.hexes[v.raid.hex].terrain].toLowerCase()} ${v.raid.turns ? `in ${v.raid.turns} turn${v.raid.turns === 1 ? "" : "s"}` : "at the end of this turn"}: strength <b>${v.raid.strength}</b> against your <b class="${def >= v.raid.strength ? "good" : "bad"}">${def}</b> there`; }
  else raid.classList.add("hidden");
}
function renderPanel() {
  const v = S.v, p = $("panel"), sel = S.sel;
  if (!sel) {
    p.innerHTML = `<h2>Your settlement</h2><div class="sub">Click a hex to build in its slots, or an outer edge (dashed) to raise a wall.</div>
      <div class="muted">Goods come from staffed buildings on the land. Construction costs materials when you order it and labour over the next turns. Raiders come every few turns; you see them two turns ahead.</div>`;
    return;
  }
  const h = v.hexes[sel.hex];
  if (sel.edge != null) {
    const key = `${sel.hex}:${sel.edge}`, cur = v.walls[key];
    const opts = Object.entries(v.wall_types).map(([k, w]) => {
      const short = Object.entries(w.cost).filter(([g, n]) => v.goods[g] < n).map(([g, n]) => `${n - v.goods[g]} ${g}`);
      const why = short.length ? `short of ${short.join(", ")}` : cur && Object.keys(v.wall_types).indexOf(k) <= Object.keys(v.wall_types).indexOf(cur.material) && cur.hp >= w.hp ? "already as strong" : "";
      return `<button class="opt" data-wall="${k}" ${why ? "disabled" : ""}><span>${esc(w.name)} <span class="muted">· strength ${w.strength}, ${w.hp} HP</span></span><span class="cost">${costText(w.cost)} · ${w.labour} labour</span>${why ? `<span class="why">${esc(why)}</span>` : ""}</button>`;
    }).join("");
    p.innerHTML = `<h2>Wall · ${HEX_NAME[h.terrain]}</h2><div class="sub">${cur ? `${esc(v.wall_types[cur.material].name)}: ${cur.hp}/${v.wall_types[cur.material].hp} HP` : "No wall on this edge yet."} Defence of this hex now: <b>${h.defence}</b>.</div><div class="opts">${opts}</div>`;
    p.querySelectorAll("[data-wall]").forEach((b) => b.onclick = () => act({ kind: "wall", hex: sel.hex, edge: sel.edge, what: b.dataset.wall }));
    return;
  }
  const slots = [];
  for (let k = 0; k < h.slots; k++) {
    const b = h.buildings[k], q = h.queued[k - h.buildings.length];
    if (b) slots.push(`<div class="slot full">${b !== "city_hall" ? `<span class="x" data-demolish="${b}" title="Demolish">×</span>` : ""}<b>${esc(b === "city_hall" ? "City hall" : v.buildings[b].name)}</b>${v.buildings[b] && Object.keys(v.buildings[b].makes).length ? `<div class="muted">${costText(v.buildings[b].makes)}/turn</div>` : ""}</div>`);
    else if (q) slots.push(`<div class="slot queued"><b>${esc(v.buildings[q].name)}</b><div class="muted">being built</div></div>`);
    else slots.push('<div class="slot"><span class="muted">Empty slot</span></div>');
  }
  const opts = Object.entries(v.buildings).filter(([k, b]) => !b.needs || b.needs === h.resource).map(([k, b]) => {
    const why = h.can_build[k];
    return `<button class="opt" data-build="${k}" ${why ? "disabled" : ""} data-tip="${esc(`<b>${b.name}</b><div>${b.info}</div><div>Strength +${b.strength}</div>`)}"><span>${esc(b.name)}${Object.keys(b.makes).length ? ` <span class="muted">· ${costText(b.makes)}/turn</span>` : ""}</span><span class="cost">${costText(b.cost)} · ${b.labour} labour</span>${why ? `<span class="why">${esc(why)}</span>` : ""}</button>`;
  }).join("");
  p.innerHTML = `<h2>${HEX_NAME[h.terrain]}${h.resource ? ` · ${G[h.resource] ? G[h.resource].icon : ""} ${pretty(h.resource)}` : ""}</h2>
    <div class="sub">${h.slots} slots · defence here <b>${h.defence}</b>${h.outer.length ? ` · ${h.outer.length} outer edges` : " · the heart of the city"}</div>
    <div class="slots">${slots.join("")}</div><div class="opts">${opts}</div>`;
  p.querySelectorAll("[data-build]").forEach((b) => b.onclick = () => act({ kind: "build", hex: sel.hex, what: b.dataset.build }));
  p.querySelectorAll("[data-demolish]").forEach((b) => b.onclick = () => act({ kind: "demolish", hex: sel.hex, what: b.dataset.demolish }));
}
function renderQueue() {
  const v = S.v;
  $("queue").innerHTML = `<h3>Construction · ${v.labour} labour a turn</h3>${v.queue.length ? v.queue.map((o, k) => {
    const tot = o.kind === "wall" ? v.wall_types[o.what].labour : v.buildings[o.what].labour;
    const name = o.kind === "wall" ? v.wall_types[o.what].name : v.buildings[o.what].name;
    return `<div class="qrow"><span style="width:110px">${esc(name)}</span><div class="pbar"><b style="width:${100 * (1 - o.labour_left / tot)}%"></b></div><button class="ghost" data-cancel="${k}" title="Cancel (materials back)">×</button></div>`;
  }).join("") : '<div class="muted">Nothing ordered. Click a hex or an edge.</div>'}`;
  $("queue").querySelectorAll("[data-cancel]").forEach((b) => b.onclick = () => act({ kind: "cancel", index: Number(b.dataset.cancel) }));
}
function describe(e) {
  const n = (k) => pretty(k).toLowerCase();
  return {
    harvest: () => Object.keys(e.goods).length ? `Harvest: ${Object.entries(e.goods).map(([g, c]) => `+${c} ${g}`).join(", ")}.` : "No harvest: nobody works the land.",
    built: () => `Finished: ${n(e.what)}${e.edge >= 0 ? " wall" : ""}.`,
    grew: () => `The city grew to ${e.pop} people.`,
    hunger: () => `Hunger: the city shrank to ${e.pop}.`,
    spoiled: () => `No room for ${Object.entries(e.goods).map(([g, c]) => `${c} ${g}`).join(", ")}: lost.`,
    raid_coming: () => `Scouts: raiders will hit the ${n(S.v.hexes[e.hex].terrain)} in ${e.turns} turn${e.turns === 1 ? "" : "s"}.`,
    raid: () => e.held ? `Raid ${e.strength} held off (defence ${e.defence}).` : `Raid ${e.strength} broke through (defence ${e.defence}).`,
    wall_fell: () => "A wall fell.",
  }[e.kind]?.() || "";
}
function renderLog() {
  const v = S.v, items = (v.log || []).map(describe).filter(Boolean);
  $("log").innerHTML = `<h3>Last turn</h3><ul>${items.map((t) => `<li>${esc(t)}</li>`).join("") || '<li class="muted">The first turn.</li>'}</ul>`;
}
function render() { renderBar(); renderPanel(); renderQueue(); renderLog(); }

async function refresh() { S.v = await api("/api/sandbox"); render(); }
async function act(cmd) {
  const r = await api("/api/sandbox/command", cmd);
  if (r.ok === false) toast(r.error);
  await refresh();
  return r;
}
$("end").onclick = async () => {
  $("end").disabled = true;
  const r = await act({ kind: "end_turn" });
  const raid = (r.events || []).find((e) => e.kind === "raid");
  if (raid) S.raid = { ...raid, start: performance.now() };
  setTimeout(() => { $("end").disabled = false; }, raid ? 2400 : 250);
};
document.addEventListener("keydown", (e) => { if (e.key === "Enter" && !$("end").disabled) $("end").click(); if (e.key === "Escape") { S.sel = null; renderPanel(); $("modal").classList.add("hidden"); } });
$("new-btn").onclick = async () => { await api("/api/sandbox/new", { seed: Math.floor(Math.random() * 9999) + 1 }); S.sel = null; await refresh(); };
$("exchange-btn").onclick = () => openExchange();
document.querySelector("#modal .close").onclick = () => $("modal").classList.add("hidden");
function openExchange() {
  const v = S.v;
  $("modal-body").innerHTML = `<h2>The Galactic Exchange</h2><div class="muted">Neutral alien traders. They always deal, never kindly: they buy low and sell high, and prices drift every turn. Selling a lot at once lowers what they pay.</div>
    <table class="ex"><tr><th>Good</th><th>Stored</th><th>They pay</th><th>They ask</th><th></th></tr>
    ${Object.keys(G).map((g) => `<tr><td>${G[g].icon} ${esc(v.goods_info[g].name)}</td><td>${v.goods[g]}/${v.caps[g]}</td><td>${v.quotes[g].sell} 🪙</td><td>${v.quotes[g].buy} 🪙</td>
      <td><button data-sell="${g}" data-n="10">Sell 10</button> <button data-sell="${g}" data-n="50">Sell 50</button> <button class="ghost" data-buy="${g}" data-n="10">Buy 10</button></td></tr>`).join("")}</table>
    <div style="margin-top:8px">Gold: <b>${v.gold}</b> 🪙</div>`;
  $("modal").classList.remove("hidden");
  $("modal-body").querySelectorAll("[data-sell]").forEach((b) => b.onclick = async () => { await act({ kind: "trade", good: b.dataset.sell, amount: Number(b.dataset.n), side: "sell" }); openExchange(); });
  $("modal-body").querySelectorAll("[data-buy]").forEach((b) => b.onclick = async () => { await act({ kind: "trade", good: b.dataset.buy, amount: Number(b.dataset.n), side: "buy" }); openExchange(); });
}
window.addEventListener("resize", layout);
layout(); refresh(); requestAnimationFrame(frame);
