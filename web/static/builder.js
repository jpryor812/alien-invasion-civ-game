// The city builder (docs/SPEC_M16.md): a close, tilted view of one city's land. No hex lines - only
// the border of the land it holds. Buildings stand anywhere on a fine grid (with a gap between
// them); walls are laid cell by cell. A blue ghost follows the cursor; click to place.
"use strict";

(function () {
  const TILT = 0.6;
  const cvs = document.getElementById("bcanvas"), g = cvs.getContext("2d");
  const B = { open: false, city: null, d: null, K: 60, camx: 0, camy: 0, tool: null, hover: null, drag: null, sel: null, pan: null };
  const MAT = { timber: "🪵", stone: "🪨", iron: "⚙️" };
  const WALL_COL = { wood: ["#8a5a2b", "#5a3a1a"], stone: ["#aaa59c", "#6a655e"], steel: ["#5d6b78", "#2f373f"], chitin: ["#6f8a3a", "#3c4d1c"], plasma: ["#5ad0ff", "#1f6a8a"] };
  const TINT = { grassland: "rgba(110,200,70,0.28)", plains: "rgba(220,200,90,0.28)", desert: "rgba(230,200,130,0.35)", tundra: "rgba(170,180,160,0.25)", snow: "rgba(240,245,255,0.5)" };
  const pr = (s) => String(s).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const ec = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const costTxt = (m) => Object.entries(m || {}).map(([k, n]) => `${MAT[k] || k}${n}`).join(" ");

  // -- images ---------------------------------------------------------------------------------
  const IMG = {};
  const load = (key, src, fallback) => { const im = new Image(); im.onload = () => { IMG[key] = im; }; im.onerror = () => { if (fallback) load(key, fallback); }; im.src = src; };
  for (const [k, src] of Object.entries({ grass: "terrain/grass.jpg", rock: "terrain/rock.jpg", sand: "terrain/sand.jpg", tundra: "terrain/tundra.jpg", snow: "terrain/snow.jpg",
    forest0: "features/forest_0.png", forest1: "features/forest_1.png", forest2: "features/forest_2.png" })) load(k, src);
  // Building art: builder/<id>.webp (Meshy and Blender renders), else the sandbox's closest model.
  const STAND_IN = { city_hall: "city_hall", food_depot: "granary", workshop: "workshop", market: "warehouse", library: "house", school: "house",
    military_base: "watchtower", radio_tower: "watchtower", storehouse: "warehouse", factory: "workshop", port: "warehouse", shipyard: "warehouse" };
  function sprite(id) {
    const key = `b:${id}`;
    if (!(key in IMG) && !B[`asked:${id}`]) { B[`asked:${id}`] = true; load(key, `builder/${id}.webp`, `settlement/${STAND_IN[id] || "house"}.webp`); }
    return IMG[key];
  }
  for (const t of ["farm", "lumber_camp", "quarry", "iron_mine"]) load(`imp:${t}`, `settlement/${t}.webp`);

  // -- geometry -------------------------------------------------------------------------------
  const cellW = () => Math.sqrt(3) / B.d.cells_per_hex;
  const toScreen = (wx, wy) => [cvs.clientWidth / 2 + (wx - B.camx) * B.K, cvs.clientHeight / 2 + (wy - B.camy) * B.K * TILT];
  const toWorld = (sx, sy) => [(sx - cvs.clientWidth / 2) / B.K + B.camx, (sy - cvs.clientHeight / 2) / (B.K * TILT) + B.camy];
  const cellAt = (sx, sy) => { const [wx, wy] = toWorld(sx, sy), c = cellW(); return [Math.round(wx / c), Math.round(wy / c)]; };
  const key = (x, y) => `${x},${y}`;
  function hexCorner(cx, cy, k, r = 1) { const a = (60 * k - 30) * Math.PI / 180; return toScreen(cx + r * Math.cos(a), cy + r * Math.sin(a)); }
  function hexPath(cx, cy, r = 1) { g.beginPath(); for (let k = 0; k < 6; k++) { const [x, y] = hexCorner(cx, cy, k, r); k ? g.lineTo(x, y) : g.moveTo(x, y); } g.closePath(); }

  // what the client checks before sending (the server checks again)
  function sets() {
    const d = B.d, land = new Set(d.cells.map(([x, y]) => key(x, y)));
    const walls = new Set([...d.walls, ...d.wall_orders].map((w) => key(w[0], w[1])));
    return { land, walls };
  }
  function footprint(x, y, n) { const out = []; for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) out.push([x + i, y + j]); return out; }
  function placeOk(what, x, y, n, skip) {
    const { land, walls } = sets(), gap = B.d.gap, cells = footprint(x, y, n);
    if (!cells.every(([a, b]) => land.has(key(a, b)))) return "outside the city's land";
    for (const e of B.d.layout) {
      if (e.id === skip) continue;
      const ex0 = e.x - gap, ey0 = e.y - gap, ex1 = e.x + e.size - 1 + gap, ey1 = e.y + e.size - 1 + gap;
      if (cells.some(([a, b]) => a >= ex0 && a <= ex1 && b >= ey0 && b <= ey1)) return "too close to a building (keep a gap)";
    }
    if (cells.some(([a, b]) => walls.has(key(a, b)))) return "a wall is there";
    return null;
  }
  function wallOk(x, y) {
    const { land } = sets();
    if (!land.has(key(x, y))) return false;
    return !B.d.layout.some((e) => x >= e.x && x < e.x + e.size && y >= e.y && y < e.y + e.size);
  }

  // -- drawing --------------------------------------------------------------------------------
  function ground() {
    const d = B.d;
    for (const t of d.tiles) {
      const cx = t.x / 1000, cy = t.y / 1000;
      hexPath(cx, cy, 1.03);
      g.save(); g.clip();
      const tex = t.elevation === "hills" ? IMG.rock : t.terrain === "desert" ? IMG.sand : t.terrain === "tundra" ? IMG.tundra : t.terrain === "snow" ? IMG.snow : IMG.grass;
      const [x0, y0] = toScreen(cx - 1.1, cy - 1.1), [x1, y1] = toScreen(cx + 1.1, cy + 1.1);
      g.fillStyle = tex ? g.createPattern(tex, "repeat") : "#5d9a3a"; g.fillRect(x0, y0, x1 - x0, y1 - y0);
      g.fillStyle = TINT[t.terrain] || "transparent"; g.fillRect(x0, y0, x1 - x0, y1 - y0);
      if (t.elevation === "hills") { g.fillStyle = "rgba(150,120,80,0.25)"; g.fillRect(x0, y0, x1 - x0, y1 - y0); }
      g.restore();
    }
    // the border: outer edges of the land, a warm glowing line (no inner hex lines)
    const centres = d.tiles.map((t) => [t.x / 1000, t.y / 1000]);
    const has = (x, y) => centres.some(([a, b]) => Math.abs(a - x) < 0.2 && Math.abs(b - y) < 0.2);
    g.lineCap = "round"; g.lineJoin = "round";
    for (const pass of [[10, "rgba(255,220,120,0.18)"], [4, "#f2d38a"]]) {
      g.lineWidth = pass[0]; g.strokeStyle = pass[1];
      for (const [cx, cy] of centres) {
        for (let k = 0; k < 6; k++) {
          const a = (60 * k) * Math.PI / 180, nx = cx + Math.sqrt(3) * Math.cos(a), ny = cy + Math.sqrt(3) * Math.sin(a);
          if (has(nx, ny)) continue;
          const [p1, q1] = hexCorner(cx, cy, k), [p2, q2] = hexCorner(cx, cy, (k + 1) % 6);
          g.beginPath(); g.moveTo(p1, q1); g.lineTo(p2, q2); g.stroke();
        }
      }
    }
  }
  function decor(items) {
    const d = B.d, used = new Set();
    for (const e of d.layout) for (const [a, b] of footprint(e.x, e.y, e.size)) used.add(key(a, b));
    for (const w of [...d.walls, ...d.wall_orders]) used.add(key(w[0], w[1]));
    const c = cellW();
    for (const t of d.tiles) {
      const cx = t.x / 1000, cy = t.y / 1000;
      if (t.feature === "forest" || t.feature === "jungle") {
        const trees = [IMG.forest0, IMG.forest1, IMG.forest2].filter(Boolean);
        for (let k = 0; k < 9; k++) {
          const a = k * 2.399 + t.tile, r = 0.25 + (k % 3) * 0.24, wx = cx + Math.cos(a) * r, wy = cy + Math.sin(a) * r * 0.9;
          if (used.has(key(Math.round(wx / c), Math.round(wy / c))) || !trees.length) continue;
          const im = trees[k % trees.length], [sx, sy] = toScreen(wx, wy), w = B.K * 0.45;
          items.push({ y: sy, draw: () => g.drawImage(im, sx - w / 2, sy - w * 0.85, w, w * im.height / im.width) });
        }
      }
      const imp = { farm: "farm", lumber_camp: "lumber_camp", mine: "iron_mine" }[t.improvement];
      if (imp && IMG[`imp:${imp}`] && !used.has(key(Math.round(cx / c), Math.round(cy / c)))) {
        const im = IMG[`imp:${imp}`], [sx, sy] = toScreen(cx, cy + 0.2), w = B.K * 1.3;
        items.push({ y: sy, draw: () => { g.globalAlpha = 0.95; g.drawImage(im, sx - w / 2, sy - w * 0.654, w, w); g.globalAlpha = 1; } });
      }
    }
  }
  function drawBuilding(what, x, y, n, alpha, tint) {
    const c = cellW(), wx = (x + (n - 1) / 2) * c, wy = (y + (n - 1) / 2) * c, [sx, sy] = toScreen(wx, wy);
    const fw = n * c * B.K;
    g.fillStyle = "rgba(0,0,0,0.28)"; g.beginPath(); g.ellipse(sx + fw * 0.06, sy + fw * 0.08 * TILT, fw * 0.55, fw * 0.4 * TILT, 0, 0, 7); g.fill();
    const im = sprite(what);
    g.globalAlpha = alpha;
    if (im) { const w = fw * 2.0; g.drawImage(im, sx - w / 2, sy - w * 0.654, w, w * im.height / im.width); }
    else { g.fillStyle = "#c9b28a"; g.fillRect(sx - fw * 0.4, sy - fw * 0.7, fw * 0.8, fw * 0.7); }
    g.globalAlpha = 1;
    if (tint) { g.fillStyle = tint; footprintPath(x, y, n); g.fill(); }
  }
  function footprintPath(x, y, n) {
    const c = cellW(), [ax, ay] = toScreen((x - 0.5) * c, (y - 0.5) * c), [bx, by] = toScreen((x + n - 0.5) * c, (y + n - 0.5) * c);
    g.beginPath(); g.rect(ax, ay, bx - ax, by - ay);
  }
  function drawWall(x, y, m, ghost) {
    const c = cellW(), [ax, ay] = toScreen((x - 0.5) * c, (y - 0.5) * c), [bx, by] = toScreen((x + 0.5) * c, (y + 0.5) * c);
    const h = c * B.K * (m === "wood" ? 0.9 : 0.75), [fill, edge] = WALL_COL[m] || WALL_COL.wood;
    g.globalAlpha = ghost ? 0.55 : 1;
    g.fillStyle = edge; g.fillRect(ax, by - h, bx - ax, h);  // front face
    g.fillStyle = fill; g.fillRect(ax, ay - h, bx - ax, by - ay);  // top
    g.strokeStyle = "rgba(0,0,0,0.35)"; g.lineWidth = 1; g.strokeRect(ax, ay - h, bx - ax, by - ay + h);
    if (m === "wood") { g.fillStyle = "#3a2410"; for (let k = 1; k < 3; k++) g.fillRect(ax + (bx - ax) * k / 3, by - h, 1, h); }
    if (m === "plasma") { g.fillStyle = "rgba(170,240,255,0.6)"; g.fillRect(ax, ay - h, bx - ax, 2); }
    g.globalAlpha = 1;
  }
  function frame() {
    if (!B.open) return;
    const W = cvs.clientWidth, H = cvs.clientHeight;
    if (cvs.width !== W * devicePixelRatio) { cvs.width = W * devicePixelRatio; cvs.height = H * devicePixelRatio; }
    g.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    const bg = g.createRadialGradient(W / 2, H / 2, 50, W / 2, H / 2, Math.max(W, H)); bg.addColorStop(0, "#2f4a24"); bg.addColorStop(1, "#0f1a0c");
    g.fillStyle = bg; g.fillRect(0, 0, W, H);
    if (!B.d) { requestAnimationFrame(frame); return; }
    ground();
    const d = B.d, tool = B.tool;
    if (tool) {  // the grid shows while building
      g.strokeStyle = "rgba(255,255,255,0.07)"; g.lineWidth = 1; const c = cellW();
      for (const [x, y] of d.cells) { const [ax, ay] = toScreen((x - 0.5) * c, (y - 0.5) * c), [bx, by] = toScreen((x + 0.5) * c, (y + 0.5) * c); g.strokeRect(ax, ay, bx - ax, by - ay); }
    }
    const items = [];
    decor(items);
    for (const [x, y, m] of d.walls) { const [, sy] = toScreen(0, (y + 0.5) * cellW()); items.push({ y: sy, draw: () => drawWall(x, y, m, false) }); }
    for (const [x, y, m] of d.wall_orders) { const [, sy] = toScreen(0, (y + 0.5) * cellW()); items.push({ y: sy, draw: () => drawWall(x, y, m, true) }); }
    for (const e of d.layout) {
      if (tool && tool.kind === "move" && tool.entry === e.id) continue;
      const [, sy] = toScreen(0, (e.y + e.size - 0.5) * cellW());
      items.push({ y: sy, draw: () => drawBuilding(e.what, e.x, e.y, e.size, e.done ? 1 : 0.6, B.sel === e.id ? "rgba(255,230,120,0.18)" : e.done ? null : "rgba(110,180,255,0.18)") });
    }
    items.sort((a, b) => a.y - b.y).forEach((it) => it.draw());
    // the ghost under the cursor
    if (tool && B.hover) {
      const [hx, hy] = B.hover;
      if (tool.kind === "place" || tool.kind === "move") {
        const n = tool.size, x = hx - Math.floor(n / 2), y = hy - Math.floor(n / 2);
        const why = placeOk(tool.what, x, y, n, tool.entry);
        footprintPath(x, y, n); g.fillStyle = why ? "rgba(230,70,60,0.35)" : "rgba(80,170,255,0.35)"; g.fill();
        g.strokeStyle = why ? "#ff6b5a" : "#7fc4ff"; g.lineWidth = 2; g.stroke();
        drawBuilding(tool.what, x, y, n, 0.75, null);
        B.ghost = { x, y, why };
      } else if (tool.kind === "wall") {
        const cells = B.drag ? B.drag : [[hx, hy]];
        for (const [x, y] of cells) drawWall(x, y, tool.material, true);
        for (const [x, y] of cells) { if (!wallOk(x, y)) { const c = cellW(), [ax, ay] = toScreen((x - 0.5) * c, (y - 0.5) * c), [bx, by] = toScreen((x + 0.5) * c, (y + 0.5) * c); g.fillStyle = "rgba(230,70,60,0.5)"; g.fillRect(ax, ay, bx - ax, by - ay); } }
      }
    }
    requestAnimationFrame(frame);
  }

  // -- the panel ------------------------------------------------------------------------------
  function panel() {
    const d = B.d, p = document.getElementById("bpanel");
    const stores = Object.keys(d.stores).map((k) => `<span class="store">${MAT[k]} ${d.stores[k]}<span class="muted">/${d.caps[k]} +${d.income[k]}</span></span>`).join(" ");
    const sel = B.sel != null ? d.layout.find((e) => e.id === B.sel) : null;
    const tab = B.tab || "build";
    const list = tab === "build"
      ? Object.entries(d.catalog).filter(([, b]) => !b.why || !/needs tech/.test(b.why)).map(([id, b]) => {
        const short = Object.entries(b.materials).filter(([k, n]) => d.stores[k] < n);
        const why = b.placed ? "placed, waiting to be built" : b.why;
        return `<button class="bopt" data-place="${id}" ${why ? "disabled" : ""} title="${ec(b.note || "")}"><b>${ec(b.name)}</b><span class="muted"> ${b.size}x${b.size}</span>
          <span class="cost">${costTxt(b.materials)} · ${b.production} work${short.length ? ` <span class="bad">(short of ${short.map(([k, n]) => `${n - d.stores[k]} ${k}`).join(", ")}: it will wait)</span>` : ""}</span>${why ? `<span class="why">${ec(why)}</span>` : ""}</button>`;
      }).join("")
      : Object.entries(d.wall_types).map(([id, w]) => `<button class="bopt${B.tool && B.tool.material === id ? " on" : ""}" data-wall="${id}" ${w.why ? "disabled" : ""}><b>${ec(w.name)}</b><span class="cost">${costTxt(w.cost)} · ${w.production} work · each piece +${w.strength / 10} strength, +${w.hp} HP</span>${w.why ? `<span class="why">${ec(w.why)}</span>` : ""}</button>`).join("");
    const walls = Object.entries(d.wall_totals).map(([m, t]) => `${t.pieces} ${m}`).join(", ");
    p.innerHTML = `<div class="title">${ec(d.city.name)}</div>
      <div class="row">${stores}</div>
      <div class="row muted">Strength ${d.strength} · HP ${d.city.hp}/${d.city.max_hp}${walls ? ` · walls: ${walls}` : ""}${d.wall_orders.length ? ` · <span class="good">${d.wall_orders.length} pieces being built</span>` : ""}</div>
      ${sel ? `<div class="bsel"><b>${ec(pr(sel.what))}</b> ${sel.done ? "" : '<span class="muted">(being built)</span>'} ${sel.what !== "city_hall" ? '<button id="bmove">Move</button>' : ""}</div>` : ""}
      <div class="row btabs"><button class="${tab === "build" ? "primary" : ""}" data-tab="build">Buildings</button><button class="${tab === "walls" ? "primary" : ""}" data-tab="walls">Walls</button></div>
      <div class="blist">${list}</div>`;
    p.querySelectorAll("[data-tab]").forEach((b) => b.onclick = () => { B.tab = b.dataset.tab; B.tool = null; panel(); hint(); });
    p.querySelectorAll("[data-place]").forEach((b) => b.onclick = () => { B.tool = { kind: "place", what: b.dataset.place, size: d.catalog[b.dataset.place].size }; B.sel = null; hint(); });
    p.querySelectorAll("[data-wall]").forEach((b) => b.onclick = () => { B.tool = { kind: "wall", material: b.dataset.wall }; hint(); panel(); });
    if (document.getElementById("bmove")) document.getElementById("bmove").onclick = () => { B.tool = { kind: "move", entry: sel.id, what: sel.what, size: sel.size }; hint(); };
  }
  function hint() {
    const t = B.tool, bar = document.getElementById("bbar");
    bar.innerHTML = !t ? "Choose a building or a wall to build. Click a building to select it. Drag to pan, wheel to zoom."
      : t.kind === "wall" ? `Drag across the land to lay ${ec(B.d.wall_types[t.material].name.toLowerCase())} pieces. Esc to stop.`
      : `Move the ${ec(pr(t.what))} and click to ${t.kind === "move" ? "set it down" : "place it"}. Blue fits, red does not. Esc to cancel.`;
  }

  // -- input ----------------------------------------------------------------------------------
  async function send(cmd) {
    const r = await api("/api/command", cmd);
    if (r.ok === false) toast(r.error);
    await reload();
    return r;
  }
  async function reload() { B.d = await api(`/api/builder/${B.city}`); panel(); }
  const pos = (e) => { const r = cvs.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  function line(a, b) {  // the cells between two cells (so a fast drag leaves no holes)
    const out = [], n = Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]), 1);
    for (let k = 0; k <= n; k++) out.push([Math.round(a[0] + (b[0] - a[0]) * k / n), Math.round(a[1] + (b[1] - a[1]) * k / n)]);
    return out;
  }
  cvs.addEventListener("mousemove", (e) => {
    const [sx, sy] = pos(e);
    if (B.pan) { B.camx = B.pan.cx - (sx - B.pan.x) / B.K; B.camy = B.pan.cy - (sy - B.pan.y) / (B.K * TILT); return; }
    B.hover = cellAt(sx, sy);
    if (B.drag) {
      const last = B.drag[B.drag.length - 1];
      for (const c of line(last, B.hover)) if (!B.drag.some(([x, y]) => x === c[0] && y === c[1])) B.drag.push(c);
    }
  });
  cvs.addEventListener("mousedown", (e) => {
    const [sx, sy] = pos(e);
    if (B.tool && B.tool.kind === "wall" && e.button === 0) { B.drag = [cellAt(sx, sy)]; return; }
    if (!B.tool) B.pan = { x: sx, y: sy, cx: B.camx, cy: B.camy, moved: false };
  });
  window.addEventListener("mouseup", async (e) => {
    if (!B.open) return;
    if (B.pan) {
      const [sx, sy] = pos(e), moved = Math.hypot(sx - B.pan.x, sy - B.pan.y) > 4; B.pan = null;
      if (!moved) {  // a click: select the building under the cursor
        const [cx, cy] = cellAt(sx, sy);
        const hit = B.d.layout.find((b) => cx >= b.x && cx < b.x + b.size && cy >= b.y && cy < b.y + b.size);
        B.sel = hit ? hit.id : null; panel();
      }
      return;
    }
    if (B.drag) {
      const cells = B.drag.filter(([x, y]) => wallOk(x, y)); B.drag = null;
      if (cells.length) await send({ kind: "place_walls", city: B.city, cells, material: B.tool.material });
    }
  });
  cvs.addEventListener("click", async () => {
    const t = B.tool;
    if (!t || t.kind === "wall" || !B.ghost) return;
    if (B.ghost.why) { toast(B.ghost.why); return; }
    if (t.kind === "place") await send({ kind: "place_building", city: B.city, building: t.what, x: B.ghost.x, y: B.ghost.y });
    else await send({ kind: "move_building", city: B.city, entry: t.entry, x: B.ghost.x, y: B.ghost.y });
    B.tool = null; hint();
  });
  cvs.addEventListener("wheel", (e) => { e.preventDefault(); B.K = Math.max(25, Math.min(220, B.K * (e.deltaY < 0 ? 1.12 : 1 / 1.12))); }, { passive: false });
  document.addEventListener("keydown", (e) => {
    if (!B.open) return;
    if (e.key === "Escape") { e.stopPropagation(); if (B.tool) { B.tool = null; B.drag = null; hint(); panel(); } else close(); }
  }, true);

  async function open(cityId) {
    B.city = cityId; B.tool = null; B.sel = null; B.tab = "build";
    document.getElementById("builder").classList.remove("hidden");
    B.open = true;
    await reload();
    const xs = B.d.tiles.map((t) => t.x / 1000), ys = B.d.tiles.map((t) => t.y / 1000);
    B.camx = (Math.min(...xs) + Math.max(...xs)) / 2; B.camy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const w = cvs.clientWidth - 380, h = cvs.clientHeight - 80;
    B.camx = 0; B.camy = 0.15;  // start on the city centre, about three hexes across
    B.K = Math.max(40, Math.min(w / 5.6, h / (4.2 * TILT)));
    B.camx += 160 / B.K;  // leave room for the panel on the right
    hint(); requestAnimationFrame(frame);
  }
  async function close() {
    B.open = false; B.tool = null;
    document.getElementById("builder").classList.add("hidden");
    if (typeof refresh === "function") await refresh(true);
  }
  document.getElementById("bclose").onclick = close;
  window.Builder = { open, close, state: B, draw: () => { const was = B.open; B.open = true; frame(); B.open = was; } };
})();
