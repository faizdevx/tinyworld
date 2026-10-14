import { api } from "./api.js";
import { action, el, setCrumbs, tag } from "./ui.js";

const EXAMPLE = "1941. Germany never invades the USSR. A town near Berlin.";

export async function showHome(view) {
  setCrumbs([]);
  const premise = el("textarea", {
    placeholder: EXAMPLE,
    "aria-label": "World premise",
  });
  const list = el("ul", { class: "plain world-list" });

  async function refresh() {
    const worlds = await api("/worlds");
    list.replaceChildren(
      ...(worlds.length
        ? worlds.reverse().map((world) =>
            el("li", {},
              el("a", { class: "grow", href: `#/world/${world.id}` }, world.premise.split("\n")[0]),
              tag(world.stage, world.stage === "done" ? "good" : world.stage === "error" ? "bad" : "warn"),
              el("span", { class: "muted small nowrap" },
                `${world.branches} timeline${world.branches === 1 ? "" : "s"}`)))
        : [el("li", { class: "muted" }, "No worlds yet.")]),
    );
  }

  const page = el("div", { class: "page stack" },
    el("div", { class: "panel hero stack" },
      el("h1", {}, "Describe a world"),
      el("p", { class: "muted" },
        "A period, a place, and what is different. It is researched, written up as a world you can review and edit, then set running with people who decide for themselves."),
      premise,
      el("div", { class: "row" },
        action("Create world", async () => {
          const text = premise.value.trim() || EXAMPLE;
          const created = await api("/worlds", { method: "POST", body: { premise: text } });
          location.hash = `#/world/${created.world_id}`;
        }, { class: "primary" }),
        action("Open a small test town", async () => {
          const toy = await api("/worlds/toy", { method: "POST" });
          location.hash = `#/branch/${toy.branch_id}`;
        }),
        el("span", { class: "muted small" }, "Leave empty to use the example."))),
    el("div", { class: "panel" }, el("h2", {}, "Your worlds"), list),
  );
  view.append(page);
  await refresh();
}
