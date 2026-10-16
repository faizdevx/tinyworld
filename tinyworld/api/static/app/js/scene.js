// The studio floor: tiles, walls with doorways, furniture that shows state,
// pixel characters that walk real paths, speech bubbles, and day and night.
// It only draws what the foreman says; it decides nothing.

const COLS = 40;
const ROWS = 24;

// Where things stand, in tiles. `slots` are the tiles agents use at a station.
// `ly` is the row the label sits on: clear of the furniture and the walls.
const STATIONS = {
  wall: { x: 5, y: 4, label: "Task wall", ly: 3.9 },
  web: { x: 20, y: 3, label: "The web", ly: 3.9 },
  library: { x: 34, y: 4, label: "Library", ly: 3.9 },
  drafting: { x: 6, y: 15, label: "Drafting table", ly: 11.6 },
  review: { x: 20, y: 15, label: "Review desk", ly: 11.6 },
  podium: { x: 33, y: 15, label: "Decision podium", ly: 11.6 },
  lounge: { x: 20, y: 21, label: "Lounge", ly: 20.7 },
};

// Walls: an outer ring, and two partitions with doorways between the rooms.
function buildGrid() {
  const g = Array.from({ length: ROWS }, () => Array(COLS).fill(0));
  for (let x = 0; x < COLS; x++) { g[0][x] = 1; g[ROWS - 1][x] = 1; }
  for (let y = 0; y < ROWS; y++) { g[y][0] = 1; g[y][COLS - 1] = 1; }
  for (let x = 1; x < COLS - 1; x++) {
    // The upper partition, with three doorways.
    if (![10, 11, 20, 21, 29, 30].includes(x)) g[9][x] = 1;
    // The lower partition, before the lounge.
    if (![6, 7, 19, 20, 21, 33, 34].includes(x)) g[19][x] = 1;
  }
  // Furniture blocks the tiles it stands on.
  const block = (x0, y0, w, h) => { for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) g[y][x] = 2; };
  block(2, 2, 7, 1);    // task wall board
  block(17, 2, 6, 1);   // web terminals
  block(31, 2, 7, 1);   // shelves
  block(3, 12, 6, 2);   // drafting table
  block(18, 12, 5, 2);  // review desk
  block(32, 12, 3, 2);  // podium
  block(16, 21, 9, 1);  // sofa
  return g;
}

const GRID = buildGrid();

function walkable(x, y) {
  return x >= 0 && y >= 0 && x < COLS && y < ROWS && GRID[y][x] === 0;
}

// A* on the tile grid, four directions.
export function findPath(from, to) {
  const key = (p) => p.y * COLS + p.x;
  if (!walkable(to.x, to.y)) return [from];
  const open = [{ ...from, g: 0, f: 0 }];
  const came = new Map();
  const cost = new Map([[key(from), 0]]);
  const seen = new Set();
  while (open.length) {
    open.sort((a, b) => a.f - b.f);
    const cur = open.shift();
    if (cur.x === to.x && cur.y === to.y) {
      const path = [{ x: cur.x, y: cur.y }];
      let k = key(cur);
      while (came.has(k)) { const p = came.get(k); path.unshift(p); k = key(p); }
      return path;
    }
    seen.add(key(cur));
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const n = { x: cur.x + dx, y: cur.y + dy };
      if (!walkable(n.x, n.y) || seen.has(key(n))) continue;
      const g = cost.get(key(cur)) + 1;
      if (g < (cost.get(key(n)) ?? Infinity)) {
        cost.set(key(n), g);
        came.set(key(n), { x: cur.x, y: cur.y });
        open.push({ ...n, g, f: g + Math.abs(n.x - to.x) + Math.abs(n.y - to.y) });
      }
    }
  }
  return [from];
}

