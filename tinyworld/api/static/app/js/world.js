import { api, listen } from "./api.js";
import { createMap } from "./map.js";
import { action, clear, fill, el, money, setCrumbs, shortId, toast, when } from "./ui.js";

const FEED_LIMIT = 400;
// Ordinary routine lines. They are in the log; the feed hides them by default.
const QUIET = /( sleeps| rests| waits| works at .+)\.$/;

function daypart(hour) {
  if (hour < 5 || hour >= 22) return "night";
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}

function initials(name) {
  return name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase();
}

const LEVELS = { 3: "worked out", 2: "taught", 1: "aware" };

// person.attrs.knowledge is {idea: level}; labels live in state.rules.knowledge.
function ideas(value, graph) {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value)
    .map(([id, level]) => ({
      label: (graph && graph[id] && graph[id].label) || shortId(id),
      level: Number(level) || 1,
    }))
    .sort((a, b) => b.level - a.level || a.label.localeCompare(b.label));
}

export async function showWorld(view, branchId) {
  const branch = await api(`/branches/${branchId}`);
  const world = await api(`/worlds/${branch.world_id}`);
  setCrumbs([[world.premise.split("\n")[0].slice(0, 48), `#/world/${world.id}`], [branch.name, null]]);

  let status = branch.status;
  let state = await api(`/branches/${branchId}/state`);
  let selectedPerson = null;
  let lastSeq = 0;
  let lastDay = null;
  let stateTimer = null;
  let tab = "now";
  const nameOf = (id) => (state.entities[id] ? state.entities[id].name : id === "god" ? "God" : shortId(id));

  // -- top bar ------------------------------------------------------------
  const date = el("span", { class: "date" });
  const part = el("span", { class: "part" });
  const speed = el("select", { "aria-label": "Speed" },
    el("option", { value: "2" }, "slow"),
    el("option", { value: "0.8", selected: true }, "normal"),
    el("option", { value: "0.1" }, "fast"));
  const playButton = action("▶", async () => {
    await api(`/branches/${branchId}/run`, {
      method: "POST", body: { action: status.running ? "pause" : "play", delay: Number(speed.value) },
    });
  }, { class: "primary icon", title: "Play / pause" });
  speed.addEventListener("change", async () => {
    if (!status.running) return;
    await api(`/branches/${branchId}/run`, { method: "POST", body: { action: "play", delay: Number(speed.value) } });
  });
  const skipSpan = el("input", { class: "short", value: "1mo", "aria-label": "Skip ahead", title: "3d, 2w, 6mo, 20y" });
  const cost = el("span", { class: "cost" });
  const meter = el("div", { class: "meter", title: "Budget used" }, el("i", {}));
  const busy = el("span", { class: "small muted" });
  const capInput = el("input", { class: "short", type: "number", min: "0", step: "0.5", placeholder: "$ cap", "aria-label": "Budget cap" });

  capInput.addEventListener("change", () =>
    api(`/branches/${branchId}/budget`, { method: "POST", body: { run_cap: Number(capInput.value) || 0 } })
      .then(() => toast("Cap set")).catch((e) => toast(e.message)));

  const topbar = el("div", { class: "topbar" },
    el("div", { class: "when" }, date, part),
    playButton,
    action("Step", () => api(`/branches/${branchId}/run`, { method: "POST", body: { action: "step" } }), { class: "ghost", title: "One step" }),
    speed,
    skipSpan,
    action("Skip", async () => {
      const result = await api(`/branches/${branchId}/skip`, { method: "POST", body: { span: skipSpan.value } });
      toast(result.complete ? `Skipped ${skipSpan.value}.` : `Stopped early: ${result.stopped}`);
      await loadFeed(true);
    }, { class: "ghost" }),
    busy,
    el("span", { class: "grow" }),
    cost, meter, capInput,
    action("Fork", async () => {
      const name = prompt("Name this timeline", "what-if");
      if (!name) return;
      const fork = await api(`/branches/${branchId}/fork`, { method: "POST", body: { name } });
      location.hash = `#/branch/${fork.branch_id}`;
    }, { class: "ghost", title: "Branch the timeline here" }),
    el("a", { class: "button ghost", href: `#/branch/${branchId}/history` }, "History"),
    el("a", { class: "button ghost", href: `#/world/${world.id}` }, "World"));

  function renderStatus() {
    const stamp = status.sim_time || state.sim_time || "";
    date.textContent = when(stamp, false);
    const hour = Number((/T(\d\d):/.exec(stamp) || [])[1]);
    part.textContent = Number.isNaN(hour) ? "" : `${String(hour).padStart(2, "0")}:${stamp.slice(14, 16)} · ${daypart(hour)}`;
    playButton.textContent = status.running ? "❚❚" : "▶";
    busy.textContent = status.busy || (status.level === "pause" ? "paused: budget spent" : "");
    cost.textContent = status.run_cap ? `${money(status.cost)} / ${money(status.run_cap)}` : money(status.cost);
    meter.className = `meter ${status.level}`;
    meter.firstChild.style.width = status.run_cap ? `${Math.min(100, (status.cost / status.run_cap) * 100)}%` : "0%";
  }

  // -- map ----------------------------------------------------------------
  const canvas = el("canvas", { class: "mapcanvas", "aria-label": "Map" });
  const mapPanel = el("div", { class: "panel map" }, canvas);
  const map = createMap(canvas, {
    onSelect(id) {
      const entity = state.entities[id];
      if (entity && entity.kind === "person") selectPerson(id);
      else if (entity) showPlace(id);
    },
  });

  // -- side: tabs ---------------------------------------------------------
  const tabNow = el("button", { type: "button" }, "Now");
  const tabPeople = el("button", { type: "button" }, "People");
  const tabChange = el("button", { type: "button" }, "Change");
  const tabs = el("div", { class: "tabs", role: "tablist" }, tabNow, tabPeople, tabChange);
  const pane = el("div", { class: "pane" });
  const sidePanel = el("div", { class: "panel side" }, tabs, pane);

  const feedList = el("ul", { class: "plain feed" });
  const peopleList = el("ul", { class: "plain people" });
  const godOut = el("div", {});
  const godText = el("textarea", { rows: 2, placeholder: "Say what changes…", "aria-label": "Change the world" });
  const godBox = el("div", { class: "stack" },
    el("div", { class: "god-input" }, godText,
      action("Send", async () => {
        const text = godText.value.trim();
        if (!text) return;
        const result = await api(`/branches/${branchId}/god`, { method: "POST", body: { text } });
        renderVerdict(result);
        if (result.verdict === "apply" || result.verdict === "apply_adjusted") godText.value = "";
      }, { class: "primary" })),
    godOut);

  function showTab(name) {
    tab = name;
    selectedPerson = null;
    map.select(null);
    for (const [button, key] of [[tabNow, "now"], [tabPeople, "people"], [tabChange, "change"]]) {
      button.setAttribute("aria-selected", String(key === name));
    }
    fill(pane, name === "now" ? [el("div", { class: "row" }, quietToggle), feedList] : name === "people" ? peopleList : godBox);
    if (name === "now") pane.scrollTop = pane.scrollHeight;
    if (name === "people") renderPeople();
  }
  tabNow.addEventListener("click", () => showTab("now"));
  tabPeople.addEventListener("click", () => showTab("people"));
  tabChange.addEventListener("click", () => showTab("change"));

  // -- feed ---------------------------------------------------------------
  let showQuiet = false;
  const quietToggle = el("button", { type: "button", class: "ghost small" });
  quietToggle.addEventListener("click", () => {
    showQuiet = !showQuiet;
    feedList.classList.toggle("show-quiet", showQuiet);
    updateQuiet();
  });
  function updateQuiet() {
    const n = feedList.querySelectorAll("li.quiet").length;
    quietToggle.textContent = showQuiet ? "Hide routine" : `Show routine (${n})`;
    quietToggle.hidden = n === 0;
  }

  function feedItem(event) {
    const time = event.sim_time.slice(11, 16);
    const item = el("li", { class: `kind-${event.kind}${QUIET.test(event.narration) ? " quiet" : ""}`, "data-seq": event.seq },
      el("span", { class: "t" }, time),
      el("span", { class: "text" }, event.narration));
    item.addEventListener("click", () => toggleEvent(event, item));
    return item;
  }

  async function toggleEvent(event, item) {
    const open = item.querySelector(".detail");
    for (const node of feedList.querySelectorAll(".detail")) node.remove();
    if (open) return;
    const detail = el("div", { class: "detail small stack" }, "…");
    item.append(detail);
    try {
      const graph = await api(`/branches/${branchId}/causes/${event.seq}`);
      const earlier = graph.nodes.filter((n) => n.seq !== event.seq).slice(-5);
      fill(detail,
        earlier.length
          ? el("div", {}, el("div", { class: "muted" }, "Because"),
              el("ul", { class: "dots" }, earlier.map((n) => el("li", {}, n.narration))))
          : el("div", { class: "muted" }, "No recorded cause."),
        action("Branch from just before this", async () => {
          const name = prompt("Name this timeline", "what-if");
          if (!name) return;
          const fork = await api(`/branches/${branchId}/fork`, { method: "POST", body: { name, at_seq: event.seq - 1 } });
          location.hash = `#/branch/${fork.branch_id}`;
        }, { class: "quiet" }));
    } catch (error) {
      fill(detail, error.message);
    }
  }

  function addEvents(events) {
    const stick = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 80;
    for (const event of events) {
      if (event.seq <= lastSeq) continue;
      lastSeq = event.seq;
      const skipped = event.effects.some((effect) => effect.type === "AdvanceTime");
      if (!event.narration || (event.actor === "system" && !skipped)) continue;
      const day = event.sim_time.slice(0, 10);
      if (day !== lastDay) {
        feedList.append(el("li", { class: "day" }, when(event.sim_time, false)));
        lastDay = day;
      }
      feedList.append(feedItem(event));
    }
    while (feedList.children.length > FEED_LIMIT) feedList.firstChild.remove();
    updateQuiet();
    if (tab === "now" && stick) pane.scrollTop = pane.scrollHeight;
  }

  async function loadFeed(reset = false) {
    if (reset) { clear(feedList); lastSeq = 0; lastDay = null; }
    const events = await api(`/branches/${branchId}/events?newest=true&limit=${FEED_LIMIT}`);
    addEvents(events.reverse());
  }

  // -- people -------------------------------------------------------------
  function renderPeople() {
    if (tab !== "people" || selectedPerson) return;
    const people = Object.values(state.entities)
      .filter((e) => e.kind === "person")
      .sort((a, b) => a.name.localeCompare(b.name));
    fill(peopleList, ...people.map((p) => {
      const here = state.entities[p.location];
      const row = el("li", {},
        el("span", { class: "avatar" }, initials(p.name)),
        el("span", { class: "grow" },
          el("div", { class: "name" }, p.name, p.alive ? "" : " †"),
          el("div", { class: "where" },
            [p.attrs.occupation, here ? here.name : ""].filter(Boolean).join(" · "))));
      row.addEventListener("click", () => selectPerson(p.id));
      return row;
    }));
  }

  function showPlace(id) {
    selectedPerson = null;
    map.select(id);
    const place = state.entities[id];
    const here = Object.values(state.entities).filter((e) => e.kind === "person" && e.location === id);
    const stored = Object.entries(place.inventory);
    tab = "place";
    for (const button of [tabNow, tabPeople, tabChange]) button.setAttribute("aria-selected", "false");
    fill(pane,
      el("div", { class: "person stack" },
        el("h3", {}, place.name),
        place.attrs.description ? el("p", { class: "line" }, place.attrs.description) : null,
        el("div", { class: "block" }, el("h2", {}, "Here"),
          here.length
            ? el("div", { class: "relchips" }, here.map((p) =>
                el("button", { type: "button", onclick: () => selectPerson(p.id) }, p.name)))
            : el("span", { class: "muted" }, "Nobody")),
        stored.length
          ? el("div", { class: "block" }, el("h2", {}, "Stored"),
              stored.map(([item, n]) => `${n} ${nameOf(item)}`).join(", "))
          : null));
  }

  async function selectPerson(id) {
    selectedPerson = id || null;
    map.select(selectedPerson);
    if (!selectedPerson) return;
    tab = "person";
    for (const button of [tabNow, tabPeople, tabChange]) button.setAttribute("aria-selected", "false");
    await renderPerson();
  }

  const show = (value) => {
    if (typeof value === "string" && state.entities[value]) return state.entities[value].name;
    if (typeof value === "boolean") return value ? "yes" : "no";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  };
  function claim(subject, predicate, value) {
    const who = nameOf(subject);
    if (predicate === "location") return `${who} is at ${show(value)}`;
    if (predicate === "alive") return value ? `${who} is alive` : `${who} is dead`;
    return `${who} ${predicate}: ${show(value)}`;
  }

  function block(title, ...children) {
    const kids = children.flat().filter((c) => c !== null && c !== false && c !== undefined);
    return kids.length ? el("div", { class: "block" }, el("h2", {}, title), kids) : null;
  }

  async function renderPerson() {
    const id = selectedPerson;
    let person;
    try {
      person = await api(`/branches/${branchId}/agents/${encodeURIComponent(id)}`);
    } catch (error) {
      fill(pane, el("p", { class: "muted" }, error.message));
      return;
    }
    if (id !== selectedPerson) return;
    const persona = person.persona;
    const promises = Object.values(state.commitments || {})
      .filter((c) => c.status === "open" && (c.by === id || c.to === id));
    const known = ideas(person.attrs.knowledge, state.rules && state.rules.knowledge);
    const sure = (b) => (b.correct === false ? "bad" : b.correct === true ? "good" : "");
    const back = el("button", { class: "ghost", type: "button", onclick: () => showTab("people") }, "← People");

    fill(pane,
      el("div", { class: "person" },
        back,
        el("h3", { style: "margin-top:8px" }, person.name, person.alive ? "" : " †"),
        el("div", { class: "line" },
          [person.attrs.occupation, person.attrs.age !== undefined ? `${person.attrs.age}` : null,
            person.location_name].filter(Boolean).join(" · ")),
        person.thought && person.thought !== "routine"
          ? el("p", { class: "say", style: "margin-top:10px" }, `“${person.thought}”`)
          : person.thought === "routine"
            ? el("p", { class: "muted small", style: "margin-top:10px" }, "On their usual day.") : null,
        persona ? el("p", { style: "margin-top:10px" }, persona.summary) : null,
        block("Wants", persona && persona.goals.length ? el("ul", { class: "dots" }, persona.goals.map((g) => el("li", {}, g))) : null),
        block("Plan", person.plan.length ? el("ol", { class: "dots" }, person.plan.map((s) => el("li", {}, s))) : null),
        block("Promises", promises.length
          ? el("ul", { class: "dots" }, promises.map((c) =>
              el("li", {}, c.by === id ? `to ${nameOf(c.to)}: ` : `${nameOf(c.by)} to them: `, c.text)))
          : null),
        block("Knows how", known.length
          ? el("div", { class: "relchips" }, known.slice(0, 10).map((k) =>
              el("span", { class: `chip ${k.level >= 3 ? "good" : ""}`, title: LEVELS[k.level] || "" }, k.label)))
          : null),
        block("Believes", person.beliefs.length
          ? el("ul", { class: "plain" }, person.beliefs.slice(0, 5).map((b) =>
              el("li", { class: "row", style: "flex-wrap:nowrap;gap:8px;align-items:baseline" },
                el("span", { class: `dot ${sure(b)}`, title: b.correct === false ? "wrong" : b.correct === true ? "right" : "unchecked" }),
                el("span", {}, claim(b.subject, b.predicate, b.believed),
                  b.correct === false ? el("span", { class: "muted" }, ` (really ${show(b.actual)})`) : null))))
          : null),
        block("Remembers", person.memories.recent.length
          ? el("ul", { class: "plain" }, person.memories.recent.slice(0, 4).map((m) => el("li", {}, m.text)))
          : null),
        block("Knows", person.relations.length
          ? el("div", { class: "relchips" }, person.relations.map((r) => {
              const value = r.theirs ? r.theirs.value : 0;
              return el("button", {
                type: "button", class: value > 15 ? "pos" : value < -15 ? "neg" : "",
                title: r.theirs ? `${r.theirs.kind} (${value})` : "",
                onclick: () => selectPerson(r.other),
              }, r.name);
            }))
          : null),
        block("Carrying", person.inventory.length ? person.inventory.map((i) => `${i.quantity} ${i.name}`).join(", ") : null)));
  }

  // -- change the world ---------------------------------------------------
  const VERDICTS = {
    apply: "Done", apply_adjusted: "Done, adjusted", reject: "Not possible",
    needs_fork: "That is in the past", question: "Unclear",
  };

  function renderVerdict(result) {
    const box = el("div", { class: `verdict ${result.verdict}` },
      el("strong", {}, VERDICTS[result.verdict] || result.verdict),
      el("div", {}, result.question || result.explanation));
    if (result.verdict === "needs_fork") {
      box.append(action("Branch there and apply", async () => {
        const forked = await api(`/branches/${branchId}/god/fork`, { method: "POST", body: result });
        location.hash = `#/branch/${forked.branch_id}`;
      }, { class: "quiet" }));
    }
    godOut.prepend(box);
  }

  // -- live updates -------------------------------------------------------
  async function reloadState() {
    state = await api(`/branches/${branchId}/state`);
    map.update(state);
    renderStatus();
    renderPeople();
    if (selectedPerson) await renderPerson();
  }

  function scheduleReload() {
    clearTimeout(stateTimer);
    stateTimer = setTimeout(() => reloadState().catch((e) => toast(e.message)), 150);
  }

  view.append(el("div", { class: "world" }, topbar, el("div", { class: "stage" }, mapPanel, sidePanel)));
  renderStatus();
  map.update(state);
  await loadFeed();
  showTab("now");

  const stop = listen(`/ws/branches/${branchId}`, (message) => {
    if (message.status) { status = message.status; renderStatus(); }
    if (message.type === "events") { addEvents(message.events); scheduleReload(); }
    if (message.type === "paused") toast("Budget spent. Raise the cap to go on.");
    if (message.type === "error") toast(message.message);
  }, () => {
    api(`/branches/${branchId}/events?after=${lastSeq}`).then((events) => {
      if (events.length) { addEvents(events); scheduleReload(); }
    }).catch(() => {});
  });

  return () => {
    stop();
    clearTimeout(stateTimer);
    map.destroy();
  };
}
