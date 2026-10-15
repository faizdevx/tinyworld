// The studio: a team of agents building a world, drawn from the foreman's state.
// This view holds no logic. It draws snapshot + upserts and sends back intents.
import { api, listen } from "./api.js";
import { action, clear, el, fill, setCrumbs, tag, toast } from "./ui.js";

// Where each station sits in the scene, as a fraction of the canvas.
const STATIONS = {
  wall: { x: 0.14, y: 0.2, label: "Task wall" },
  web: { x: 0.5, y: 0.14, label: "The web" },
  library: { x: 0.86, y: 0.2, label: "Library" },
  drafting: { x: 0.2, y: 0.62, label: "Drafting table" },
  review: { x: 0.52, y: 0.66, label: "Review desk" },
  podium: { x: 0.82, y: 0.62, label: "Decision podium" },
  lounge: { x: 0.5, y: 0.9, label: "Lounge" },
};
const STATE_WORD = {
  idle: "idle", thinking: "thinking", researching: "searching", reading: "reading",
  writing: "writing", reviewing: "reviewing", waiting_user: "needs you",
  blocked: "blocked", done: "done", error: "stuck",
};
const SECTIONS = [
  "premise", "divergence", "geography", "politics", "economy", "technology",
  "culture", "factions", "figures", "tensions", "digest",
];

