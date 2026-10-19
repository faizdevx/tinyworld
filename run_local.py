"""Start TinyWorld on your own open-weight model, and open it in the browser.

    python run_local.py

What it does:
1. looks for a model server at LOCAL_BASE_URL (default http://127.0.0.1:8081/v1);
2. if there is none and a llama.cpp server and a model file are found, starts one;
3. runs the website on http://127.0.0.1:8000 with the local model as the provider;
4. opens the browser. Type a scenario; the team builds it; the town opens.

Paths are read from LLAMA_SERVER and LLAMA_MODEL, else the usual places on this machine.
Use --offline to run without any model (the scripted stand-in), --port to change the site's port.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_SERVER = "D:/DATA_ANALYSIS/llama_cpp/llama-server.exe"
DEFAULT_MODEL = "D:/DATA_ANALYSIS/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"


def up(base: str) -> bool:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/models", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def start_model(server: str, model: str, port: int) -> subprocess.Popen | None:
    if not (Path(server).exists() and Path(model).exists()):
        return None
    print(f"Starting the model server on port {port} (first load takes a minute)...")
    return subprocess.Popen(
        [server, "-m", model, "-ngl", "16", "-c", "12288", "-np", "1", "--cache-type-k", "q8_0",
         "--cache-type-v", "q8_0", "-fa", "on", "--jinja", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model-port", type=int, default=8081)
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()

    child = None
    if not options.offline:
        base = os.environ.setdefault("LOCAL_BASE_URL", f"http://127.0.0.1:{options.model_port}/v1")
        if not up(base):
            child = start_model(os.environ.get("LLAMA_SERVER", DEFAULT_SERVER), os.environ.get("LLAMA_MODEL", DEFAULT_MODEL), options.model_port)
            if child is None:
                print(f"No model server at {base} and no llama.cpp found. Start one, or set LLAMA_SERVER and LLAMA_MODEL,\n"
                      "or run with --offline to use the scripted stand-in.")
                sys.exit(2)
            deadline = time.time() + 300
            while time.time() < deadline and not up(base):
                time.sleep(2)
            if not up(base):
                print("The model server did not come up in five minutes.")
                child.terminate()
                sys.exit(2)
        os.environ["TINYWORLD_PROVIDER"] = "local"
        os.environ.setdefault("LOCAL_CONCURRENCY", "1")
        os.environ.setdefault("LOCAL_MAX_CONCURRENCY", "1")
        print(f"Model ready at {base}.")
    else:
        os.environ.pop("TINYWORLD_PROVIDER", None)

    import uvicorn

    from tinyworld.api.app import serve

    url = f"http://127.0.0.1:{options.port}/app/"
    print(f"TinyWorld is at {url}")
    if not options.no_browser:
        webbrowser.open(url)
    try:
        uvicorn.run(serve(), host="127.0.0.1", port=options.port, log_level="warning")
    finally:
        if child is not None:
            child.terminate()


if __name__ == "__main__":
    main()
