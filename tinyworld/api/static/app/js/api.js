export async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && payload.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ")
      : detail || response.statusText;
    throw new Error(message);
  }
  return payload;
}

// A socket that reconnects on its own. Returns a function that closes it for good.
export function listen(path, onMessage, onOpen) {
  let socket = null;
  let closed = false;
  let retry = 500;

  function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${location.host}${path}`);
    socket.onopen = () => {
      retry = 500;
      if (onOpen) onOpen();
    };
    socket.onmessage = (event) => onMessage(JSON.parse(event.data));
    socket.onclose = () => {
      if (closed) return;
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 8000);
    };
  }

  connect();
  return () => {
    closed = true;
    if (socket) socket.close();
  };
}
