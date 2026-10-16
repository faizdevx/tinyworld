// The studio: a team of agents building a world, drawn from the foreman's state.
// This view holds no logic. It draws snapshot + upserts and sends back intents.
import { api, listen } from "./api.js";
import { action, el, fill, setCrumbs, tag, toast } from "./ui.js";

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
const SECTIONS = [
  "premise", "divergence", "geography", "politics", "economy", "technology",
  "culture", "factions", "figures", "tensions", "digest",
];
const money = (n) => `$${(n || 0).toFixed(n && n < 0.1 ? 3 : 2)}`;

export async function showStudio(view, worldId) {
  setCrumbs([["Studio", null]]);
  const S = {
    goal: null, agents: new Map(), tasks: new Map(), decisions: new Map(),
    memory: [], feed: [], draft: new Set(), pos: new Map(), audit: [],
    diff: [], picked: null, town: null, mergeOn: null,
  };
  let current = "now";
  let notified = new Set();

  const canvas = el("canvas", { class: "studio-canvas", "aria-label": "The studio" });
  const scene = el("div", { class: "studio-scene" }, canvas);
  const goalLine = el("div", { class: "goal-line" });
  const consoleOut = el("div", { class: "console-out" });
  const hints = el("div", { class: "console-hints" });
  const consoleIn = el("input", {
    type: "text", class: "console-in", autocomplete: "off",
    placeholder: "A goal, @name to message, or / for commands",
    "aria-label": "Command console",
  });
  const decisionBox = el("div", { class: "decision-box" });
  const cardBox = el("div", { class: "card-box" });
  const tabs = el("div", { class: "tabs" });
  const body = el("div", { class: "tab-body" });

  view.append(
    el("div", { class: "studio" },
      el("div", { class: "studio-left" }, goalLine, scene,
        el("div", { class: "console" }, consoleOut, hints, consoleIn)),
      el("div", { class: "studio-right" }, decisionBox, cardBox, tabs, body)),
  );

  // -- the console -----------------------------------------------------

  async function send(text) {
    try {
      const reply = await api(`/studio/${worldId}/console`, { method: "POST", body: { text } });
      fill(consoleOut, ...reply.lines.map((l) => el("div", {}, l)));
    } catch (error) { toast(error.message); }
  }
  consoleIn.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && consoleIn.value.trim()) {
      const text = consoleIn.value.trim();
      consoleIn.value = ""; fill(hints); send(text);
    } else if (event.key === "Tab") {
      const m = consoleIn.value.match(/@(\w*)$/);
      if (m) {
        const found = [...S.agents.values()].find((a) => a.name.toLowerCase().startsWith(m[1].toLowerCase()));
        if (found) { event.preventDefault(); consoleIn.value = consoleIn.value.replace(/@\w*$/, `@${found.name.toLowerCase()} `); }
      }
    }
  });
  consoleIn.addEventListener("input", () => {
    const m = consoleIn.value.match(/@(\w*)$/);
    fill(hints, ...(m ? [...S.agents.values()].filter((a) => a.name.toLowerCase().startsWith(m[1].toLowerCase()))
      .map((a) => el("span", { class: "hint" }, `@${a.name.toLowerCase()}`)) : []));
  });
  const onKey = (event) => {
    if (event.key === "`" && document.activeElement !== consoleIn) { event.preventDefault(); consoleIn.focus(); }
  };
  document.addEventListener("keydown", onKey);

  // -- state -----------------------------------------------------------

  function apply(msg) {
    switch (msg.type) {
      case "snapshot":
        S.goal = msg.goal;
        S.agents = new Map(msg.agents.map((a) => [a.id, a]));
        S.tasks = new Map(msg.tasks.map((t) => [t.id, t]));
        S.decisions = new Map(msg.decisions.map((d) => [d.id, d]));
        S.memory = msg.memory; S.feed = msg.feed;
        S.draft = new Set(msg.draft_sections || []);
        break;
      case "goal.upsert": S.goal = msg.goal; break;
      case "agent.upsert": S.agents.set(msg.agent.id, msg.agent); break;
      case "task.upsert": S.tasks.set(msg.task.id, msg.task); break;
      case "decision.upsert": S.decisions.set(msg.decision.id, msg.decision); break;
      case "memory.upsert":
        S.memory = S.memory.filter((m) => m.id !== msg.entry.id).concat(msg.entry); break;
      case "memory.remove": S.memory = S.memory.filter((m) => m.id !== msg.id); break;
      case "feed.add": S.feed = S.feed.concat(msg.item).slice(-200); break;
      case "audit.add": S.audit = S.audit.concat(msg.entry).slice(-200); break;
      case "draft.upsert": S.draft.add(msg.section); break;
      default: return;
    }
    notify();
    render();
  }

  // A badge in the tab title and, if allowed, a desktop notification.
  function notify() {
    const open = [...S.decisions.values()].filter((d) => d.status === "open");
    document.title = open.length ? `(${open.length}) TinyWorld` : "TinyWorld";
    for (const d of open) {
      if (notified.has(d.id)) continue;
      notified.add(d.id);
      if ("Notification" in window && Notification.permission === "granted") {
        try { new Notification("TinyWorld needs you", { body: d.question }); } catch { /* ignore */ }
      }
    }
  }

  // -- the scene -------------------------------------------------------

  function place(agent) {
    const st = STATIONS[agent.station] || STATIONS.lounge;
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
    g.textAlign = "center";
    const anyOpen = [...S.decisions.values()].some((d) => d.status === "open");
    for (const [key, st] of Object.entries(STATIONS)) {
      const x = st.x * w, y = st.y * h;
      g.fillStyle = soft; g.strokeStyle = line;
      g.beginPath(); g.roundRect(x - 52, y - 26, 104, 52, 12); g.fill(); g.stroke();
      g.fillStyle = muted; g.font = "12px system-ui, sans-serif"; g.fillText(st.label, x, y - 34);
      if (key === "podium" && anyOpen) {
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
      g.globalAlpha = agent.active ? 1 : 0.35;
      g.fillStyle = agent.color;
      g.beginPath(); g.arc(x, y, busy ? 15 : 12, 0, 7); g.fill();
      const ring = agent.state === "waiting_user" ? "#c9a227" : agent.state === "error" ? "#b5382c"
        : agent.paused ? "#8b857a" : S.picked === agent.id ? ink : null;
      if (ring) { g.strokeStyle = ring; g.lineWidth = 3; g.stroke(); g.lineWidth = 1; }
      g.fillStyle = "#fff"; g.font = "bold 12px system-ui"; g.fillText(agent.name[0], x, y + 4);
      g.fillStyle = ink; g.font = "12px system-ui"; g.fillText(agent.name, x, y - 22);
      if (agent.activity && busy) { g.fillStyle = muted; g.font = "11px system-ui"; g.fillText(agent.activity.slice(0, 34), x, y + 30); }
      g.globalAlpha = 1;
    }
  }

  canvas.addEventListener("click", (event) => {
    const rect = canvas.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width, py = (event.clientY - rect.top) / rect.height;
    let hit = null;
    for (const agent of S.agents.values()) {
      const p = S.pos.get(agent.id);
      if (p && Math.hypot((p.x - px) * rect.width, (p.y - py) * rect.height) < 20) hit = agent.id;
    }
    S.picked = hit;
    render();
  });

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
    const tone = { merged: "good", rejected: "bad", failed: "bad", review: "warn", paused: "warn" }[goal.status] || "";
    const cap = goal.budget != null ? ` of ${money(goal.budget)}` : "";
    fill(goalLine,
      el("div", { class: "goal-text" }, goal.text),
      el("div", { class: "row" },
        tag(goal.status, tone),
        el("div", { class: "bar" }, el("div", { class: "bar-fill", style: `width:${Math.round((goal.progress || 0) * 100)}%` })),
        el("span", { class: "muted small" }, `${Math.round((goal.progress || 0) * 100)}%`),
        el("span", { class: "muted small", title: "Spent on this goal" }, `${money(goal.spent)}${cap}`),
        "Notification" in window && Notification.permission === "default"
          ? el("button", { type: "button", class: "ghost small", onclick: async () => { await Notification.requestPermission(); render(); } }, "Notify me") : null,
        goal.status === "merged"
          ? action("Seed the world", async () => {
            const seeded = await api(`/worlds/${worldId}/seed`, { method: "POST", body: { name: "main" } });
            location.hash = `#/branch/${seeded.branch_id}`;
          }, { class: "primary" }) : null));
  }

  async function loadDiff() {
    try { S.diff = (await api(`/studio/${worldId}/draft`)).diff; } catch { S.diff = []; }
    render();
  }

  function mergeCard(d) {
    if (!S.diff.length) loadDiff();
    // Which sections to merge now. Read at the moment of the click, since the card is redrawn as things change.
    const picks = () => S.mergeOn || new Set(S.diff.filter((x) => x.status !== "unchanged").map((x) => x.section));
    const note = el("input", { type: "text", placeholder: "What to change (sent with anything you hold back)", "aria-label": "Your words" });
    const boxes = S.diff.map((x) => {
      const box = el("input", { type: "checkbox", checked: picks().has(x.section), disabled: x.status === "unchanged",
        onchange: () => { const next = new Set(picks()); box.checked ? next.add(x.section) : next.delete(x.section); S.mergeOn = next; } });
      return el("label", { class: `diff-row ${x.status}` }, box, el("span", {}, x.summary));
    });
    const held = () => S.diff.filter((x) => x.status !== "unchanged" && !picks().has(x.section)).map((x) => x.section);
    const submit = async (all) => {
      const send_back = {};
      if (!all) for (const s of held()) send_back[s] = note.value || "please revise";
      try {
        await api(`/studio/${worldId}/merge`, { method: "POST", body: { merge: all ? null : [...picks()], send_back } });
      } catch (error) { toast(error.message); }
    };
    const flagged = d.options.includes("Merge anyway");
    return [
      // The per-section lines are in the list below; keep only the summary and any warning.
      el("div", { class: "muted small pre" }, d.context.split("\n").filter((l) => !/: (new|changed|no change)/.test(l)).join("\n")),
      el("div", { class: "diff" }, ...boxes),
      el("div", { class: "row" },
        flagged ? el("button", { type: "button", onclick: () => submit(true) }, "Merge anyway") : el("button", { type: "button", class: "primary", onclick: () => submit(true) }, "Merge all"),
        el("button", { type: "button", onclick: () => submit(false) }, "Merge selected, send the rest back"),
        ...d.options.filter((o) => !["Merge", "Merge anyway"].includes(o)).map((o) => el("button", { type: "button", onclick: () => answer(d, o, note.value) }, o))),
      el("div", { class: "row" }, note),
    ];
  }

  async function answer(d, option, text) {
    try { await api(`/studio/${worldId}/decisions/${d.id}/answer`, { method: "POST", body: { option, text: text || "" } }); }
    catch (error) { toast(error.message); }
  }

  function renderDecisions() {
    const open = [...S.decisions.values()].filter((d) => d.status === "open");
    fill(decisionBox, ...open.map((d) => {
      const agent = S.agents.get(d.agent_id);
      const who = `${agent ? agent.name : d.agent_id} ${d.kind === "merge" ? "asks you to merge" : d.kind === "permission" ? "needs permission" : "asks"}`;
      if (d.kind === "merge") {
        return el("div", { class: "decision merge" }, el("div", { class: "who" }, who), el("div", { class: "q" }, d.question), ...mergeCard(d));
      }
      const note = el("input", { type: "text", placeholder: "Or say it in words", "aria-label": "Your words" });
      return el("div", { class: `decision ${d.kind}` },
        el("div", { class: "who" }, who),
        el("div", { class: "q" }, d.question),
        d.context && d.kind === "permission" ? el("div", { class: "muted small" }, d.context) : d.context ? el("div", { class: "muted small" }, d.context) : null,
        el("div", { class: "row" },
          ...d.options.map((o) => el("button", { type: "button", onclick: () => answer(d, o, note.value) }, o)),
          d.options.length ? null : el("button", { type: "button", onclick: () => answer(d, "", note.value) }, "Send")),
        el("div", { class: "row" }, note));
    }));
  }

  function renderCard() {
    const a = S.picked ? S.agents.get(S.picked) : null;
    if (!a) { fill(cardBox); return; }
    const task = a.task_id ? S.tasks.get(a.task_id) : null;
    const recent = S.feed.filter((f) => f.agent_id === a.id).slice(-6).reverse();
    const msg = el("input", { type: "text", placeholder: `Message ${a.name}`, "aria-label": `Message ${a.name}` });
    const act = (what) => api(`/studio/${worldId}/agents/${a.id}/${what}`, { method: "POST" }).catch((e) => toast(e.message));
    fill(cardBox, el("div", { class: "agent-card" },
      el("div", { class: "row" }, el("span", { class: "dot", style: `background:${a.color}` }), el("strong", {}, a.name),
        el("span", { class: "muted small" }, a.title), el("span", { class: "grow" }),
        el("button", { type: "button", class: "ghost small", onclick: () => { S.picked = null; render(); } }, "Close")),
      el("div", { class: "muted small" }, `${a.state}${a.paused ? " (paused)" : ""}${a.active ? "" : " (off shift)"}${a.activity ? ": " + a.activity : ""}`),
      task ? el("div", { class: "small" }, `Task: ${task.title}`) : null,
      el("div", { class: "muted small" }, `${a.steps} steps on this task · ${a.calls} calls · ${money(a.cost)}`),
      el("ul", { class: "plain small" }, ...recent.map((f) => el("li", {}, f.text))),
      el("div", { class: "row" },
        a.paused ? el("button", { type: "button", onclick: () => act("resume") }, "Resume") : el("button", { type: "button", onclick: () => act("pause") }, "Pause"),
        a.active ? el("button", { type: "button", onclick: () => act("stop") }, "Stop") : el("button", { type: "button", onclick: () => act("spawn") }, "Bring back")),
      el("div", { class: "row" }, msg, el("button", { type: "button", onclick: async () => {
        if (!msg.value.trim()) return;
        try { await api(`/studio/${worldId}/message`, { method: "POST", body: { to: a.id, text: msg.value } }); msg.value = ""; toast(`Sent to ${a.name}`); }
        catch (e) { toast(e.message); }
      } }, "Send"))));
  }

  function renderTabs() {
    const names = [["now", "Now"], ["team", "Team"], ["tasks", "Tasks"], ["draft", "Draft"], ["notes", "Notes"], ["town", "Town"], ["log", "Log"]];
    fill(tabs, ...names.map(([key, label]) =>
      el("button", { type: "button", class: key === current ? "tab on" : "tab", onclick: () => {
        current = key;
        if (key === "town") api(`/studio/${worldId}/town`).then((t) => { S.town = t; render(); }).catch(() => {});
        if (key === "log") api(`/studio/${worldId}/audit`).then((a) => { S.audit = a; render(); }).catch(() => {});
        if (key === "draft") loadDiff();
        render();
      } }, label)));
  }

  function renderBody() {
    if (current === "now") {
      const items = S.feed.slice(-60).reverse();
      fill(body, el("ul", { class: "plain feed" }, ...items.map((f) => {
        const a = f.agent_id ? S.agents.get(f.agent_id) : null;
        return el("li", { class: `feed-${f.kind}` },
          a ? el("span", { class: "dot", style: `background:${a.color}` }) : null,
          el("span", {}, (a ? a.name + " " : "") + f.text));
      })));
    } else if (current === "team") {
      fill(body, ...[...S.agents.values()].map((a) =>
        el("div", { class: "team-row", onclick: () => { S.picked = a.id; render(); } },
          el("span", { class: "dot", style: `background:${a.color}` }),
          el("strong", {}, a.name), el("span", { class: "muted small" }, ` ${a.title}`),
          el("div", { class: "muted small" }, `${a.state}${a.paused ? " (paused)" : ""}${a.active ? "" : " (off shift)"} · ${money(a.cost)} · ${a.calls} calls`))));
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
            return el("li", {}, el("span", {}, t.title),
              a ? el("span", { class: "muted small" }, ` · ${a.name}`) : null,
              t.attempts ? el("span", { class: "muted small" }, ` · attempt ${t.attempts + 1}`) : null,
              t.blocked_reason ? el("div", { class: "muted small" }, t.blocked_reason) : null);
          })));
      }));
    } else if (current === "draft") {
      const byName = new Map(S.diff.map((d) => [d.section, d]));
      fill(body, el("p", { class: "muted small" }, "Nothing here is the world until you merge it."),
        el("ul", { class: "plain" }, ...SECTIONS.map((s) => {
          const d = byName.get(s);
          return el("li", {}, el("span", { class: S.draft.has(s) ? "ok" : "muted" }, S.draft.has(s) ? "✓ " : "· "), d ? d.summary : s);
        })));
    } else if (current === "notes") {
      const title = el("input", { type: "text", placeholder: "Note title", "aria-label": "Note title" });
      const text = el("input", { type: "text", placeholder: "A note for the whole team", "aria-label": "Note" });
      fill(body,
        el("div", { class: "row" }, title, text, el("button", { type: "button", onclick: async () => {
          try { await api(`/studio/${worldId}/memory`, { method: "PUT", body: { title: title.value, body: text.value } }); title.value = text.value = ""; }
          catch (e) { toast(e.message); }
        } }, "Add")),
        ...(S.memory.length ? S.memory.slice().reverse().map((m) =>
          el("div", { class: "note" },
            el("div", { class: "row" }, el("strong", {}, m.title), el("span", { class: "grow" }),
              el("button", { type: "button", class: "ghost small", onclick: () => api(`/studio/${worldId}/memory/${m.id}`, { method: "DELETE" }).catch((e) => toast(e.message)) }, "Delete")),
            el("div", { class: "muted small" }, m.author), el("div", {}, m.body.slice(0, 400)))) : [el("p", { class: "muted" }, "No notes yet.")]));
    } else if (current === "town") {
      const t = S.town;
      fill(body, !t || !t.branch_id
        ? el("p", { class: "muted" }, "The town appears here once the world is merged and seeded.")
        : el("ul", { class: "plain" }, ...t.people.map((p) =>
          el("li", {}, el("strong", {}, p.name), el("span", { class: "muted small" }, ` ${p.occupation} · ${p.place}`),
            p.doing ? el("div", { class: "muted small" }, p.doing) : null))));
    } else {
      fill(body, el("ul", { class: "plain feed" }, ...S.audit.slice().reverse().slice(0, 100).map((a) =>
        el("li", {}, el("span", { class: "muted small" }, `${a.actor} · ${a.action}`), el("span", {}, ` ${a.detail}`)))));
    }
  }

  function render() {
    renderGoal();
    renderDecisions();
    renderCard();
    renderTabs();
    renderBody();
  }

  const close = listen(`/ws/studio/${worldId}`, apply);
  loop();
  render();
  return () => { cancelAnimationFrame(frame); close(); document.removeEventListener("keydown", onKey); document.title = "TinyWorld"; };
}
