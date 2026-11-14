"""Portable theme switching, with no runtime dependencies beyond Python 3.11+."""

import argparse
import configparser
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from .state import current_theme, default_state_file
from .targets import TARGETS
from .theme import Theme, read_toml, shell_exports

DEFAULT_APPS = set(TARGETS)
APPS = DEFAULT_APPS


def path(value):
    return Path(os.path.expandvars(str(value))).expanduser().absolute()


def settings(args):
    root = path(os.environ.get("XDG_CONFIG_HOME") or "~/.config")
    config_file = path(args.config) if args.config else root / "chthm/config.toml"
    config = read_toml(config_file) if args.config or config_file.exists() else {}
    allowed = {"alacritty_dir", "themes_dir", "zathura_config", "rofi_env",
               "rofi_config", "firefox_root", "firefox_profiles", "clementine_config", "qt6ct_config",
               "qt6ct_palette", "sioyek_config",
               "default_theme", "state_file", "targets", "reload", "qutebrowser_config", "qutebrowser_page"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"Unknown configuration options: {', '.join(sorted(unknown))}")
    for key in allowed - {"targets", "reload", "firefox_profiles"}:
        if key in config and not isinstance(config[key], str):
            raise ValueError(f"{key} must be a string")
    if "reload" in config and not isinstance(config["reload"], bool):
        raise ValueError("reload must be true or false")
    alacritty = path(args.alacritty_dir or config.get("alacritty_dir", root / "alacritty"))
    targets = args.targets.split(",") if args.targets is not None else config.get("targets", sorted(DEFAULT_APPS))
    if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
        raise ValueError("targets must be an array of application names")
    targets = {t.strip() for t in targets}
    if targets - APPS:
        raise ValueError(f"Supported targets: {', '.join(sorted(APPS))}")
    profiles = args.firefox_profile if args.firefox_profile is not None else config.get("firefox_profiles")
    if profiles is not None and (not isinstance(profiles, list) or
                                 not all(isinstance(p, str) and p for p in profiles)):
        raise ValueError("firefox_profiles must be an array of profile directory paths")
    firefox_root = args.firefox_root or config.get("firefox_root")
    firefox_roots = [path(firefox_root)] if firefox_root else list(dict.fromkeys([
        root / "mozilla/firefox", Path.home() / ".mozilla/firefox",
        Path.home() / ".var/app/org.mozilla.firefox/.mozilla/firefox",
        Path.home() / "snap/firefox/common/.mozilla/firefox",
    ]))
    forced = set(args.targets.split(",")) if args.targets is not None else set()
    forced = {name.strip() for name in forced}
    destinations = {
        "alacritty": ("alacritty_dir",), "zathura": ("zathura_config",),
        "rofi": ("rofi_config", "rofi_env"), "clementine": ("clementine_config",), "qt6ct": ("qt6ct_config", "qt6ct_palette"),
        "sioyek": ("sioyek_config",),
        "qutebrowser": ("qutebrowser_config", "qutebrowser_page"),
        "firefox": ("firefox_root", "firefox_profile"),
    }
    for app, keys in destinations.items():
        if any(getattr(args, key, None) is not None or key in config for key in keys):
            forced.add(app)
    if "firefox_profiles" in config:
        forced.add("firefox")
    return {
        "alacritty": alacritty,
        "themes": path(args.themes_dir or config.get("themes_dir",
            path(os.environ.get("XDG_DATA_HOME") or "~/.local/share") / "chthm/themes")),
        "state_file": path(args.state_file or config.get("state_file", default_state_file())),
        "zathura": path(args.zathura_config or config.get("zathura_config", root / "zathura/zathurarc")),
        "rofi": path(args.rofi_env or config.get("rofi_env", root / "rofi/theme.env")),
        "rofi_config": path(args.rofi_config or config.get("rofi_config", root / "rofi/config.rasi")),
        "firefox_roots": firefox_roots,
        "firefox_profiles": [path(p) for p in profiles] if profiles is not None else None,
        "clementine": path(args.clementine_config or config.get("clementine_config", root / "Clementine/Clementine.conf")),
        "qt6ct": path(args.qt6ct_config or config.get("qt6ct_config", root / "qt6ct/qt6ct.conf")),
        "qt6ct_palette": path(args.qt6ct_palette or config.get("qt6ct_palette", root / "qt6ct/colors/chthm.conf")),
        "sioyek": path(args.sioyek_config or config.get("sioyek_config", root / "sioyek/prefs_user.config")),
        "qutebrowser": path(args.qutebrowser_config or config.get("qutebrowser_config", root / "qutebrowser/config.py")),
        "qutebrowser_page": path(args.qutebrowser_page or config.get("qutebrowser_page",
            path(os.environ.get("XDG_DATA_HOME") or "~/.local/share") / "chthm/qutebrowser/blank.html")),
        "default": config.get("default_theme", "kimbie_dark"),
        "targets": targets,
        "forced_targets": forced,
        "config_root": root,
        "reload": config.get("reload", True) and not args.no_reload,
    }