// The free tiles around a station, so agents stand next to it, not on it.
function slotsFor(station) {
  // Tiles two apart in front of the furniture, nearest first, so nameplates do not collide.
  const st = STATIONS[station] || STATIONS.lounge;
  const out = [];
  const near = [];
  // Stay in the station's own room: the rows between its partitions.
  const [top, bottom] = st.y < 9 ? [1, 8] : st.y < 19 ? [10, 18] : [20, 22];
  for (let y = top; y <= bottom; y++) {
    for (let dx = -12; dx <= 12; dx += 3) {
      const x = st.x + dx;
      const dy = y - st.y;
      if (walkable(x, y)) near.push({ x, y, d: Math.abs(dx) + Math.abs(dy) * 1.5 });
    }
  }
  near.sort((a, b) => a.d - b.d);
  for (const p of near) {
    if (out.length >= 8) break;
    // Far enough apart that two nameplates never overlap.
    if (!out.some((q) => Math.abs(q.x - p.x) < 3 && Math.abs(q.y - p.y) < 2)) out.push({ x: p.x, y: p.y });
  }
  return out.length ? out : [{ x: 20, y: 20 }];
}
const SLOTS = Object.fromEntries(Object.keys(STATIONS).map((k) => [k, slotsFor(k)]));

// -- characters -----------------------------------------------------------

const SKIN = ["#f1c7a3", "#d9a37b", "#b97f56", "#8d5a3b", "#e8b48c", "#c58e66"];
const HAIR = ["#2b1d14", "#5a3a22", "#a8642a", "#d8b464", "#1f1f2b", "#7a2f2f", "#444444", "#b0b0b0"];

