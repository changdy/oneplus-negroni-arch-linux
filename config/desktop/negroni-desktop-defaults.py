#!/usr/bin/env python3
"""Apply the confirmed internal-screen rotation policy once per desktop user."""
import json
import os
from pathlib import Path
import subprocess


def ensure_quick_settings(home):
    state_dir = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "negroni"
    state = state_dir / "quicksettings-v3"
    if state.exists():
        return

    def read(key):
        result = subprocess.run(["kreadconfig6", "--file", "plasmamobilerc", "--group", "QuickSettings", "--key", key],
                                capture_output=True, text=True, check=True, timeout=10)
        return [item for item in result.stdout.strip().split(",") if item]

    enabled = read("enabledQuickSettings")
    disabled = set(read("disabledQuickSettings"))
    if not enabled:
        enabled = sorted(path.name for path in Path("/usr/share/plasma/quicksettings").iterdir()
                         if path.name not in disabled and (path / "metadata.json").exists())

    additions = [("org.negroni.quicksetting.krdp", "org.negroni.quicksetting.gps")]
    if not (state_dir / "quicksettings-v2").exists():
        additions.insert(0, ("org.negroni.quicksetting.gps", "org.negroni.quicksetting.nfc"))
        if not (state_dir / "quicksettings-v1").exists():
            additions = [("org.negroni.quicksetting.nfc", "org.kde.plasma.quicksetting.bluetooth"),
                         ("org.negroni.quicksetting.gyro", "org.kde.plasma.quicksetting.screenrotation")] + additions
    for setting, predecessor in additions:
        if setting not in enabled and setting not in disabled:
            position = enabled.index(predecessor) + 1 if predecessor in enabled else len(enabled)
            enabled.insert(position, setting)

    subprocess.run(["kwriteconfig6", "--file", "plasmamobilerc", "--group", "QuickSettings",
                    "--key", "enabledQuickSettings", "--notify", ",".join(enabled)], check=True, timeout=10)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("registered KRDP quick setting\n")


def main():
    home = Path.home()
    ensure_quick_settings(home)
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
