"""Built-in application adapters. Add a registry entry to support a new target."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Callable

from .integrations import (firefox_profiles, firefox_writes, read_text,
                           rofi_text, sioyek_text, zathura_text)
from .qt6ct import scheme_text, settings_text
from .clementine import clementine_text
from .pages import blank_page_html
from .qutebrowser import blank_page_config
from .terminals import (foot_config, foot_theme, ghostty_config, ghostty_theme,
                        kitty_config, kitty_theme, wezterm_config, wezterm_scheme)
from .theme import shell_exports


@dataclass(frozen=True)
class Target:
    name: str
    plan: Callable
    commands: tuple = ()
    installed_paths: Callable = lambda config: ()
    default: bool = False
    qt6ct_covered: bool = False

    def unavailable_reason(self, config):
        commands = self.commands + tuple(config["target_commands"].get(self.name, ()))
        for command in commands:
            candidate = Path(os.path.expandvars(command)).expanduser()
            if ((candidate.is_absolute() or "/" in command) and candidate.is_file()
                    and os.access(candidate, os.X_OK)):
                return None
            if "/" not in command and shutil.which(command):
                return None
        if any(path.is_file() for path in self.installed_paths(config)):
            return None
        return "not installed"


def alacritty_plan(theme, config):
    root = config["alacritty"]
    palette = root / "chthm-colors.toml"
    # Keep the established import-file shape for older Qtile/qutebrowser loaders.
    selection = "general.import = [" + json.dumps(str(palette), ensure_ascii=False) + "]\n"
    return [(palette, theme.palette_toml(), True),
            (root / "theme.toml", selection, True)], []


def ghostty_plan(theme, config):
    palette, target = config["ghostty_theme"], config["ghostty_config"]
    return [(palette, ghostty_theme(theme), True),
            (target, ghostty_config(read_text(target), palette), True)], [
        "Ghostty: press Ctrl+Shift+Comma to reload the configuration, or restart it"]


def kitty_plan(theme, config):
    palette, target = config["kitty_theme"], config["kitty_config"]
    return [(palette, kitty_theme(theme), True),
            (target, kitty_config(read_text(target), palette), True)], [
        "kitty: colors update automatically unless config file watching is disabled; Ctrl+Shift+F5 reloads manually"]


def wezterm_plan(theme, config):
    palette, target = config["wezterm_scheme"], config["wezterm_config"]
    # Validate the user's Lua before returning any writes, so an unsupported
    # config shape cannot leave a generated palette behind.
    updated = wezterm_config(read_text(target), palette)
    return [(palette, wezterm_scheme(theme), True), (target, updated, True)], [
        "WezTerm: the generated scheme is watched for automatic reload; Ctrl+Shift+R reloads manually"]


def foot_plan(theme, config):
    palette, target = config["foot_theme"], config["foot_config"]
    return [(palette, foot_theme(theme), True),
            (target, foot_config(read_text(target), palette), True)], [
        "foot: restart open terminals to load the updated colors"]


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


def librewolf_plan(theme, config):
    profiles = firefox_profiles(config["librewolf_roots"], config["librewolf_profiles"], "LibreWolf")
    writes, notices = [], []
    for profile in profiles:
        writes.extend(firefox_writes(profile, theme.exports, "librewolf"))
        notices.append(f"LibreWolf profile: {profile} (themed home page updated; restart LibreWolf to apply settings)")
    if not profiles:
        notices.append("Skipping LibreWolf: no profile found or selected; use --librewolf-profile PATH")
    return writes, notices


def clementine_plan(theme, config):
    target = config["clementine"]
    return [(target, clementine_text(read_text(target), theme.exports), True)], [
        "Clementine: compatibility colors updated; this app overrides the platform palette (restart to apply)"]


def qt6ct_plan(theme, config):
    palette = scheme_text(theme)
    settings = settings_text(read_text(config["qt6ct"]), config["qt6ct_palette"], palette)
    return [(config["qt6ct_palette"], palette, True),
            (config["qt6ct"], settings, True),
            (config["config_root"] / "environment.d/60-chthm-qt6ct.conf",
             "QT_QPA_PLATFORMTHEME=qt6ct\n", True)], [
        "qt6ct: shared Qt 6 palette updated; Qt apps must inherit QT_QPA_PLATFORMTHEME=qt6ct"]


def qutebrowser_plan(theme, config):
    page, settings = config["qutebrowser_page"], config["qutebrowser"]
    colors = theme.colors["primary"]
    updated = blank_page_config(read_text(settings), page, colors["background"])
    return [(page, blank_page_html(colors["background"], colors["foreground"]), True),
            (settings, updated, True)], ["qutebrowser: native website appearance and themed blank page updated"]


def shared_palette_plan(theme, config):
    # Qtile reads the shared snapshot.
    return [], []


def qt6_platform_plan(theme, config):
    """Qt 6 applications use the shared qt6ct target; no app file is needed."""
    return [], []


def flatpak_desktop(application_id):
    filename = application_id + ".desktop"
    return lambda config: (
        Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
        / "flatpak/exports/share/applications" / filename,
        Path("/var/lib/flatpak/exports/share/applications") / filename,
    )


TARGETS = {target.name: target for target in (
    Target("alacritty", alacritty_plan, ("alacritty",),
           default=True),
    Target("ghostty", ghostty_plan, ("ghostty",), default=True),
    Target("kitty", kitty_plan, ("kitty",), default=True),
    Target("wezterm", wezterm_plan, ("wezterm",), default=True),
    Target("foot", foot_plan, ("foot", "footclient"), default=True),
    Target("zathura", zathura_plan, ("zathura",), default=True),
    Target("rofi", rofi_plan, ("rofi",), default=True),
    Target("firefox", firefox_plan, ("firefox", "firefox-esr"),
           installed_paths=flatpak_desktop("org.mozilla.firefox"), default=True),
    Target("librewolf", librewolf_plan, ("librewolf",),
           installed_paths=flatpak_desktop("io.gitlab.librewolf-community"), default=True),
    Target("sioyek", sioyek_plan, ("sioyek",), default=True, qt6ct_covered=True),
    Target("clementine", clementine_plan, ("clementine",), default=True, qt6ct_covered=True),
    Target("pcmanfm-qt", qt6_platform_plan, ("pcmanfm-qt",), default=True, qt6ct_covered=True),
    Target("qt6ct", qt6ct_plan, ("qt6ct",)),
    Target("qutebrowser", qutebrowser_plan, ("qutebrowser",),
           installed_paths=flatpak_desktop("org.qutebrowser.qutebrowser"),
           default=True, qt6ct_covered=True),
    Target("qtile", shared_palette_plan, ("qtile",), default=True),
)}

DEFAULT_TARGETS = frozenset(name for name, target in TARGETS.items() if target.default)