function hash(text) {
  let h = 2166136261;
  for (const c of text) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

// 8 by 12 pixels, two walking frames. Each agent gets a skin, a hair colour and style,
// and its own shirt colour: a silhouette you can tell apart across the room.
function makeSprite(agent) {
  const h = hash(agent.id);
  const skin = SKIN[h % SKIN.length];
  const hair = HAIR[(h >> 3) % HAIR.length];
  const longHair = (h >> 7) & 1;
  const frames = [];
  for (let f = 0; f < 2; f++) {
    const c = document.createElement("canvas");
    c.width = 8; c.height = 12;
    const g = c.getContext("2d");
    const px = (x, y, col) => { g.fillStyle = col; g.fillRect(x, y, 1, 1); };
    // hair and head
    for (let x = 2; x < 6; x++) px(x, 0, hair);
    for (let x = 1; x < 7; x++) px(x, 1, hair);
    for (let y = 2; y < 5; y++) for (let x = 2; x < 6; x++) px(x, y, skin);
    px(1, 2, hair); px(6, 2, hair);
    if (longHair) { px(1, 3, hair); px(6, 3, hair); px(1, 4, hair); px(6, 4, hair); }
    px(3, 3, "#1b1a17"); px(5, 3, "#1b1a17");
    // body in the agent's colour, arms in skin
    for (let y = 5; y < 9; y++) for (let x = 2; x < 6; x++) px(x, y, agent.color);
    px(1, 6, skin); px(6, 6, skin);
    px(1, 5, agent.color); px(6, 5, agent.color);
    // legs: the two frames swap them
    const legs = "#34322e";
    if (f === 0) { px(2, 9, legs); px(2, 10, legs); px(5, 9, legs); px(5, 10, legs); px(2, 11, "#1b1a17"); px(5, 11, "#1b1a17"); }
    else { px(3, 9, legs); px(3, 10, legs); px(4, 9, legs); px(4, 10, legs); px(3, 11, "#1b1a17"); px(4, 11, "#1b1a17"); }
    frames.push(c);
  }
  return frames;
}

// -- the scene ------------------------------------------------------------

export function createScene(canvas, getState) {
  const walkers = new Map(); // agent id -> {x, y, path, target, station, frame, facing}
  const sprites = new Map();
  let tile = 16;
  let ox = 0, oy = 0;

  function spriteOf(agent) {
    const key = agent.id + agent.color;
    if (!sprites.has(key)) sprites.set(key, makeSprite(agent));
    return sprites.get(key);
  }

  function walkerOf(agent, index) {
    let w = walkers.get(agent.id);
    if (!w) {
      const start = SLOTS.lounge[index % SLOTS.lounge.length];
      w = { x: start.x, y: start.y, path: [], station: null, frame: 0, facing: 1, slot: start };
      walkers.set(agent.id, w);
    }
    if (w.station !== agent.station) {
      // Pick the first free slot at the new station and walk there.
      const taken = new Set([...walkers.values()].filter((o) => o !== w && o.slot).map((o) => `${o.slot.x},${o.slot.y}`));
      const slots = SLOTS[agent.station] || SLOTS.lounge;
      const slot = slots.find((s) => !taken.has(`${s.x},${s.y}`)) || slots[0];
      const from = { x: Math.round(w.x), y: Math.round(w.y) };
      w.path = findPath(from, slot).slice(1);
      w.slot = slot;
      w.station = agent.station;
    }
    return w;
  }

  function step(w, dt) {
    if (!w.path.length) return false;
    const next = w.path[0];
    const dx = next.x - w.x, dy = next.y - w.y;
    const dist = Math.hypot(dx, dy);
    const speed = 5.5 * dt; // tiles per second
    if (dist <= speed) { w.x = next.x; w.y = next.y; w.path.shift(); }
    else { w.x += (dx / dist) * speed; w.y += (dy / dist) * speed; }
    if (Math.abs(dx) > 0.01) w.facing = dx > 0 ? 1 : -1;
    return true;
  }

  function nightness(date = new Date()) {
    const h = date.getHours() + date.getMinutes() / 60;
    if (h >= 7 && h <= 18) return 0;
    if (h > 18 && h < 21) return (h - 18) / 3;
    if (h > 4 && h < 7) return (7 - h) / 3;
    return 1;
  }

  function furniture(g, S, css) {
    const at = (x, y) => [ox + x * tile, oy + y * tile];
    const box = (x, y, w, h, fill, stroke) => {
      const [px, py] = at(x, y);
      g.fillStyle = fill; g.fillRect(px, py, w * tile, h * tile);
      if (stroke) { g.strokeStyle = stroke; g.strokeRect(px + 0.5, py + 0.5, w * tile - 1, h * tile - 1); }
    };
    // task wall: a board with one card per task, coloured by status
    box(2, 2, 7, 1, "#6b5a45", "#4a3d2f");
    const colour = { todo: "#d8d2c4", doing: "#e0b84a", review: "#7fb0d8", done: "#7cbf8a", blocked: "#d9776b", cancelled: "#999" };
    const tasks = [...S.tasks.values()];
    tasks.slice(0, 26).forEach((t, i) => {
      const [px, py] = at(2, 2);
      g.fillStyle = colour[t.status] || "#ccc";
      g.fillRect(px + 3 + (i % 13) * (tile * 7 - 6) / 13, py + 2 + Math.floor(i / 13) * (tile / 2 - 1), (tile * 7 - 6) / 13 - 2, tile / 2 - 3);
    });
    // web terminals with glowing screens
    for (let i = 0; i < 3; i++) {
      box(17 + i * 2, 2, 2, 1, "#2c2f36", "#1b1d22");
      const [px, py] = at(17 + i * 2, 2);
      g.fillStyle = "#4fb3c8"; g.fillRect(px + 4, py + 3, tile * 2 - 8, tile - 6);
    }
    // shelves with books
    box(31, 2, 7, 1, "#7a5c3e", "#5b432c");
    const books = ["#b8574a", "#4a7bb8", "#d8a64a", "#5e9a63", "#8a5bb0"];
    for (let i = 0; i < 21; i++) {
      const [px, py] = at(31, 2);
      g.fillStyle = books[i % books.length];
      g.fillRect(px + 3 + i * ((tile * 7 - 6) / 21), py + 3, (tile * 7 - 6) / 21 - 1, tile - 6);
    }
    // drafting table: one paper per section in the draft
    box(3, 12, 6, 2, "#b8956a", "#8a6c48");
    [...S.draft].slice(0, 11).forEach((s, i) => {
      const [px, py] = at(3, 12);
      g.fillStyle = "#f7f4ec";
      g.fillRect(px + 4 + (i % 6) * tile, py + 4 + Math.floor(i / 6) * tile, tile - 6, tile - 8);
    });
    // review desk with a lamp
    box(18, 12, 5, 2, "#8a6c48", "#6b5236");
    // podium: lit when something waits for the user
    const waiting = [...S.decisions.values()].some((d) => d.status === "open");
    box(32, 12, 3, 2, "#5b432c", "#3d2d1d");
    if (waiting) {
      const [px, py] = at(33, 12);
      const pulse = 0.55 + 0.45 * Math.sin(performance.now() / 260);
      g.fillStyle = `rgba(232, 184, 74, ${pulse})`;
      g.beginPath(); g.arc(px + tile / 2, py + tile / 2, tile * 0.55, 0, 7); g.fill();
      g.fillStyle = "#1b1a17"; g.font = `bold ${Math.round(tile * 0.8)}px system-ui`; g.textAlign = "center";
      g.fillText("!", px + tile / 2, py + tile * 0.8);
    }
    // lounge sofa and plants
    box(16, 21, 9, 1, "#8f6f9c", "#6f5079");
    for (const x of [14, 26]) { const [px, py] = at(x, 21); g.fillStyle = "#4f8a4f"; g.beginPath(); g.arc(px + tile / 2, py + tile / 2, tile * 0.45, 0, 7); g.fill(); }
    // labels
    g.font = `${Math.max(10, Math.round(tile * 0.7))}px system-ui, sans-serif`;
    g.textAlign = "center";
    g.fillStyle = css.muted;
    for (const st of Object.values(STATIONS)) {
      const [px, py] = at(st.x, st.y);
      g.fillText(st.label, px + tile / 2, oy + st.ly * tile);
    }
  }

  function bubble(g, x, y, text, colour) {
    g.font = `${Math.max(10, Math.round(tile * 0.65))}px system-ui, sans-serif`;
    const w = Math.min(g.measureText(text).width + 12, tile * 14);
    const h = tile * 1.1;
    g.fillStyle = colour || "rgba(255,255,255,0.95)";
    g.strokeStyle = "rgba(0,0,0,0.15)";
    g.beginPath(); g.roundRect(x - w / 2, y - h, w, h, 6); g.fill(); g.stroke();
    g.beginPath(); g.moveTo(x - 4, y); g.lineTo(x + 4, y); g.lineTo(x, y + 5); g.fill();
    g.fillStyle = "#1b1a17"; g.textAlign = "center";
    let t = text;
    while (g.measureText(t).width > w - 12 && t.length > 4) t = t.slice(0, -2);
    g.fillText(t === text ? t : t + "…", x, y - h / 2 + 4);
  }

  let last = performance.now();
  let frame = 0;

  function draw(now) {
    const S = getState();
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const ratio = window.devicePixelRatio || 1;
    const parent = canvas.parentElement;
    const W = parent.clientWidth, H = parent.clientHeight;
    if (canvas.width !== Math.round(W * ratio) || canvas.height !== Math.round(H * ratio)) {
      canvas.width = Math.round(W * ratio); canvas.height = Math.round(H * ratio);
    }
    const g = canvas.getContext("2d");
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.imageSmoothingEnabled = false;
    tile = Math.max(8, Math.floor(Math.min(W / COLS, H / ROWS)));
    ox = Math.floor((W - tile * COLS) / 2); oy = Math.floor((H - tile * ROWS) / 2);
    const style = getComputedStyle(document.documentElement);
    const css = { muted: style.getPropertyValue("--muted").trim() || "#888" };

    // floor and walls
    g.fillStyle = "#e9e2d3"; g.fillRect(0, 0, W, H);
    for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
      const px = ox + x * tile, py = oy + y * tile;
      if (GRID[y][x] === 1) { g.fillStyle = "#6d6459"; g.fillRect(px, py, tile, tile); }
      else { g.fillStyle = (x + y) % 2 ? "#ece6d8" : "#e4dccb"; g.fillRect(px, py, tile, tile); }
    }
    furniture(g, S, css);

    // characters, back to front
    const agents = [...S.agents.values()];
    const placed = agents.map((a, i) => [a, walkerOf(a, i)]).sort((p, q) => p[1].y - q[1].y);
    for (const [agent, w] of placed) {
      const moving = step(w, dt);
      if (moving) w.frame += dt * 8;
      const [f0, f1] = spriteOf(agent);
      const sprite = moving && Math.floor(w.frame) % 2 ? f1 : f0;
      const scale = tile / 8 * 1.5;
      const sw = 8 * scale, sh = 12 * scale;
      const cx = ox + w.x * tile + tile / 2;
      const by = oy + w.y * tile + tile;
      const bob = moving ? 0 : Math.sin(now / 500 + hash(agent.id)) * 0.6;
      g.globalAlpha = agent.active ? 1 : 0.35;
      g.fillStyle = "rgba(0,0,0,0.18)";
      g.beginPath(); g.ellipse(cx, by - 1, sw * 0.4, sw * 0.15, 0, 0, 7); g.fill();
      g.save();
      g.translate(cx, by - sh + bob);
      if (w.facing < 0) { g.scale(-1, 1); }
      g.drawImage(sprite, -sw / 2, 0, sw, sh);
      g.restore();
      // a ring for whoever is selected or needs the user
      if (S.picked === agent.id || agent.state === "waiting_user" || agent.state === "error") {
        g.strokeStyle = agent.state === "error" ? "#b5382c" : agent.state === "waiting_user" ? "#e0b84a" : "#1b1a17";
        g.lineWidth = 2; g.beginPath(); g.ellipse(cx, by - 1, sw * 0.55, sw * 0.22, 0, 0, 7); g.stroke(); g.lineWidth = 1;
      }
      // nameplate
      g.font = `bold ${Math.max(10, Math.round(tile * 0.7))}px system-ui, sans-serif`;
      g.textAlign = "center";
      g.fillStyle = "#1b1a17";
      g.fillText(agent.name + (agent.paused ? " (paused)" : ""), cx, by - sh - 4 + bob);
      // what it is doing: a bubble while busy, from the latest thing it said or did
      const busy = !["idle", "done"].includes(agent.state) && !moving;
      if (busy && agent.activity) {
        bubble(g, cx, by - sh - tile * 1.2 + bob, agent.activity,
          agent.state === "waiting_user" ? "rgba(250, 232, 180, 0.97)" : undefined);
      }
      g.globalAlpha = 1;
    }

    // day and night, from the viewer's own clock; lamps glow at night
    const night = nightness();
    if (night > 0) {
      g.fillStyle = `rgba(20, 28, 58, ${0.42 * night})`;
      g.fillRect(0, 0, W, H);
      for (const st of Object.values(STATIONS)) {
        const px = ox + st.x * tile + tile / 2, py = oy + st.y * tile + tile / 2;
        const glow = g.createRadialGradient(px, py, 0, px, py, tile * 4);
        glow.addColorStop(0, `rgba(255, 214, 140, ${0.35 * night})`);
        glow.addColorStop(1, "rgba(255, 214, 140, 0)");
        g.fillStyle = glow; g.fillRect(px - tile * 4, py - tile * 4, tile * 8, tile * 8);
      }
    }
    frame = requestAnimationFrame(draw);
  }

  function agentAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left, y = clientY - rect.top;
    let hit = null;
    for (const [id, w] of walkers) {
      const cx = ox + w.x * tile + tile / 2, cy = oy + w.y * tile;
      if (Math.abs(x - cx) < tile && y > cy - tile * 1.5 && y < cy + tile * 1.2) hit = id;
    }
    return hit;
  }

  frame = requestAnimationFrame(draw);
  return { agentAt, stop: () => cancelAnimationFrame(frame), nightness };
}
