"""Built-in application adapters. Add a registry entry to support a new target."""

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Callable

from .integrations import (firefox_profiles, firefox_writes, read_text,
                           rofi_text, sioyek_text, zathura_text)
from .qt6ct import scheme_text, settings_text
from .clementine import clementine_text
from .pages import blank_page_html
from .qutebrowser import blank_page_config
from .theme import shell_exports


@dataclass(frozen=True)
class Target:
    name: str
    plan: Callable
    commands: tuple = ()
    configured_paths: Callable = lambda config: ()

    def unavailable_reason(self, config):
        if any(path.is_file() for path in self.configured_paths(config)):
            return None
        if any(shutil.which(command) for command in self.commands):
            return None
        return "not installed or configured"


def alacritty_plan(theme, config):
    root = config["alacritty"]
    palette = root / "chthm-colors.toml"
    # Keep the established import-file shape for older Qtile/qutebrowser loaders.
    selection = "general.import = [" + json.dumps(str(palette), ensure_ascii=False) + "]\n"
    return [(palette, theme.palette_toml(), True),
            (root / "theme.toml", selection, True)], []


def zathura_plan(theme, config):
    target = config["zathura"]
    return [(target, zathura_text(read_text(target), theme.exports), True)], []


def rofi_plan(theme, config):
    target, values = config["rofi_config"], theme.exports
    return [(target, rofi_text(read_text(target), values), True),
            (config["rofi"], shell_exports({key: values[key] for key in
                ("CHTHM_BACKGROUND", "CHTHM_FOREGROUND")}), False)], []


def sioyek_plan(theme, config):
    return [(config["sioyek"], sioyek_text(read_text(config["sioyek"]), theme.exports), True)], [
        "Sioyek: restart to load interface colors; PDF recoloring settings were preserved"]


def firefox_plan(theme, config):
    profiles = firefox_profiles(config["firefox_roots"], config["firefox_profiles"])
    writes, notices = [], []
    for profile in profiles:
        writes.extend(firefox_writes(profile, theme.exports))
        notices.append(f"Firefox profile: {profile} (themed home page updated; restart Firefox to apply settings)")
    if not profiles:
        notices.append("Skipping Firefox: no profile found or selected; use --firefox-profile PATH")
    return writes, notices


def clementine_plan(theme, config):
    target = config["clementine"]
    return [(target, clementine_text(read_text(target), theme.exports), True)], [
        "Clementine: compatibility colors updated; this app overrides the platform palette (restart to apply)"]


def qt6ct_plan(theme, config):
    palette = scheme_text(theme)
    settings = settings_text(read_text(config["qt6ct"]), config["qt6ct_palette"], palette)
    return [(config["qt6ct_palette"], palette, True),
            (config["qt6ct"], settings, True)], [
        "qt6ct: shared Qt 6 palette updated; Qt apps must inherit QT_QPA_PLATFORMTHEME=qt6ct"]


def qutebrowser_plan(theme, config):
    page, settings = config["qutebrowser_page"], config["qutebrowser"]
    colors = theme.colors["primary"]
    updated = blank_page_config(read_text(settings), page)
    return [(page, blank_page_html(colors["background"], colors["foreground"]), True),
            (settings, updated, True)], ["qutebrowser: themed blank page updated"]


def shared_palette_plan(theme, config):
    # Qtile reads the shared snapshot.
    return [], []


TARGETS = {target.name: target for target in (
    Target("alacritty", alacritty_plan, ("alacritty",),
           lambda c: (c["alacritty"] / "alacritty.toml", c["alacritty"] / "theme.toml")),
    Target("zathura", zathura_plan, ("zathura",), lambda c: (c["zathura"],)),
    Target("rofi", rofi_plan, ("rofi",), lambda c: (c["rofi_config"],)),
    Target("firefox", firefox_plan, ("firefox", "firefox-esr"),
           lambda c: tuple(root / "profiles.ini" for root in c["firefox_roots"]) +
                     tuple(Path(profile) / "prefs.js" for profile in c["firefox_profiles"] or ())),
    Target("sioyek", sioyek_plan, ("sioyek",), lambda c: (c["sioyek"],)),
    Target("clementine", clementine_plan, ("clementine",), lambda c: (c["clementine"],)),
    Target("qt6ct", qt6ct_plan, ("qt6ct",), lambda c: (c["qt6ct"],)),
    Target("qutebrowser", qutebrowser_plan, ("qutebrowser",), lambda c: (c["qutebrowser"],)),
    Target("qtile", shared_palette_plan, ("qtile",), lambda c: (c["config_root"] / "qtile/config.py",)),
)}