def unavailable_reason(target, config):
    """Probe local files/commands only; never start an app to detect it."""
    return TARGETS[target].unavailable_reason(config)


def theme_path(name, config):
    candidate = path(name)
    if candidate.is_file():
        return candidate
    # Names address the configured collection; explicit paths must exist.
    if "/" in name or name.startswith("~"):
        raise ValueError(f"Theme file not found: {name}")
    return config["themes"] / (name if name.endswith(".toml") else name + ".toml")


def palette(filename):
    """Compatibility API for scripts which need shell palette values."""
    return Theme.load(filename).exports


def exports(values):
    return shell_exports(values)


def atomic_write(filename, text, backup=False):
    # Resolve symlinks so dotfile-manager links survive the replacement.
    filename = filename.resolve()
    if filename.exists() and filename.read_text(encoding="utf-8") == text:
        return
    filename.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=filename.name + ".tmp.", dir=filename.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if filename.exists():
            shutil.copymode(filename, temporary)
            if backup:
                shutil.copy2(filename, str(filename) + ".bak")
        os.replace(temporary, filename)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def reload_apps(values, qtile_enabled=True, qutebrowser_enabled=True, qt6ct_enabled=False):
    env = os.environ | values
    if qt6ct_enabled and shutil.which("qt6ct"):
        env["QT_QPA_PLATFORMTHEME"] = "qt6ct"
    if qtile_enabled and shutil.which("qtile"):
        try:
            result = subprocess.run(["qtile", "cmd-obj", "-o", "cmd", "-f", "reload_config"],
                                    env=env, capture_output=True, timeout=15)
            if result.returncode:
                print("Warning: Qtile reload failed.", file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"Warning: Qtile reload failed: {error}", file=sys.stderr)
    if qutebrowser_enabled and shutil.which("qutebrowser") and shutil.which("pgrep"):
        try:
            running = subprocess.run(["pgrep", "-x", "qutebrowser"], capture_output=True, timeout=5)
            if running.returncode == 0:
                subprocess.Popen(["qutebrowser", ":restart"], env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"Warning: qutebrowser restart failed: {error}", file=sys.stderr)


