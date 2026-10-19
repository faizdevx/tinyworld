// Scenario in, living town out. Shows the team building the world, then opens the Town.
import { api } from "./api.js";
import { action, el, fill, setCrumbs, tag, toast } from "./ui.js";

const STAGES = [
  ["building", "The team builds your world"],
  ["ready", "Laying it out as a town"],
];

export async function showLaunch(view, worldId) {
  setCrumbs([["Worlds", "#/"], ["Building", null]]);
  const head = el("h1", {}, "Building your world");
  const scenario = el("p", { class: "muted" }, "");
  const bar = el("div", { class: "bar" }, el("div", { class: "bar-fill", style: "width:2%" }));
  const status = el("p", { class: "muted small" }, "");
  const tasks = el("ul", { class: "plain stack" });
  const feed = el("div", { class: "launch-feed small" });
  const note = el("p", { class: "muted small" }, "");
  view.append(el("div", { class: "page stack launch" },
    el("div", { class: "eyebrow muted small" }, "Step 1 of 2"), head, scenario, bar, status,
    el("div", { class: "launch-cols" },
      el("div", {}, el("h2", {}, "The team"), tasks),
      el("div", {}, el("h2", {}, "What they are saying"), feed)),
    note));

  let alive = true;
  let entered = false;

  async function tick() {
    if (!alive) return;
    let p;
    try { p = await api(`/launch/${worldId}`); } catch (error) { note.textContent = error.message; return setTimeout(tick, 3000); }
    scenario.textContent = p.scenario;
    bar.firstChild.style.width = `${Math.max(2, Math.round(p.progress * 100))}%`;
    status.textContent = `${p.tasks.filter((t) => t.status === "done").length} of ${p.tasks.length || "?"} jobs done · ${p.calls} model calls · ${p.backend === "model" ? "your model" : "offline stand-in"}`;
    fill(tasks, ...p.tasks.map((t) => el("li", { class: "row" },
      tag(t.status, t.status === "done" ? "good" : t.status === "blocked" ? "bad" : t.status === "doing" ? "warn" : ""),
      el("span", {}, t.title), t.who ? el("span", { class: "muted small" }, t.who) : null)));
    fill(feed, ...p.feed.map((f) => el("div", {}, f.text)));
    if (p.asking.length) note.textContent = `The team is asking: ${p.asking[0]}`;
    if (p.stage === "failed") {
      head.textContent = "The build did not finish";
      note.textContent = "Open the studio to see why, or try a simpler scenario.";
      note.append(" ", el("a", { href: `#/studio/${worldId}` }, "Open the studio"));
      return;
    }
    if (p.stage === "ready" && !entered) {
      entered = true;
      head.textContent = "Your world is ready";
      status.textContent = "Laying it out as a town…";
      try {
        const { branch_id } = await api(`/launch/${worldId}/enter`, { method: "POST" });
        location.hash = `#/town/${branch_id}`;
      } catch (error) {
        note.textContent = error.message;
        entered = false;
      }
      return;
    }
    setTimeout(tick, 1500);
  }
  tick();
  return () => { alive = false; };
}

// The front door: one box, one button.
export function scenarioBox(view) {
  const box = el("textarea", {
    id: "scenario", rows: 3, "aria-label": "Your scenario",
    placeholder: "A trading town on the Silk Road in 1250, and the road has just closed.",
  });
  const go = action("Build it and let it live", async () => {
    const text = box.value.trim();
    if (text.length < 8) { toast("Describe the scenario in a sentence or two."); return; }
    const r = await api("/launch", { method: "POST", body: { scenario: text } });
    location.hash = `#/launch/${r.world_id}`;
  }, { class: "primary" });
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) go.click(); });
  const examples = [
    "India never got Jio in 2016. Lucknow, Uttar Pradesh.",
    "1941. Germany never invades the USSR. A town near Berlin.",
    "A small trading town on the Silk Road, 1250, where the road is closed.",
    "A Mars colony ten years after the supply ships stopped.",
  ];
  return el("div", { class: "scenario stack" },
    box, el("div", { class: "row" }, go, el("span", { class: "muted small" }, "Ctrl+Enter")),
    el("div", { class: "row small" }, el("span", { class: "muted" }, "Try:"),
      ...examples.map((x) => el("button", { class: "link", type: "button", onclick: () => { box.value = x; box.focus(); } }, x.split(".")[0].slice(0, 40)))));
}
