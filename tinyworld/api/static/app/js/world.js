import { api, listen } from "./api.js";
import { createMap } from "./map.js";
import { action, clear, fill, el, money, setCrumbs, shortId, tag, toast, when } from "./ui.js";

const FEED_LIMIT = 300;

export async function showWorld(view, branchId) {
  const branch = await api(`/branches/${branchId}`);
  const world = await api(`/worlds/${branch.world_id}`);
  setCrumbs([
    [world.premise.split("\n")[0].slice(0, 50), `#/world/${world.id}`],
    [branch.name, null],
  ]);

  let status = branch.status;
  let state = await api(`/branches/${branchId}/state`);
  let selectedPerson = null;
  let selectedEvent = null;
  let lastSeq = 0;
  let stateTimer = null;
  const nameOf = (id) => (state.entities[id] ? state.entities[id].name : id === "god" ? "God" : shortId(id));

  // -- top bar ------------------------------------------------------------
  const date = el("span", { class: "date" });
  const playButton = action("Play", async () => {
    await api(`/branches/${branchId}/run`, {
      method: "POST", body: { action: status.running ? "pause" : "play", delay: Number(speed.value) },
    });
  }, { class: "primary" });
  const speed = el("select", { "aria-label": "Speed" },
    el("option", { value: "2" }, "slow"),
    el("option", { value: "0.8", selected: true }, "normal"),
    el("option", { value: "0.1" }, "fast"));
  speed.addEventListener("change", async () => {
    if (!status.running) return;
    await api(`/branches/${branchId}/run`, { method: "POST", body: { action: "play", delay: Number(speed.value) } });
  });
  const skipSpan = el("input", { class: "short", value: "1mo", "aria-label": "How far to skip", title: "e.g. 3d, 2w, 6mo, 20y" });
  const cost = el("span", { class: "small nowrap" });
  const meter = el("div", { class: "meter", title: "Share of the budget spent" }, el("i", {}));
  const capInput = el("input", { class: "short", type: "number", min: "0", step: "0.5", placeholder: "cap $", "aria-label": "Budget cap in dollars" });
  const busy = el("span", { class: "small muted" });

  const bar = el("div", { class: "panel bar" },
    date,
    el("div", { class: "row" },
      playButton,
      action("Step", () => api(`/branches/${branchId}/run`, { method: "POST", body: { action: "step" } })),
      speed),
    el("div", { class: "row" },
      skipSpan,
      action("Skip", async () => {
        const result = await api(`/branches/${branchId}/skip`, { method: "POST", body: { span: skipSpan.value } });
        const dropped = result.rejected.length ? ` ${result.rejected.length} proposed event(s) were ruled out.` : "";
        toast(result.complete
          ? `Skipped ${skipSpan.value} in ${result.periods} step(s).${dropped}`
          : `Stopped early: ${result.stopped}. Raise the budget to continue.`);
        await loadFeed(true);
      })),
    el("div", { class: "row" },
      cost, meter, capInput,
      action("Set cap", async () => {
        await api(`/branches/${branchId}/budget`, { method: "POST", body: { run_cap: Number(capInput.value) || 0 } });
      })),
    busy,
    el("span", { class: "grow" }),
    action("Fork here", async () => {
      const name = prompt("Name for the new timeline", "what-if");
      if (!name) return;
      const fork = await api(`/branches/${branchId}/fork`, { method: "POST", body: { name } });
      location.hash = `#/branch/${fork.branch_id}`;
    }),
    el("a", { class: "button", href: `#/branch/${branchId}/history` }, "History"),
    el("a", { class: "button", href: `#/world/${world.id}` }, "Bible"));

  function renderStatus() {
    date.textContent = status.sim_time_text;
    playButton.textContent = status.running ? "Pause" : "Play";
    busy.textContent = status.busy || (status.level === "pause" ? "Paused: budget spent" : "");
    cost.textContent = status.run_cap
      ? `${money(status.cost)} / ${money(status.run_cap)}`
      : `${money(status.cost)}${status.offline ? " est." : ""}`;
    meter.className = `meter ${status.level}`;
    meter.firstChild.style.width = status.run_cap
      ? `${Math.min(100, (status.cost / status.run_cap) * 100)}%` : "0%";
  }

  // -- map ----------------------------------------------------------------
  const canvas = el("canvas", { class: "mapcanvas", "aria-label": "Map of the world" });
  const mapPanel = el("div", { class: "panel map" }, canvas,
    el("span", { class: "maphint small muted" }, "Dashed paths cannot be seen across. Squares are closed rooms."));
  const map = createMap(canvas, {
    onSelect(id) {
      const entity = state.entities[id];
      if (entity && entity.kind === "person") selectPerson(id);
      else if (entity) showPlace(id);
    },
  });

  // -- feed ---------------------------------------------------------------
  const feedList = el("ul", { class: "plain" });
  const feedPanel = el("div", { class: "panel feed" },
    el("h2", {}, "What is happening"), el("div", { class: "scroll" }, feedList));

  function feedItem(event) {
    const item = el("li", { class: `kind-${event.kind}`, "data-seq": event.seq },
      el("div", { class: "meta" },
        el("span", {}, when(event.sim_time)),
        event.actor.startsWith("person:") ? el("span", {}, nameOf(event.actor)) : null,
        event.kind === "god" ? tag("god", "god") : null,
        event.kind === "chronicle" ? tag("chronicle") : null,
        event.location ? el("span", {}, `at ${nameOf(event.location)}`) : null),
      el("div", { class: "text" }, event.narration));
    item.addEventListener("click", () => toggleEvent(event, item));
    return item;
  }

  async function toggleEvent(event, item) {
    const open = item.querySelector(".detail");
    for (const node of feedList.querySelectorAll(".detail")) node.remove();
    for (const node of feedList.querySelectorAll(".selected")) node.classList.remove("selected");
    if (open) { selectedEvent = null; return; }
    selectedEvent = event.seq;
    item.classList.add("selected");
    const detail = el("div", { class: "detail small stack" }, "Tracing…");
    item.append(detail);
    try {
      const graph = await api(`/branches/${branchId}/causes/${event.seq}`);
      const earlier = graph.nodes.filter((n) => n.seq !== event.seq);
      fill(detail, 
        earlier.length
          ? el("div", {}, el("div", { class: "muted" }, "What led to this:"),
              el("ul", { class: "dots" }, earlier.slice(-6).map((n) =>
                el("li", {}, `${when(n.sim_time, false)}: ${n.narration}`))))
          : el("div", { class: "muted" }, "Nothing recorded as leading to this."),
        el("div", { class: "row" },
          action("Fork from just before this", async () => {
            const name = prompt("Name for the new timeline", "what-if");
            if (!name) return;
            const fork = await api(`/branches/${branchId}/fork`, {
              method: "POST", body: { name, at_seq: event.seq - 1 },
            });
            location.hash = `#/branch/${fork.branch_id}`;
          }, { class: "quiet" })));
    } catch (error) {
      fill(detail, error.message);
    }
  }

  function addEvents(events) {
    for (const event of events) {
      if (event.seq <= lastSeq) continue;
      lastSeq = event.seq;
      // Housekeeping is not news; a skipped stretch of time is.
      const skipped = event.effects.some((effect) => effect.type === "AdvanceTime");
      if (!event.narration || (event.actor === "system" && !skipped)) continue;
      feedList.prepend(feedItem(event));
    }
    while (feedList.children.length > FEED_LIMIT) feedList.lastChild.remove();
  }

  async function loadFeed(reset = false) {
    if (reset) { clear(feedList); lastSeq = 0; }
    const events = await api(`/branches/${branchId}/events?newest=true&limit=${FEED_LIMIT}`);
    addEvents(events.reverse());
  }

  // -- inspector ----------------------------------------------------------
  const personSelect = el("select", { "aria-label": "Person" });
  const inspectBody = el("div", { class: "scroll stack" });
  const inspectPanel = el("div", { class: "panel inspect" },
    el("div", { class: "row" }, el("h2", { class: "grow" }, "Who is who"), personSelect), inspectBody);
  personSelect.addEventListener("change", () => selectPerson(personSelect.value));

  function renderPeople() {
    const people = Object.values(state.entities)
      .filter((e) => e.kind === "person")
      .sort((a, b) => a.name.localeCompare(b.name));
    personSelect.replaceChildren(
      el("option", { value: "" }, "Choose someone…"),
      ...people.map((p) => el("option", { value: p.id, selected: p.id === selectedPerson },
        `${p.name}${p.alive ? "" : " (dead)"}`)));
  }

  function showPlace(id) {
    selectedPerson = null;
    map.select(id);
    renderPeople();
    const place = state.entities[id];
    const here = Object.values(state.entities).filter((e) => e.kind === "person" && e.location === id);
    const stored = Object.entries(place.inventory);
    fill(inspectBody, 
      el("h3", {}, place.name),
      el("p", {}, place.attrs.description || ""),
      el("div", {}, el("span", { class: "muted" }, "Here: "),
        here.length ? here.map((p, i) => [i ? ", " : "",
          el("button", { class: "quiet", type: "button", onclick: () => selectPerson(p.id) }, p.name)])
          : "nobody"),
      stored.length ? el("div", {}, el("span", { class: "muted" }, "Stored: "),
        stored.map(([item, n]) => `${n} ${nameOf(item)}`).join(", ")) : null);
  }

  async function selectPerson(id) {
    selectedPerson = id || null;
    map.select(selectedPerson);
    renderPeople();
    if (!selectedPerson) { clear(inspectBody); return; }
    await renderPerson();
  }

  async function renderPerson() {
    const id = selectedPerson;
    let person;
    try {
      person = await api(`/branches/${branchId}/agents/${encodeURIComponent(id)}`);
    } catch (error) {
      fill(inspectBody, el("p", { class: "muted" }, error.message));
      return;
    }
    if (id !== selectedPerson) return;
    const persona = person.persona;
    const tierLabel = { 0: "decides every step", 1: "decides now and then", 2: "background" }[person.attrs.tier ?? 0];
    fill(inspectBody, 
      el("div", {},
        el("h3", {}, person.name, " ", person.alive ? null : tag("dead", "bad")),
        el("div", { class: "muted small" },
          [person.attrs.age !== undefined ? `${person.attrs.age}` : null, person.attrs.occupation,
            `at ${person.location_name}`, tierLabel, `cost ${money(person.cost)}`].filter(Boolean).join(" · "))),
      persona ? el("p", {}, persona.summary) : el("p", { class: "muted" }, "No character sheet: part of the background."),
      person.thought ? el("p", {}, el("span", { class: "muted" }, "Thinking: "), person.thought) : null,
      persona && persona.goals.length
        ? el("div", {}, el("span", { class: "muted" }, "Wants: "), persona.goals.join("; ")) : null,
      persona && persona.fears.length
        ? el("div", {}, el("span", { class: "muted" }, "Fears: "), persona.fears.join("; ")) : null,
      persona && persona.secrets.length
        ? el("div", {}, el("span", { class: "muted" }, "Secret: "), persona.secrets.join("; ")) : null,
      person.plan.length
        ? el("div", {}, el("h2", {}, "Plan"), el("ol", { class: "dots" }, person.plan.map((s) => el("li", {}, s)))) : null,
      el("div", {},
        el("h2", {}, "Believes"),
        person.beliefs.length
          ? el("ul", { class: "plain" }, person.beliefs.map((b) =>
              el("li", { class: "belief" },
                b.correct === true ? tag("right", "good") : b.correct === false ? tag("wrong", "bad") : tag("unknown"),
                el("span", { class: "grow" },
                  `${nameOf(b.subject)} ${b.predicate}: ${JSON.stringify(b.believed)}`,
                  b.correct === false ? el("span", { class: "muted" }, ` (actually ${JSON.stringify(b.actual)})`) : null,
                  el("span", { class: "muted small" },
                    ` — ${b.source_name ? `heard from ${b.source_name}` : b.origin}, ${Math.round(b.confidence * 100)}% sure`)))))
          : el("p", { class: "muted" }, "Nothing in particular yet.")),
      el("div", {},
        el("h2", {}, `Remembers (${person.memories.count})`),
        person.memories.recent.length
          ? el("ul", { class: "plain" }, person.memories.recent.slice(0, 8).map((m) =>
              el("li", { class: "memory" },
                el("span", { class: "imp small", title: "importance" }, m.importance.toFixed(1)),
                el("span", {}, m.text, m.kind === "reflection" ? [" ", tag("reflection")] : null))))
          : el("p", { class: "muted" }, "No memories yet.")),
      person.relations.length
        ? el("div", {}, el("h2", {}, "Relations"),
            el("ul", { class: "plain" }, person.relations.map((r) =>
              el("li", {}, el("button", { class: "quiet", type: "button", onclick: () => selectPerson(r.other) }, r.name),
                r.theirs ? ` ${r.theirs.kind} (${r.theirs.value > 0 ? "+" : ""}${r.theirs.value})` : ""))))
        : null,
      person.inventory.length
        ? el("div", {}, el("span", { class: "muted" }, "Carrying: "),
            person.inventory.map((i) => `${i.quantity} ${i.name}`).join(", "))
        : null);
  }

  // -- god console --------------------------------------------------------
  const godText = el("textarea", { rows: 3, placeholder: "Make a drought hit the region next summer…", "aria-label": "Command the world" });
  const godOut = el("div", { class: "scroll stack" });
  const godPanel = el("div", { class: "panel godbox stack" },
    el("h2", {}, "Change the world"),
    godText,
    el("div", { class: "row" },
      action("Send", async () => {
        const text = godText.value.trim();
        if (!text) return;
        const result = await api(`/branches/${branchId}/god`, { method: "POST", body: { text } });
        renderVerdict(result);
        if (result.verdict === "apply" || result.verdict === "apply_adjusted") godText.value = "";
      }, { class: "primary" }),
      status.offline
        ? el("span", { class: "muted small" }, "Offline: try “kill NAME”, “move NAME to PLACE”, “NAME is born at PLACE”, “skip 3d”, or any sentence as an event.")
        : null),
    godOut);

  const VERDICTS = {
    apply: "Done", apply_adjusted: "Done, with a change", reject: "Not possible",
    needs_fork: "That is in the past", question: "Unclear",
  };

  function renderVerdict(result) {
    const box = el("div", { class: `verdict ${result.verdict} stack` },
      el("div", {}, el("strong", {}, VERDICTS[result.verdict] || result.verdict), el("span", { class: "muted" }, ` — “${result.text}”`)),
      el("div", {}, result.question || result.explanation),
      result.scheduled.length ? el("div", { class: "muted small" }, `${result.scheduled.length} event(s) queued.`) : null);
    if (result.verdict === "needs_fork") {
      box.append(action("Branch the timeline there and apply", async () => {
        const forked = await api(`/branches/${branchId}/god/fork`, { method: "POST", body: result });
        toast(forked.result.explanation || "Applied on a new timeline.");
        location.hash = `#/branch/${forked.branch_id}`;
      }));
    }
    godOut.prepend(box);
  }

  // -- live updates -------------------------------------------------------
  async function reloadState() {
    state = await api(`/branches/${branchId}/state`);
    map.update(state);
    renderPeople();
    if (selectedPerson) await renderPerson();
  }

  function scheduleReload() {
    clearTimeout(stateTimer);
    stateTimer = setTimeout(() => reloadState().catch((e) => toast(e.message)), 150);
  }

  view.append(el("div", { class: "world" }, bar, mapPanel, feedPanel, inspectPanel, godPanel));
  renderStatus();
  map.update(state);
  renderPeople();
  await loadFeed();

  const stop = listen(`/ws/branches/${branchId}`, (message) => {
    if (message.status) { status = message.status; renderStatus(); }
    if (message.type === "events") { addEvents(message.events); scheduleReload(); }
    if (message.type === "paused") toast("Paused: the budget is spent. Raise the cap to go on.");
    if (message.type === "error") toast(message.message);
  }, () => {
    // After a reconnect, catch up on anything missed while the socket was down.
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
