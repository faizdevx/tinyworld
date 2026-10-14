// Small DOM helpers. Everything the server sends is treated as text, never HTML:
// world content is written by a model and by fetched web pages.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key in node && key !== "list") node[key] = value;
    else node.setAttribute(key, value);
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function tag(text, tone = "") {
  return el("span", { class: `tag ${tone}` }, text);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function when(iso, withTime = true) {
  // Parsed by hand: simulated dates can be centuries from the browser's clock.
  const match = /^(-?\d+)-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(iso || "");
  if (!match) return iso || "";
  const [, year, month, day, hour, minute] = match;
  const date = `${Number(day)} ${MONTHS[Number(month) - 1]} ${Number(year)}`;
  return withTime ? `${date}, ${hour}:${minute}` : date;
}

export function money(amount) {
  if (amount === null || amount === undefined) return "–";
  if (amount > 0 && amount < 0.01) return "<$0.01";
  return `$${amount.toFixed(2)}`;
}

export function shortId(id) {
  const index = (id || "").indexOf(":");
  return index === -1 ? id : id.slice(index + 1).replaceAll("_", " ");
}

let toastTimer = null;
export function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 3500);
}

// Runs an async action from a button, disabling it meanwhile and reporting failure.
export function action(label, run, attrs = {}) {
  const button = el("button", { ...attrs, type: "button" }, label);
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await run(button);
    } catch (error) {
      toast(error.message || String(error));
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

export function setCrumbs(parts) {
  const nav = clear(document.getElementById("crumbs"));
  for (const [label, href] of parts) {
    nav.append(el("span", {}, href ? el("a", { href }, label) : label));
  }
}

export function download(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const link = el("a", { href: URL.createObjectURL(blob), download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
