// The world map: places as nodes of a graph, people as markers on them.
// Drawn on a plain canvas; the model never draws anything, it only emits state.

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function initials(name) {
  return name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase();
}

// Places are a graph, not a survey: positions only need to be readable. They
// start from the seeded coordinates (or beside a neighbour, for places created
// later) and are then relaxed so that nothing overlaps. The result is cached
// per set of places and links, so the map holds still while the world runs.
const layoutCache = new Map();

function relax(ids, start, links) {
  const nodes = ids.map((id, index) => {
    const p = start.get(id);
    // A tiny fixed offset per node breaks ties between coincident places.
    return { id, x: p.x + Math.cos(index * 2.4) * 0.01, y: p.y + Math.sin(index * 2.4) * 0.01 };
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 1e-6);
  for (const n of nodes) { n.x /= span; n.y /= span; }
  const ideal = 1 / Math.sqrt(Math.max(nodes.length, 2));
  for (let step = 0; step < 300; step += 1) {
    const heat = 0.08 * (1 - step / 300);
    const push = new Map(nodes.map((n) => [n.id, { x: 0, y: 0 }]));
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distance = Math.max(Math.hypot(dx, dy), 1e-4);
        const force = (ideal * ideal) / distance;
        push.get(a.id).x += (dx / distance) * force;
        push.get(a.id).y += (dy / distance) * force;
        push.get(b.id).x -= (dx / distance) * force;
        push.get(b.id).y -= (dy / distance) * force;
      }
    }
    for (const [a, b] of links) {
      const from = byId.get(a);
      const to = byId.get(b);
      const dx = from.x - to.x;
      const dy = from.y - to.y;
      const distance = Math.max(Math.hypot(dx, dy), 1e-4);
      const force = (distance * distance) / ideal;
      push.get(a).x -= (dx / distance) * force;
      push.get(a).y -= (dy / distance) * force;
      push.get(b).x += (dx / distance) * force;
      push.get(b).y += (dy / distance) * force;
    }
    for (const n of nodes) {
      const move = push.get(n.id);
      const size = Math.max(Math.hypot(move.x, move.y), 1e-6);
      n.x += (move.x / size) * Math.min(size, heat);
      n.y += (move.y / size) * Math.min(size, heat);
    }
  }
  return new Map(nodes.map((n) => [n.id, { x: n.x, y: n.y }]));
}

function layout(state) {
  const places = Object.values(state.entities).filter((e) => e.kind === "place");
  const ids = places.map((p) => p.id).sort();
  const links = Object.keys(state.edges)
    .map((key) => key.split("|"))
    .filter(([a, b]) => ids.includes(a) && ids.includes(b));
  const cacheKey = ids.join(",") + "#" + links.map((l) => l.join("|")).sort().join(",");
  if (layoutCache.has(cacheKey)) return { places, position: layoutCache.get(cacheKey) };

  const start = new Map();
  for (const place of places) {
    const { x, y } = place.attrs;
    if (typeof x === "number" && typeof y === "number") start.set(place.id, { x, y });
  }
  const neighbours = new Map(ids.map((id) => [id, []]));
  for (const [a, b] of links) {
    neighbours.get(a).push(b);
    neighbours.get(b).push(a);
  }
  let pending = ids.filter((id) => !start.has(id));
  for (let pass = 0; pass < 4 && pending.length; pass += 1) {
    pending.forEach((id, index) => {
      const anchor = neighbours.get(id).find((n) => start.has(n));
      if (!anchor && pass < 3) return;
      const base = anchor ? start.get(anchor) : { x: 0, y: 0 };
      start.set(id, { x: base.x + Math.cos(index * 2.4 + pass), y: base.y + Math.sin(index * 2.4 + pass) });
    });
    pending = pending.filter((id) => !start.has(id));
  }
  const position = relax(ids, start, links);
  if (layoutCache.size > 20) layoutCache.clear();
  layoutCache.set(cacheKey, position);
  return { places, position };
}

