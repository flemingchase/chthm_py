"""Read chthm's data-only snapshot; no installed chthm package is required."""

from copy import deepcopy
import logging
import os
from pathlib import Path
import re
import tomllib

FALLBACK = {
    "colors": {
        "primary": {"background": "#221a0f", "foreground": "#d3af86"},
        "normal": dict(zip(("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"),
                           ("#221a0f", "#c87e5a", "#879a6b", "#e4b581", "#5d90cd", "#c792ea", "#6bbab2", "#d3af86"))),
    },
    "roles": {"accent": "#5d90cd", "error": "#c87e5a", "warning": "#e4b581", "success": "#879a6b"},
}
FALLBACK["colors"]["bright"] = FALLBACK["colors"]["normal"].copy()


def _path(value):
    return Path(os.path.expandvars(str(value))).expanduser().absolute()


def current_palette_path():
    config_root = _path(os.environ.get("XDG_CONFIG_HOME") or "~/.config")
    settings = config_root / "chthm/config.toml"
    if settings.is_file():
        with settings.open("rb") as stream:
            config = tomllib.load(stream)
        if "state_file" in config:
            if not isinstance(config["state_file"], str):
                raise ValueError("state_file must be a path string")
            return _path(config["state_file"])
    state_root = _path(os.environ.get("XDG_STATE_HOME") or "~/.local/state")
    return state_root / "chthm/current.toml"


def load_palette(state_file=None):
    """Always return a usable palette, including on first startup or bad data."""
    try:
        filename = _path(state_file) if state_file is not None else current_palette_path()
        with filename.open("rb") as stream:
            data = tomllib.load(stream)
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("unsupported palette schema")
        colors = data["colors"]
        primary = colors["primary"]

        def color(value):
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError("invalid palette color")
            return value

        background = color(primary["background"])
        foreground = color(primary["foreground"])
        for group in ("primary", "normal", "bright"):
            table = colors.setdefault(group, {})
            if not isinstance(table, dict):
                raise ValueError(f"invalid {group} table")
            for value in table.values():
                color(value)
        for name in FALLBACK["colors"]["normal"]:
            colors["normal"].setdefault(name, background if name == "black" else foreground)
            colors["bright"].setdefault(name, colors["normal"][name])
        roles = data.setdefault("roles", {})
        if not isinstance(roles, dict):
            raise ValueError("invalid roles table")
        for value in roles.values():
            color(value)
        for role, normal in {"accent": "blue", "error": "red", "warning": "yellow", "success": "green"}.items():
            roles.setdefault(role, colors["normal"][normal])
        return data
    except FileNotFoundError:
        return deepcopy(FALLBACK)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        logging.getLogger("libqtile").warning("Cannot load chthm palette; using fallback: %s", error)
        return deepcopy(FALLBACK)
