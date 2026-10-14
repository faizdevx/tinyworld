import { api } from "./api.js";
import { clear, el, toast } from "./ui.js";
import { showHome } from "./home.js";
import { showGenesis } from "./genesis.js";
import { showWorld } from "./world.js";
import { showHistory } from "./history.js";

const view = document.getElementById("view");
let teardown = null;

const routes = [
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

async function showMode() {
  try {
    const status = await api("/status");
    document.getElementById("mode").textContent = status.offline
      ? "offline demo"
      : "";
  } catch (error) {
    toast(error.message);
  }
}

window.addEventListener("hashchange", route);
showMode();
route();
