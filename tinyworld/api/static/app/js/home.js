import { api } from "./api.js";
import { action, el, setCrumbs, tag } from "./ui.js";

const EXAMPLE = "India never got Jio in 2016. Lucknow.";

export async function showHome(view) {
  setCrumbs([]);
  const premise = el("textarea", { placeholder: EXAMPLE, "aria-label": "World premise", rows: 2 });
  const list = el("ul", { class: "plain worlds" });

  async function refresh() {
    const worlds = await api("/worlds");
    list.replaceChildren(
      ...worlds.reverse().map((world) =>
        el("li", {},
          el("a", { class: "title", href: `#/world/${world.id}` }, world.premise.split("\n")[0]),
          tag(world.stage, world.stage === "done" ? "good" : world.stage === "error" ? "bad" : "warn"),
          el("span", { class: "muted small nowrap" }, `${world.branches} timeline${world.branches === 1 ? "" : "s"}`))),
    );
  }

  const create = action("Create", async () => {
    const text = premise.value.trim() || EXAMPLE;
    const created = await api("/worlds", { method: "POST", body: { premise: text } });
    location.hash = `#/world/${created.world_id}`;
  }, { class: "primary" });

  premise.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) create.click();
  });

  view.append(
    el("div", { class: "page" },
      el("div", { class: "hero" },
        el("h1", {}, "What world?"),
        el("div", { class: "prompt" }, premise, create),
        el("div", { class: "row", style: "margin-top:10px" },
          action("Try a small town", async () => {
            const toy = await api("/worlds/toy", { method: "POST" });
            location.hash = `#/branch/${toy.branch_id}`;
          }, { class: "ghost" }))),
      list),
  );
  await refresh();
}