export function createMap(canvas, { onSelect }) {
  let state = null;
  let selected = null;
  let hits = [];

  function draw() {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    hits = [];
    if (!state) return;

    const { places, position } = layout(state);
    if (!places.length) return;
    const points = [...position.values()];
    const minX = Math.min(...points.map((p) => p.x));
    const maxX = Math.max(...points.map((p) => p.x));
    const minY = Math.min(...points.map((p) => p.y));
    const maxY = Math.max(...points.map((p) => p.y));
    // Each axis is fitted on its own so the graph fills whatever shape the panel has.
    const padX = 70;
    const padTop = 34;
    const padBottom = 52;
    const scaleX = (width - padX * 2) / Math.max(maxX - minX, 1e-6);
    const scaleY = (height - padTop - padBottom) / Math.max(maxY - minY, 1e-6);
    const at = (id) => {
      const p = position.get(id);
      return { x: padX + (p.x - minX) * scaleX, y: padTop + (p.y - minY) * scaleY };
    };

    const ink = cssVar("--ink");
    const muted = cssVar("--muted");
    const accent = cssVar("--accent");

    ctx.lineWidth = 1.5;
    for (const [key, edge] of Object.entries(state.edges)) {
      const [a, b] = key.split("|");
      if (!position.has(a) || !position.has(b)) continue;
      const from = at(a);
      const to = at(b);
      ctx.strokeStyle = cssVar("--map-edge");
      ctx.setLineDash(edge.visible ? [] : [4, 4]);
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    const people = Object.values(state.entities).filter((e) => e.kind === "person");
    ctx.textAlign = "center";
    for (const place of places) {
      const { x, y } = at(place.id);
      const here = people.filter((p) => p.location === place.id);
      // A crowded place grows so its people stay distinguishable.
      const radius = 20 + Math.max(0, here.length - 3) * 4;
      ctx.fillStyle = cssVar("--map-place");
      ctx.strokeStyle = selected === place.id ? accent : cssVar("--map-edge");
      ctx.lineWidth = selected === place.id ? 2.5 : 1.5;
      ctx.beginPath();
      if (place.attrs.enclosed) ctx.rect(x - radius, y - radius, radius * 2, radius * 2);
      else ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      hits.push({ id: place.id, x, y, r: radius });

      ctx.fillStyle = ink;
      ctx.font = "12px system-ui, sans-serif";
      ctx.textBaseline = "top";
      ctx.fillText(place.name, x, y + radius + 5);

      here.forEach((person, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(here.length, 1) - Math.PI / 2;
        const ring = here.length === 1 ? 0 : Math.max(12, radius - 8);
        const px = x + Math.cos(angle) * ring;
        const py = y + Math.sin(angle) * ring;
        const r = 9;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fillStyle = !person.alive ? muted : selected === person.id ? accent : ink;
        ctx.globalAlpha = person.alive ? 1 : 0.45;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillStyle = cssVar("--panel");
        ctx.font = "600 9px system-ui, sans-serif";
        ctx.textBaseline = "middle";
        ctx.fillText(initials(person.name), px, py + 0.5);
        // People are listed after their place so a click on one wins.
        hits.push({ id: person.id, x: px, y: py, r: r + 2 });
      });
    }
  }

  canvas.addEventListener("click", (event) => {
    const box = canvas.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    const hit = [...hits].reverse().find((h) => Math.hypot(h.x - x, h.y - y) <= h.r);
    if (hit) onSelect(hit.id);
  });

  const observer = new ResizeObserver(draw);
  observer.observe(canvas);
  const scheme = window.matchMedia("(prefers-color-scheme: dark)");
  scheme.addEventListener("change", draw);

  return {
    update(nextState) {
      state = nextState;
      draw();
    },
    select(id) {
      selected = id;
      draw();
    },
    destroy() {
      observer.disconnect();
      scheme.removeEventListener("change", draw);
    },
  };
}