def theme_listing(names, current=None):
    """Readable, alphabetized columns, with the saved theme marked."""
    if not names:
        return "Available themes (0)\n\nNo .toml theme files found."
    width = shutil.get_terminal_size(fallback=(80, 24)).columns
    cells = [("* " if name == current else "  ") + name for name in names]
    cell_width = max(map(len, cells)) + 2
    columns = max(1, min(len(cells), (width + 2) // cell_width))
    rows = (len(cells) + columns - 1) // columns
    lines = [f"Available themes ({len(names)})", ""]
    for row in range(rows):
        lines.append("".join(cells[i].ljust(cell_width)
                             for i in range(row, len(cells), rows)).rstrip())
    lines.append("")
    if current in names:
        lines.append("* Current theme")
    lines.append("Apply a theme: chthm <name>")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("theme", nargs="?", help="Theme name, TOML path, 'list', or 'exports'")
    parser.add_argument("--version", action="version", version="chthm 2.0.0")
    parser.add_argument("--config", help="Configuration TOML file")
    parser.add_argument("--themes-dir", help="Directory of independent TOML palettes")
    parser.add_argument("--state-file", help="Shared current palette snapshot destination")
    parser.add_argument("--alacritty-dir")
    parser.add_argument("--zathura-config")
    parser.add_argument("--rofi-env")
    parser.add_argument("--rofi-config", help="Rofi config.rasi to edit directly")
    parser.add_argument("--firefox-root", help="Firefox directory containing profiles.ini")
    parser.add_argument("--firefox-profile", action="append", help="Profile directory; repeat to update multiple profiles")
    parser.add_argument("--clementine-config", help="Clementine palette compatibility settings")
    parser.add_argument("--qt6ct-config", help="qt6ct configuration destination")
    parser.add_argument("--qt6ct-palette", help="Shared Qt 6 palette destination")
    parser.add_argument("--sioyek-config", help="Sioyek prefs_user.config destination (interface colors only)")
    parser.add_argument("--qutebrowser-config", help="qutebrowser config.py destination")
    parser.add_argument("--qutebrowser-page", help="Generated theme-colored blank HTML page")
    parser.add_argument("--targets", help="Comma-separated targets: " + ",".join(sorted(APPS)))
    parser.add_argument("--no-reload", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writes or reloads")
    parser.add_argument("--shell", action="store_true", help="Emit safely quoted shell commands")
    parser.add_argument("--plain", action="store_true", help="With list, print only theme names, one per line")
    args = parser.parse_args(argv)
    try:
        config = settings(args)
        if args.theme == "list":
            if not config["themes"].is_dir():
                raise ValueError(f'Themes directory not found: {config["themes"]}')
            files = sorted((p for p in config["themes"].glob("*.toml") if p.is_file()), key=lambda p: p.stem)
            names = [p.stem for p in files]
            current = None
            if not args.plain:
                try:
                    selected = current_theme(config).source.resolve()
                    current = next((p.stem for p in files if p.resolve() == selected), None)
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    pass  # A broken saved selection should not prevent listing themes.
            output = "\n".join(names) if args.plain else theme_listing(names, current)
            if output:
                print("printf '%s\\n' " + shlex.quote(output) if args.shell else output)
            return 0
        theme = current_theme(config) if args.theme == "exports" else Theme.load(theme_path(args.theme or config["default"], config))
        filename = theme.source
        values = theme.exports | {"CHTHM_STATE_FILE": str(config["state_file"])}
        if args.theme == "exports":
            print(exports(values), end="")
            return 0
        writes, notices, targets = [], [], set()
        for target in sorted(config["targets"]):
            reason = None if target in config["forced_targets"] else unavailable_reason(target, config)
            if reason:
                notices.append(f"Skipping {target}: {reason}")
            else:
                targets.add(target)
        for name in sorted(targets):
            planned, messages = TARGETS[name].plan(theme, config)
            writes.extend(planned)
            notices.extend(messages)
        # State is always saved, even when every optional application is absent.
        # Publish it after application files, before any reload request.
        writes.append((config["state_file"], theme.snapshot_toml(), True))
        resolved = [p.resolve() for p, _, _ in writes]
        backups = [Path(str(p.resolve()) + ".bak") for p, _, backup in writes if backup and p.exists()]
        destinations = resolved + [p.resolve() for p in backups]
        if len(set(destinations)) != len(destinations) or filename.resolve() in destinations:
            raise ValueError("Output and backup paths must be distinct and must not overwrite the source theme")
        if args.dry_run:
            print(f"Theme: {filename}", file=sys.stderr)
            for target, _, _ in writes:
                print(f"Would update: {target}", file=sys.stderr)
            print(f'Application reloads: {"enabled" if config["reload"] else "disabled"}', file=sys.stderr)
            for notice in notices:
                print(notice, file=sys.stderr)
            return 0
        for target, content, backup in writes:
            atomic_write(target, content, backup)
        if config["reload"]:
            reload_apps(values, qtile_enabled="qtile" in targets, qutebrowser_enabled="qutebrowser" in targets,
                        qt6ct_enabled="qt6ct" in targets)
        for notice in notices:
            print(notice, file=sys.stderr)
        if args.shell:
            print(exports(values), end="")
        else:
            print(f"Applied theme: {theme.name}", file=sys.stderr)
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, configparser.Error) as error:
        print(f"chthm: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
