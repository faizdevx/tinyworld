import { api } from "./api.js";
import { clear, el, fill, toast } from "./ui.js";
import { showHome } from "./home.js";
import { showGenesis } from "./genesis.js";
import { showWorld } from "./world.js";
import { showHistory } from "./history.js";
import { showStudio } from "./studio.js";
import { showTown } from "./town.js";

const view = document.getElementById("view");
let teardown = null;

const routes = [
  [/^#\/studio\/([^/]+)$/, (m) => showStudio(view, m[1])],
  [/^#\/town\/([^/]+)$/, (m) => showTown(view, m[1])],
  [/^#\/world\/([^/]+)$/, (m) => showGenesis(view, m[1])],
  [/^#\/branch\/([^/]+)\/history$/, (m) => showHistory(view, m[1])],
  [/^#\/branch\/([^/]+)$/, (m) => showWorld(view, m[1])],
  [/^#?\/?$/, () => showHome(view)],
];

async function route() {
  if (teardown) teardown();
  teardown = null;
  clear(view);
  const hash = location.hash || "#/";
  for (const [pattern, show] of routes) {
    const match = pattern.exec(hash);
    if (!match) continue;
    try {
      teardown = (await show(match)) || null;
    } catch (error) {
      clear(view).append(
        el("div", { class: "page stack" },
          el("h1", {}, "That could not be opened"),
          el("p", { class: "muted" }, error.message || String(error)),
          el("a", { href: "#/" }, "Back to worlds")),
      );
    }
    return;
  }
  location.hash = "#/";
}

// A key typed here is held by the server in memory only, never written to disk.
function keyForm(box) {
  const provider = el("select", { "aria-label": "Provider" },
    el("option", { value: "openrouter" }, "OpenRouter"),
    el("option", { value: "gemini" }, "Gemini"),
    el("option", { value: "anthropic" }, "Anthropic"),
    el("option", { value: "local" }, "Local model (open weights)"));
  const key = el("input", {
    type: "password", placeholder: "API key", autocomplete: "off",
    "aria-label": "API key",
  });
  // An open-weight model runs on a server you control; it needs an address,
  // and often no key at all.
  const address = el("input", {
    type: "text", placeholder: "http://localhost:11434/v1", autocomplete: "off",
    "aria-label": "Model server address", hidden: true,
  });
  provider.addEventListener("change", () => {
    const local = provider.value === "local";
    address.hidden = !local;
    key.placeholder = local ? "API key (optional)" : "API key";
  });
  const go = el("button", { class: "primary", type: "button" }, "Connect");
  const note = el("span", { class: "muted small" }, "kept in memory, never saved");
  go.addEventListener("click", async () => {
    go.disabled = true;
    try {
      await api("/connect", {
        method: "POST",
        body: { provider: provider.value, key: key.value, base_url: address.value || null },
      });
      toast("Connected. New worlds are built by the model.");
      key.value = "";
      location.reload();
    } catch (error) {
      toast(error.message);
      go.disabled = false;
    }
  });
  fill(box, provider, address, key, go, note);
}

async function showMode() {
  const box = document.getElementById("mode");
  try {
    const status = await api("/status");
    if (!status.offline) {
      fill(box);
      return;
    }
    const open = el("button", { class: "link", type: "button" }, "Add a model key");
    open.addEventListener("click", () => keyForm(box));
    fill(box, "offline demo \u00b7 ", open);
  } catch (error) {
    toast(error.message);
  }
}

window.addEventListener("hashchange", route);
showMode();
route();
