"""Start TinyWorld on your own open-weight model, and open it in the browser.

    python run_local.py

What it does:
1. looks for a model server at LOCAL_BASE_URL (default http://127.0.0.1:8081/v1);
2. if there is none and a llama.cpp server and a model file are found, starts one;
3. runs the website on http://127.0.0.1:8000 with the local model as the provider;
4. opens the browser. Type a scenario; the team builds it; the town opens.

llama.cpp's ``llama-server`` is found on PATH (or LLAMA_SERVER); the model file comes from --model or
LLAMA_MODEL (any instruct GGUF, for example Qwen2.5-7B-Instruct-Q4_K_M.gguf).
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

import shutil

DEFAULT_SERVER = shutil.which("llama-server") or "llama-server"


def up(base: str) -> bool:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/models", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def start_model(server: str, model: str, port: int) -> subprocess.Popen | None:
    if not (shutil.which(server) or Path(server).exists()) or not (model and Path(model).exists()):
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
    parser.add_argument("--model", help="path to a .gguf model file (or set LLAMA_MODEL)")
    options = parser.parse_args()

    child = None
    if not options.offline:
        base = os.environ.setdefault("LOCAL_BASE_URL", f"http://127.0.0.1:{options.model_port}/v1")
        if not up(base):
            child = start_model(os.environ.get("LLAMA_SERVER", DEFAULT_SERVER), options.model or os.environ.get("LLAMA_MODEL", ""), options.model_port)
            if child is None:
                print(f"No model server at {base}, and llama-server or a model file was not found.\n"
                      "  1. install llama.cpp (https://github.com/ggml-org/llama.cpp) and download a .gguf instruct model\n"
                      "  2. run: python run_local.py --model path/to/model.gguf\n"
                      "  or start any OpenAI-compatible server and set LOCAL_BASE_URL,\n"
                      "  or run with --offline for the scripted stand-in (no model, shallow stories).")
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
