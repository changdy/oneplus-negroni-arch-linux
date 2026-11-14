#!/usr/bin/env python3
"""Apply the confirmed internal-screen rotation policy once per desktop user."""
import json
import os
from pathlib import Path
import subprocess


def main():
    home = Path.home()
    state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "negroni/rotation-v1"
    if state.exists():
        return
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "kwinoutputconfig.json"
    # Retain an explicit user choice to lock rotation. Do not copy device output IDs.
    if config.exists():
        data = json.loads(config.read_text())

        def locked(value):
            if isinstance(value, dict):
                return value.get("autoRotation") == "Never" or any(locked(v) for v in value.values())
            return isinstance(value, list) and any(locked(v) for v in value)

        if locked(data):
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text("kept user's rotation lock\n")
            return
    result = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, check=True, timeout=15)
    outputs = json.loads(result.stdout)["outputs"]
    internal = [o for o in outputs if o.get("connected") and o.get("name", "").startswith("DSI-")]
    if not internal:
        return  # Retry at the next login when KScreen is available.
    for output in internal:
        subprocess.run(["kscreen-doctor", f"output.{output['id']}.autoRotatePolicy.always"],
                       check=True, timeout=15)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("internal display autoRotatePolicy=always\n")


if __name__ == "__main__":
    main()
