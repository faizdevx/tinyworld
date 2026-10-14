import { api, listen } from "./api.js";
import { action, clear, fill, el, setCrumbs, tag, toast } from "./ui.js";

const SECTION_ORDER = [
  "geography", "politics", "economy", "technology", "culture", "factions", "figures", "tensions",
];
const STAGES = ["premise", "divergence", "research", "sections", "critic", "digest", "done"];

function list(items) {
  return items && items.length
    ? el("ul", { class: "dots" }, items.map((item) => el("li", {}, item)))
    : el("span", { class: "muted" }, "none");
}

function kv(pairs) {
  return el("dl", { class: "kv" },
    pairs.filter(([, value]) => value !== "" && value !== null && value !== undefined)
      .map(([key, value]) => [el("dt", {}, key), el("dd", {}, value)]));
}

// A readable rendering of each bible section. Editing happens on the raw JSON.
const RENDER = {
  geography: (s) => [
    el("p", {}, s.overview),
    el("div", { class: "cards" }, s.places.map((p) =>
      el("div", { class: "card" },
        el("h3", {}, p.name, " ", p.enclosed ? tag("enclosed") : null),
        el("p", { class: "muted small" }, [p.kind, p.district].filter(Boolean).join(" · ")),
        el("p", {}, p.description),
        p.connects_to.length
          ? el("p", { class: "small muted" }, "Leads to: ",
              p.connects_to.map((c) => `${c.to} (${c.travel_minutes} min)`).join(", "))
          : null))),
  ],
  politics: (s) => [
    el("p", {}, s.overview),
    el("h3", {}, "Institutions"),
    el("div", { class: "cards" }, s.institutions.map((i) =>
      el("div", { class: "card" }, el("h3", {}, i.name), el("p", {}, i.description),
        kv([["Leader", i.leader], ["Members", i.members || ""], ["Aims", i.aims.join("; ")]])))),
    el("h3", {}, "Laws"), list(s.laws),
  ],
  economy: (s) => [
    el("p", {}, s.overview),
    el("h3", {}, "Resources"),
    el("table", {},
      el("thead", {}, el("tr", {}, ["Resource", "Unit", "Scarcity"].map((h) => el("th", {}, h)))),
      el("tbody", {}, s.resources.map((r) =>
        el("tr", {}, el("td", {}, r.name), el("td", {}, r.unit), el("td", {}, r.scarcity))))),
    el("h3", {}, "Starting stock"),
    list(s.stocks.map((x) => `${x.quantity} ${x.resource} at ${x.holder}`)),
    el("h3", {}, "Scarcities"), list(s.scarcities),
  ],
  technology: (s) => [
    el("p", {}, s.overview),
    el("div", { class: "columns" },
      el("div", {}, el("h3", {}, "In use"), list(s.available)),
      el("div", {}, el("h3", {}, "Does not exist yet"), list(s.not_yet))),
  ],
  culture: (s) => [
    el("p", {}, s.overview),
    el("div", { class: "columns" },
      el("div", {}, el("h3", {}, "Norms"), list(s.norms)),
      el("div", {}, el("h3", {}, "Daily life"), list(s.daily_life))),
    el("h3", {}, "Population"),
    list(s.population.map((g) => `${g.name}: ${g.count}${g.description ? ` — ${g.description}` : ""}`)),
  ],
  factions: (s) => [
    el("div", { class: "cards" }, s.factions.map((f) =>
      el("div", { class: "card" }, el("h3", {}, f.name), el("p", {}, f.description),
        kv([["Leader", f.leader], ["Members", f.members || ""], ["Influence", f.influence],
          ["Aims", f.aims.join("; ")]])))),
  ],
  figures: (s) => [
    el("div", { class: "cards" }, s.figures.map((f) =>
      el("div", { class: "card" },
        el("h3", {}, f.name),
        el("p", { class: "muted small" }, `${f.age}, ${f.occupation}${f.faction ? ` · ${f.faction}` : ""}`),
        el("p", {}, f.summary),
        kv([["Wants", f.goals.join("; ")], ["Fears", f.fears.join("; ")],
          ["Secret", f.secrets.join("; ")], ["Home", f.home]])))),
  ],
  tensions: (s) => [
    el("ul", { class: "plain" }, s.tensions.map((t) =>
      el("li", {}, el("div", {}, t.text),
        el("div", { class: "muted small" }, [t.parties.join(", "), t.stakes].filter(Boolean).join(" — "))))),
    el("h3", {}, "Starting facts"), list(s.starting_facts),
  ],
};

