import { api } from "./api.js";
import { action, clear, download, el, money, setCrumbs, tag, toast, when } from "./ui.js";

export async function showHistory(view, branchId) {
  const branch = await api(`/branches/${branchId}`);
  const world = await api(`/worlds/${branch.world_id}`);
  setCrumbs([
    [world.premise.split("\n")[0].slice(0, 50), `#/world/${world.id}`],
    [branch.name, `#/branch/${branchId}`],
    ["History", null],
  ]);

  const [chronicle, metrics] = await Promise.all([
    api(`/branches/${branchId}/chronicle`),
    api(`/branches/${branchId}/metrics`),
  ]);

  // -- timelines ----------------------------------------------------------
  const depth = new Map();
  const byId = new Map(world.branches.map((b) => [b.id, b]));
  const depthOf = (b) => {
    if (!depth.has(b.id)) depth.set(b.id, b.parent_id && byId.has(b.parent_id) ? depthOf(byId.get(b.parent_id)) + 1 : 0);
    return depth.get(b.id);
  };
  const compare = el("select", { "aria-label": "Timeline to compare with" },
    el("option", { value: "" }, "Compare with…"),
    world.branches.filter((b) => b.id !== branchId).map((b) => el("option", { value: b.id }, b.name)));
  const diffBox = el("div", { class: "stack" });
  compare.addEventListener("change", () => renderDiff().catch((e) => toast(e.message)));

  const tree = el("div", { class: "panel stack" },
    el("h2", {}, "Timelines"),
    el("ul", { class: "plain tree" }, world.branches.map((b) =>
      el("li", { style: `padding-left:${depthOf(b) * 18}px` },
        b.id === branchId ? el("strong", {}, b.name) : el("a", { href: `#/branch/${b.id}/history` }, b.name),
        el("span", { class: "muted small" },
          `${b.head_seq} events${b.parent_id ? `, split from ${byId.get(b.parent_id)?.name ?? "?"} at event ${b.fork_seq}` : ""}`),
        el("a", { class: "small", href: `#/branch/${b.id}` }, "open")))),
    world.branches.length > 1 ? el("div", { class: "row" }, compare) : null,
    diffBox);

  async function renderDiff() {
    clear(diffBox);
    if (!compare.value) return;
    const diff = await api(`/branches/${branchId}/diff/${compare.value}`);
    const other = byId.get(compare.value).name;
    const side = (label, part) => el("div", {},
      el("h3", {}, `${label} · ${when(part.sim_time, false)}`),
      part.events.length
        ? el("ul", { class: "plain small" }, part.events.slice(-40).map((e) =>
            el("li", {}, el("span", { class: "muted" }, `${when(e.sim_time, false)} `), e.narration)))
        : el("p", { class: "muted" }, "Nothing since the split."));
    const fate = (p) => (p ? `${p.alive ? "alive" : "dead"}, ${p.location}` : "does not exist");
    diffBox.append(
      el("p", { class: "muted" }, `The two timelines share history up to event ${diff.split_seq}.`),
      el("div", { class: "columns" }, side(branch.name, diff.a), side(other, diff.b)),
      diff.people.length
        ? el("div", {}, el("h3", {}, "People whose fate differs"),
            el("table", {},
              el("thead", {}, el("tr", {}, ["", branch.name, other].map((h) => el("th", {}, h)))),
              el("tbody", {}, diff.people.map((p) =>
                el("tr", {}, el("td", {}, p.name), el("td", {}, fate(p.a)), el("td", {}, fate(p.b)))))))
        : null,
      diff.facts_only_a.length || diff.facts_only_b.length
        ? el("div", { class: "columns" },
            el("div", {}, el("h3", {}, `True only in ${branch.name}`),
              el("ul", { class: "dots" }, diff.facts_only_a.map((f) => el("li", {}, f)))),
            el("div", {}, el("h3", {}, `True only in ${other}`),
              el("ul", { class: "dots" }, diff.facts_only_b.map((f) => el("li", {}, f)))))
        : null,
      diff.processes.length
        ? el("div", {}, el("h3", {}, "Undertakings"),
            el("ul", { class: "dots" }, diff.processes.map((p) => {
              const show = (x) => (x ? `${x.status}, ${Math.round(x.progress * 100)}%` : "never begun");
              return el("li", {}, `${p.name}: ${show(p.a)} / ${show(p.b)}`);
            })))
        : null);
  }

  // -- chronicle and causes ----------------------------------------------
  const causeBox = el("div", { class: "panel stack", hidden: true });

  async function showCauses(entry) {
    const graph = await api(`/branches/${branchId}/causes/${entry.seq}`);
    const incoming = new Map();
    for (const edge of graph.edges) {
      if (!incoming.has(edge.to)) incoming.set(edge.to, []);
      incoming.get(edge.to).push(edge);
    }
    const nodes = new Map(graph.nodes.map((n) => [n.seq, n]));
    const rows = [];
    const seen = new Set();
    // Walk back from the outcome, indenting each step further into the past.
    (function walk(seq, level, why) {
      const node = nodes.get(seq);
      if (!node) return;
      rows.push(el("li", { style: `--depth:${level}` },
        why ? tag(why) : tag("outcome", "good"), " ",
        el("span", { class: "muted" }, `${when(node.sim_time, false)} `), node.narration || "(no description)"));
      if (seen.has(seq)) return;
      seen.add(seq);
      for (const edge of incoming.get(seq) || []) walk(edge.from, level + 1, edge.why);
    })(graph.root, 0, null);
    causeBox.hidden = false;
    clear(causeBox).append(
      el("h2", {}, "How it came about"),
      rows.length > 1
        ? el("ul", { class: "plain chain" }, rows)
        : el("p", { class: "muted" }, "Nothing is recorded as having led to this."),
      el("p", { class: "muted small" },
        "“prompted”: the person had just learned of it. “undertaking”: earlier work on the same effort. “origin”: how they came into the world."));
    causeBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const chroniclePanel = el("div", { class: "panel" },
    el("h2", {}, "Chronicle"),
    chronicle.length
      ? chronicle.map((year) => el("div", { class: "year" },
          el("h3", {}, String(year.year)),
          el("ul", { class: "plain" }, year.entries.map((entry) =>
            el("li", { class: "row" },
              entry.kind === "god" ? tag("god", "god") : entry.kind === "period" ? tag("time passes") : null,
              el("span", { class: "grow" }, entry.narration),
              entry.kind === "period" ? null
                : action("why?", () => showCauses(entry), { class: "quiet" }))))))
      : el("p", { class: "muted" },
          "Nothing chronicled yet. Skip some time, or intervene, and it will appear here."));

  // -- numbers ------------------------------------------------------------
  const population = metrics.population;
  const stats = el("div", { class: "panel stack" },
    el("h2", {}, "Numbers"),
    el("dl", { class: "kv" },
      el("dt", {}, "Date"), el("dd", {}, when(metrics.sim_time)),
      el("dt", {}, "Simulated"), el("dd", {}, `${metrics.simulated_years.toFixed(2)} years, ${metrics.seq} events`),
      el("dt", {}, "People followed"), el("dd", {}, `${population.alive} alive, ${population.dead} dead`),
      el("dt", {}, "Background population"), el("dd", {}, population.background || "–"),
      el("dt", {}, "Model cost"), el("dd", {}, `${money(metrics.cost.total)} over ${metrics.cost.calls} calls`),
      el("dt", {}, "Cost per simulated year"), el("dd", {}, money(metrics.cost.per_simulated_year))),
    metrics.groups.length
      ? el("table", {},
          el("thead", {}, el("tr", {}, el("th", {}, "Group"), el("th", { class: "num" }, "Members"),
            el("th", { class: "num" }, "Morale"), el("th", { class: "num" }, "Influence"))),
          el("tbody", {}, metrics.groups.map((g) =>
            el("tr", {}, el("td", {}, g.name), el("td", { class: "num" }, g.members ?? "–"),
              el("td", { class: "num" }, g.morale ?? "–"), el("td", { class: "num" }, g.influence ?? "–")))))
      : null,
    metrics.resources.length
      ? el("div", {}, el("span", { class: "muted" }, "In the world: "),
          metrics.resources.map((r) => `${r.total} ${r.name}`).join(", "))
      : null,
    metrics.processes.length
      ? el("div", {}, el("h3", {}, "Undertakings"),
          el("ul", { class: "dots" }, metrics.processes.map((p) =>
            el("li", {}, `${p.name}: ${p.status}, ${Math.round(p.progress * 100)}%`))))
      : null,
    el("div", { class: "row" },
      action("Export this timeline", async () => {
        download(`tinyworld-${branch.name}.json`, await api(`/branches/${branchId}/export`));
      })));

  view.append(el("div", { class: "page stack" }, tree, causeBox, el("div", { class: "columns" }, chroniclePanel, stats)));
}
