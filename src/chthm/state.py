"""Selected palette persistence, independent of every application target."""

import os
from pathlib import Path

from .theme import Theme


def default_state_file():
    root = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(os.path.expandvars(root)).expanduser().absolute() / "chthm/current.toml"


def current_theme(config):
    state = config["state_file"]
    if state.exists():
        return Theme.from_snapshot(state)
    # Only the app-independent collection is used before the first selection.
    name = config["default"]
    candidate = Path(os.path.expandvars(name)).expanduser()
    if candidate.is_file():
        return Theme.load(candidate)
    filename = name if name.endswith(".toml") else name + ".toml"
    return Theme.load(config["themes"] / filename)