export async function showGenesis(view, worldId) {
  const head = el("div", { class: "panel stack" });
  const progress = el("div", { class: "panel" });
  const questions = el("div", {});
  const findings = el("div", {});
  const bibleBox = el("div", { class: "stack" });
  const start = el("div", { class: "panel stack" });
  view.append(el("div", { class: "page stack" }, head, progress, questions, findings, bibleBox, start));

  let lastStage = null;

  function renderProgress(genesis) {
    fill(progress, el("h2", {}, "Building the world"));
    const reached = STAGES.indexOf(genesis.stage);
    progress.append(
      el("div", { class: "row" }, STAGES.slice(0, -1).map((stage, index) =>
        tag(stage, genesis.stage === "done" || index < reached ? "good"
          : index === reached && genesis.running ? "warn" : ""))),
    );
    if (genesis.error) progress.append(el("p", { class: "tag bad" }, genesis.error));
    const recent = genesis.log.slice(-6);
    if (recent.length && genesis.running) {
      progress.append(el("ul", { class: "plain progress small" }, recent.map((entry) =>
        el("li", {}, el("span", { class: "stage" }, entry.stage), el("span", {}, entry.detail)))));
    }
  }

  function renderQuestions(genesis) {
    clear(questions);
    if (!genesis.questions.length) return;
    const answer = el("textarea", { "aria-label": "Your answer" });
    questions.append(el("div", { class: "panel stack" },
      el("h2", {}, "The premise needs pinning down"),
      list(genesis.questions),
      answer,
      action("Answer and continue", async () => {
        if (!answer.value.trim()) return;
        await api(`/worlds/${worldId}/genesis/answer`, { method: "POST", body: { text: answer.value } });
      }, { class: "primary" })));
  }

  function renderFindings(items) {
    clear(findings);
    if (!items.length) return;
    findings.append(el("div", { class: "panel" },
      el("h2", {}, "Reviewer's findings"),
      el("ul", { class: "plain" }, items.map((f) =>
        el("li", { class: "finding" },
          tag(f.blocking ? "must fix" : "minor", f.blocking ? "bad" : ""),
          tag(f.kind.replaceAll("_", " ")),
          el("span", { class: "muted small nowrap" }, f.section),
          el("span", {}, f.text))))));
  }

  async function renderBible() {
    const { bible, version } = await api(`/worlds/${worldId}/bible`);
    clear(bibleBox);
    if (bible.divergence) {
      bibleBox.append(el("div", { class: "panel stack" },
        el("h2", {}, "What changes"),
        el("p", {}, bible.divergence.summary),
        el("ul", { class: "plain" }, bible.divergence.consequences.map((c) =>
          el("li", {}, tag(`order ${c.order}`), " ", c.text,
            el("div", { class: "muted small" }, c.rationale))))));
    }
    for (const name of SECTION_ORDER) {
      const section = bible[name];
      const editor = el("textarea", { class: "mono", rows: 14, "aria-label": `${name} as JSON` });
      editor.value = JSON.stringify(section, null, 2);
      const editBox = el("div", { class: "stack", hidden: true },
        editor,
        el("div", { class: "row" },
          action("Save", async () => {
            let content;
            try {
              content = JSON.parse(editor.value);
            } catch (error) {
              throw new Error(`Not valid JSON: ${error.message}`);
            }
            const saved = await api(`/worlds/${worldId}/bible/${name}`, { method: "PUT", body: content });
            toast(`Saved as version ${saved.version}.`);
            await refresh();
          }, { class: "primary" }),
          el("span", { class: "muted small" }, "Saving keeps the previous version and re-checks the bible.")));
      bibleBox.append(el("details", { class: "section", open: name === "figures" },
        el("summary", {}, name[0].toUpperCase() + name.slice(1)),
        el("div", { class: "body stack" },
          RENDER[name](section),
          el("div", {}, el("button", { class: "quiet", type: "button",
            onclick: () => { editBox.hidden = !editBox.hidden; } }, "Edit as JSON")),
          editBox)));
    }
    const sources = await api(`/worlds/${worldId}/sources`);
    if (sources.length) {
      bibleBox.append(el("div", { class: "panel" },
        el("h2", {}, "Sources"),
        el("ul", { class: "plain" }, sources.map((s) =>
          el("li", {}, el("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.title),
            el("span", { class: "muted small" }, ` [${s.id}] ${s.notes.length} notes`))))));
    }
    return version;
  }

  async function refresh() {
    const world = await api(`/worlds/${worldId}`);
    setCrumbs([[world.premise.split("\n")[0].slice(0, 60), null]]);
    fill(head, 
      el("h1", {}, world.premise.split("\n")[0]),
      world.offline
        ? el("p", { class: "muted" },
            "Offline demo: this bible is a prepared example for the Berlin premise, not generated from your text.")
        : null);
    renderProgress(world.genesis);
    renderQuestions(world.genesis);
    renderFindings(world.genesis.findings);

    const ready = world.genesis.stage === "done" && !world.genesis.running;
    if (ready) await renderBible();
    else clear(bibleBox);

    clear(start);
    if (ready) {
      const blocking = world.genesis.findings.filter((f) => f.blocking).length;
      fill(start,
        el("h2", {}, "Run it"),
        blocking
          ? el("p", { class: "muted" },
              `${blocking} finding${blocking === 1 ? "" : "s"} marked must-fix. You can still start; seeding repairs what it can and tells you.`)
          : null,
        el("div", { class: "row" },
          action(world.branches.length ? "Start a fresh timeline" : "Start world", async () => {
            const seeded = await api(`/worlds/${worldId}/seed`, {
              method: "POST", body: { name: world.branches.length ? `run ${world.branches.length + 1}` : "main" },
            });
            if (seeded.notes.length) toast(`Seeded with ${seeded.notes.length} repair note(s).`);
            location.hash = `#/branch/${seeded.branch_id}`;
          }, { class: "primary" })),
        world.branches.length
          ? el("ul", { class: "plain" }, world.branches.map((b) =>
              el("li", { class: "row" },
                el("a", { href: `#/branch/${b.id}` }, b.name),
                el("span", { class: "muted small" }, `${b.head_seq} events`))))
          : null);
    }
    lastStage = `${world.genesis.stage}:${world.genesis.running}`;
  }

  await refresh();
  const stop = listen(`/ws/worlds/${worldId}`, (message) => {
    if (message.type !== "genesis") return;
    renderProgress(message.genesis);
    const stage = `${message.genesis.stage}:${message.genesis.running}`;
    // The full page is only rebuilt when the job stops or changes state.
    if (!message.genesis.running && stage !== lastStage) refresh().catch((e) => toast(e.message));
  });
  return stop;
}