export async function showStudio(view, worldId) {
  setCrumbs([["Studio", null]]);
  const S = {
    goal: null, agents: new Map(), tasks: new Map(), decisions: new Map(),
    memory: [], feed: [], draft: new Set(), pos: new Map(),
  };

  const canvas = el("canvas", { class: "studio-canvas", "aria-label": "The studio" });
  const scene = el("div", { class: "studio-scene" }, canvas);
  const goalLine = el("div", { class: "goal-line" });
  const decisionBox = el("div", { class: "decision-box" });
  const tabs = el("div", { class: "tabs" });
  const body = el("div", { class: "tab-body" });
  let current = "now";

  view.append(
    el("div", { class: "studio" },
      el("div", { class: "studio-left" }, goalLine, scene),
      el("div", { class: "studio-right" }, decisionBox, tabs, body)),
  );

  // -- state -----------------------------------------------------------

  function apply(msg) {
    switch (msg.type) {
      case "snapshot":
        S.goal = msg.goal;
        S.agents = new Map(msg.agents.map((a) => [a.id, a]));
        S.tasks = new Map(msg.tasks.map((t) => [t.id, t]));
        S.decisions = new Map(msg.decisions.map((d) => [d.id, d]));
        S.memory = msg.memory;
        S.feed = msg.feed;
        S.draft = new Set(msg.draft_sections || []);
        break;
      case "goal.upsert": S.goal = msg.goal; break;
      case "agent.upsert": S.agents.set(msg.agent.id, msg.agent); break;
      case "task.upsert": S.tasks.set(msg.task.id, msg.task); break;
      case "decision.upsert": S.decisions.set(msg.decision.id, msg.decision); break;
      case "memory.upsert":
        S.memory = S.memory.filter((m) => m.id !== msg.entry.id).concat(msg.entry);
        break;
      case "feed.add": S.feed = S.feed.concat(msg.item).slice(-200); break;
      case "draft.upsert": S.draft.add(msg.section); break;
      default: return;
    }
    render();
  }

  // -- the scene -------------------------------------------------------

  function place(agent) {
    const st = STATIONS[agent.station] || STATIONS.lounge;
    // Spread agents that share a station so nobody is hidden.
    const mates = [...S.agents.values()].filter((a) => a.station === agent.station);
    const index = mates.findIndex((a) => a.id === agent.id);
    return { x: st.x + (index - (mates.length - 1) / 2) * 0.055, y: st.y + (index % 2) * 0.03 };
  }

  function draw() {
    const ratio = window.devicePixelRatio || 1;
    const w = scene.clientWidth, h = scene.clientHeight;
    if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
      canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio);
    }
    const g = canvas.getContext("2d");
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    const css = getComputedStyle(document.documentElement);
    const ink = css.getPropertyValue("--ink").trim() || "#222";
    const muted = css.getPropertyValue("--muted").trim() || "#888";
    const soft = css.getPropertyValue("--soft").trim() || "#eee";
    const line = css.getPropertyValue("--line").trim() || "#ddd";
    g.clearRect(0, 0, w, h);
    g.font = "12px system-ui, sans-serif";
    g.textAlign = "center";
    for (const [key, st] of Object.entries(STATIONS)) {
      const x = st.x * w, y = st.y * h;
      g.fillStyle = soft; g.strokeStyle = line;
      g.beginPath(); g.roundRect(x - 52, y - 26, 104, 52, 12); g.fill(); g.stroke();
      g.fillStyle = muted; g.fillText(st.label, x, y - 34);
      if (key === "podium" && [...S.decisions.values()].some((d) => d.status === "open")) {
        g.fillStyle = "#c9a227"; g.beginPath(); g.arc(x + 44, y - 20, 7, 0, 7); g.fill();
        g.fillStyle = "#fff"; g.fillText("!", x + 44, y - 16);
      }
    }
    for (const agent of S.agents.values()) {
      const target = place(agent);
      const cur = S.pos.get(agent.id) || { x: 0.5, y: 0.9 };
      cur.x += (target.x - cur.x) * 0.12; cur.y += (target.y - cur.y) * 0.12;
      S.pos.set(agent.id, cur);
      const x = cur.x * w, y = cur.y * h;
      const busy = agent.state !== "idle" && agent.state !== "done";
      g.fillStyle = agent.color;
      g.beginPath(); g.arc(x, y, busy ? 15 : 12, 0, 7); g.fill();
      if (agent.state === "waiting_user") { g.strokeStyle = "#c9a227"; g.lineWidth = 3; g.stroke(); g.lineWidth = 1; }
      if (agent.state === "error") { g.strokeStyle = "#b5382c"; g.lineWidth = 3; g.stroke(); g.lineWidth = 1; }
      g.fillStyle = "#fff"; g.font = "bold 12px system-ui"; g.fillText(agent.name[0], x, y + 4);
      g.fillStyle = ink; g.font = "12px system-ui";
      g.fillText(agent.name, x, y - 22);
      if (agent.activity && busy) {
        g.fillStyle = muted; g.font = "11px system-ui";
        g.fillText(agent.activity.slice(0, 34), x, y + 30);
      }
    }
  }

  let frame = 0;
  function loop() {
    if (!canvas.isConnected) return;
    draw();
    frame = requestAnimationFrame(loop);
  }

  // -- panels ----------------------------------------------------------

  function renderGoal() {
    const goal = S.goal;
    if (!goal) { fill(goalLine, el("span", { class: "muted" }, "Waiting for a goal")); return; }
    const tone = { merged: "good", rejected: "bad", failed: "bad", review: "warn" }[goal.status] || "";
    fill(goalLine,
      el("div", { class: "goal-text" }, goal.text),
      el("div", { class: "row" },
        tag(goal.status, tone),
        el("div", { class: "bar" }, el("div", { class: "bar-fill", style: `width:${Math.round((goal.progress || 0) * 100)}%` })),
        el("span", { class: "muted small" }, `${Math.round((goal.progress || 0) * 100)}%`),
        goal.status === "merged"
          ? action("Seed the world", async () => {
            const seeded = await api(`/worlds/${worldId}/seed`, { method: "POST", body: { name: "main" } });
            location.hash = `#/branch/${seeded.branch_id}`;
          }, { class: "primary" }) : null));
  }

  function renderDecisions() {
    const open = [...S.decisions.values()].filter((d) => d.status === "open");
    fill(decisionBox, ...open.map((d) => {
      const agent = S.agents.get(d.agent_id);
      const note = el("input", { type: "text", placeholder: d.kind === "merge" ? "What to change (for Request changes)" : "Or say it in words", "aria-label": "Your words" });
      const answerWith = async (option) => {
        try {
          await api(`/studio/${worldId}/decisions/${d.id}/answer`, { method: "POST", body: { option, text: note.value } });
        } catch (error) { toast(error.message); }
      };
      return el("div", { class: `decision ${d.kind}` },
        el("div", { class: "who" }, `${agent ? agent.name : d.agent_id} ${d.kind === "merge" ? "asks you to merge" : "asks"}`),
        el("div", { class: "q" }, d.question),
        d.context ? el("div", { class: "muted small" }, d.context) : null,
        el("div", { class: "row" },
          ...d.options.map((o) => el("button", { type: "button", class: o === "Merge" ? "primary" : "", onclick: () => answerWith(o) }, o)),
          d.options.length ? null : el("button", { type: "button", onclick: () => answerWith("") }, "Send")),
        el("div", { class: "row" }, note));
    }));
  }

  function renderTabs() {
    const names = [["now", "Now"], ["tasks", "Tasks"], ["draft", "Draft"], ["notes", "Notes"]];
    fill(tabs, ...names.map(([key, label]) =>
      el("button", { type: "button", class: key === current ? "tab on" : "tab", onclick: () => { current = key; render(); } }, label)));
  }

  function renderBody() {
    if (current === "now") {
      const items = S.feed.slice(-60).reverse().filter((f) => f.kind !== "tool" || true);
      fill(body, el("ul", { class: "plain feed" }, ...items.map((f) => {
        const a = f.agent_id ? S.agents.get(f.agent_id) : null;
        return el("li", { class: `feed-${f.kind}` },
          a ? el("span", { class: "dot", style: `background:${a.color}` }) : null,
          el("span", {}, (a ? a.name + " " : "") + f.text));
      })));
    } else if (current === "tasks") {
      const groups = ["doing", "todo", "review", "blocked", "done"];
      const tasks = [...S.tasks.values()];
      fill(body, ...groups.map((status) => {
        const list = tasks.filter((t) => t.status === status);
        if (!list.length) return null;
        return el("div", { class: "group" },
          el("h3", {}, `${status} (${list.length})`),
          el("ul", { class: "plain" }, ...list.map((t) => {
            const a = t.assignee ? S.agents.get(t.assignee) : null;
            return el("li", {},
              el("span", {}, t.title),
              a ? el("span", { class: "muted small" }, ` · ${a.name}`) : null,
              t.blocked_reason ? el("div", { class: "muted small" }, t.blocked_reason) : null);
          })));
      }));
    } else if (current === "draft") {
      fill(body, el("p", { class: "muted small" }, "Nothing here is the world until you merge it."),
        el("ul", { class: "plain" }, ...SECTIONS.map((s) =>
          el("li", {}, el("span", { class: S.draft.has(s) ? "ok" : "muted" }, S.draft.has(s) ? "✓ " : "· "), s))));
    } else {
      fill(body, ...(S.memory.length ? S.memory.slice().reverse().map((m) =>
        el("div", { class: "note" }, el("strong", {}, m.title), el("div", { class: "muted small" }, m.author),
          el("div", {}, m.body.slice(0, 400)))) : [el("p", { class: "muted" }, "No notes yet.")]));
    }
  }

  function render() {
    renderGoal();
    renderDecisions();
    renderTabs();
    renderBody();
  }

  const close = listen(`/ws/studio/${worldId}`, apply);
  loop();
  render();
  return () => { cancelAnimationFrame(frame); close(); };
}
