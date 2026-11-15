#!/usr/bin/env python3
"""Install a downloaded chthm package and configure interactive zsh."""

import argparse
import ast
import configparser
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import tokenize
from urllib.request import Request, urlopen
import zipfile

BEGIN = "# >>> chthm installer >>>"
END = "# <<< chthm installer <<<"
THEME_REPOSITORY = "https://github.com/alacritty/alacritty-theme"
THEME_ARCHIVE = "https://codeload.github.com/alacritty/alacritty-theme/zip/refs/heads/master"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_THEME_BYTES = 1024 * 1024
FALLBACK_THEME = "kimbie_dark.toml"
FALLBACK_THEME_LICENSE = "alacritty-theme.LICENSE"
QT6_DEFAULT_APPLICATIONS = ("pcmanfm-qt", "qutebrowser", "sioyek", "clementine")


def expanded(value):
    return Path(os.path.expandvars(str(value))).expanduser().absolute()


def shell_config(text, integration):
    block = f'''{BEGIN}
# Keep user-installed commands available without adding duplicate PATH entries.
if (( ! ${{path[(Ie)$HOME/.local/bin]}} )); then
    path=("$HOME/.local/bin" "${{path[@]}}")
fi
export PATH
if [[ -r {shlex.quote(str(integration))} ]]; then
    source {shlex.quote(str(integration))}
fi
{END}'''
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("Malformed chthm setup block in .zshrc; repair its markers before installing")
    if BEGIN in text:
        start, stop = text.index(BEGIN), text.index(END)
        if stop < start:
            raise ValueError("Reversed chthm setup markers in .zshrc")
        return text[:start] + block + text[stop + len(END):]
    return text + ("\n" if text and not text.endswith("\n") else "") + "\n" + block + "\n"


QTILE_BEGIN = "# >>> chthm Qtile palette >>>"
QTILE_END = "# <<< chthm Qtile palette <<<"
QUTEBROWSER_BEGIN = "# >>> chthm qutebrowser palette >>>"
QUTEBROWSER_END = "# <<< chthm qutebrowser palette <<<"


def python_palette_config(text, loader, application):
    """Insert only our palette block, preserving all existing configuration text."""
    # A plain data-only table is an application-independent template palette.
    try:
        tree = ast.parse(text, filename=f"{application.lower()}/config.py")
    except SyntaxError as error:
        raise ValueError(f"{application} config.py syntax check failed: {error}") from error
    palettes = []
    for statement in tree.body:
        if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id == "colors"):
            continue
        try:
            value = ast.literal_eval(statement.value)
        except (ValueError, TypeError):
            continue
        if (isinstance(value, dict) and not set(value) - {"primary", "normal", "bright"}
                and isinstance(value.get("primary"), dict)
                and {"background", "foreground"} <= set(value["primary"])
                and all(isinstance(table, dict) and all(isinstance(color, str)
                        and re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                        for color in table.values()) for table in value.values())):
            palettes.append(statement)
    palette = palettes[0] if len(palettes) == 1 else None
    alias = "colors = chthm_colors\n" if palette is not None else ""
    session = ""
    if application == "Qtile":
        session = ('import os as _chthm_os\nimport pathlib as _chthm_pathlib\n'
                   'import shutil as _chthm_shutil\n'
                   '_chthm_config = _chthm_pathlib.Path(_chthm_os.environ.get('
                   '"XDG_CONFIG_HOME") or _chthm_pathlib.Path.home() / ".config")\n'
                   'if (_chthm_shutil.which("qt6ct") and (_chthm_config / '
                   '"environment.d/60-chthm-qt6ct.conf").is_file()):\n'
                   '    _chthm_os.environ["QT_QPA_PLATFORMTHEME"] = "qt6ct"\n'
                   'del _chthm_config, _chthm_os, _chthm_pathlib, _chthm_shutil\n')
    begin = f"# >>> chthm {application} palette >>>"
    end = f"# <<< chthm {application} palette <<<"
    filename = f"{application.lower()}/config.py"
    block = f'''{begin}
# Read the selected TOML palette; no application or chthm package import is needed.
{session}import runpy as _chthm_runpy
chthm_palette = _chthm_runpy.run_path({str(loader)!r})["load_palette"]()
chthm_colors = chthm_palette["colors"]
chthm_background = chthm_colors["primary"]["background"]
chthm_foreground = chthm_colors["primary"]["foreground"]
chthm_accent = chthm_palette["roles"]["accent"]
del _chthm_runpy
{alias}{end}
'''
    lines = text.splitlines(keepends=True)
    try:
        comments = [(token.string, token.start[0] - 1) for token in
                    tokenize.generate_tokens(io.StringIO(text).readline)
                    if token.type == tokenize.COMMENT and token.start[1] == 0]
    except (tokenize.TokenError, IndentationError) as error:
        raise ValueError(f"{application} config.py syntax check failed: {error}") from error
    starts = [line for comment, line in comments if comment == begin]
    stops = [line for comment, line in comments if comment == end]
    if len(starts) != len(stops) or len(starts) > 1 or (starts and starts[0] >= stops[0]):
        raise ValueError(f"Malformed chthm palette markers in {application} config.py")
    try:
        if starts and palette is not None and starts[0] < palette.end_lineno:
            # Move an earlier managed block below the template's default table.
            clean = "".join(lines[:starts[0]]) + "".join(lines[stops[0] + 1:])
            return python_palette_config(clean, loader, application)
        if starts:
            start, stop = starts[0], stops[0]
            updated = "".join(lines[:start]) + block + "".join(lines[stop + 1:])
        else:
            # Keep a module docstring and __future__ imports in their required positions.
            index = 0
            body = tree.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                index = body[0].end_lineno
                body = body[1:]
            for statement in body:
                if isinstance(statement, ast.ImportFrom) and statement.module == "__future__":
                    index = statement.end_lineno
                else:
                    break
            if palette is not None:
                index = palette.end_lineno
            elif not index:
                index = tree.body[0].lineno - 1 if tree.body else len(lines)
            prefix = "".join(lines[:index])
            updated = prefix + ("\n" if prefix and not prefix.endswith("\n") else "") + block + "".join(lines[index:])
        # Compile only: never execute a user's configuration during installation.
        compile(updated, filename, "exec")
    except SyntaxError as error:
        raise ValueError(f"{application} config.py syntax check failed: {error}") from error
    return updated


def qtile_config(text, loader):
    return python_palette_config(text, loader, "Qtile")


def qutebrowser_config(text, loader):
    return python_palette_config(text, loader, "qutebrowser")


def write_file(filename, content, mode=0o644):
    filename.parent.mkdir(parents=True, exist_ok=True)
    if filename.is_file() and not filename.is_symlink() and filename.read_bytes() == content.encode("utf-8"):
        filename.chmod(mode)
        return None
    fd, temporary = tempfile.mkstemp(prefix=".chthm-install-", dir=filename.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, filename)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def launcher_text(library, module):
    return ("#!/usr/bin/env python3\n"
            "# Installed by chthm.\n"
            "import sys\n"
            f"sys.path.insert(0, {str(library)!r})\n"
            f"from chthm.{module} import main\n"
            "raise SystemExit(main())\n")


def validate_zsh(text):
    zsh = shutil.which("zsh")
    if not zsh:
        return
    with tempfile.TemporaryDirectory(prefix="chthm-zsh-check-") as temporary:
        candidate = Path(temporary) / ".zshrc"
        candidate.write_text(text, encoding="utf-8")
        result = subprocess.run([zsh, "-n", str(candidate)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(".zshrc syntax check failed; no setup changes were made: " + result.stderr.strip())


def import_themes(destination, source):
    """Copy a palette collection once, preserving existing user theme files."""
    if source is not None and not source.is_dir():
        raise ValueError(f"Theme source directory not found: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    if source is not None:
        for filename in sorted(source.glob("*.toml")):
            target = destination / filename.name
            if filename.is_file() and not target.exists() and not target.is_symlink():
                shutil.copy2(filename, target)
                count += 1
    return count


def install_bundled_fallback(source, destination):
    """Install the bundled default without replacing a user's existing file."""
    palette = source / "themes" / FALLBACK_THEME
    license_file = source / "themes" / FALLBACK_THEME_LICENSE
    target = destination / FALLBACK_THEME
    if target.exists() or target.is_symlink():
        return False
    if not palette.is_file() or not license_file.is_file():
        raise ValueError("Downloaded package is missing the bundled fallback theme or its license")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(palette, target)
    provenance = destination / ".sources/bundled-kimbie-dark"
    write_file(provenance / "LICENSE", license_file.read_text(encoding="utf-8"))
    write_file(
        provenance / "SOURCE.txt",
        f"Bundled fallback: {FALLBACK_THEME}\nOriginal collection: {THEME_REPOSITORY}\n",
    )
    return True


def download_theme_archive():
    request = Request(THEME_ARCHIVE, headers={"User-Agent": "chthm-installer"})
    with urlopen(request, timeout=20) as response:
        content = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ValueError("Upstream theme archive exceeds 32 MiB")
    return content


def fetch_upstream_themes(destination):
    """Read only palette data and the license; never extract repository paths."""
    content = download_theme_archive()
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ValueError("Upstream theme archive exceeds 32 MiB")
    themes, license_text, total = {}, None, 0
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename).parts
            if not parts or parts[0] != "alacritty-theme-master" or entry.is_dir():
                continue
            is_license = parts == ("alacritty-theme-master", "LICENSE")
            is_theme = (len(parts) == 3 and parts[1] == "themes" and
                        parts[2].endswith(".toml"))
            if not is_license and not is_theme:
                continue
            name = parts[-1]
            if "\\" in name or any(ord(char) < 32 or ord(char) == 127 for char in name):
                raise ValueError("Invalid upstream theme filename")
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if kind not in (0, stat.S_IFREG):
                raise ValueError("Upstream palette entries must be regular files")
            if entry.file_size > MAX_THEME_BYTES:
                raise ValueError("An upstream theme or license exceeds 1 MiB")
            with archive.open(entry) as stream:
                data = stream.read(MAX_THEME_BYTES + 1)
            total += len(data)
            if len(data) > MAX_THEME_BYTES or total > 8 * MAX_THEME_BYTES:
                raise ValueError("Upstream palette data exceeds its size limit")
            text = data.decode("utf-8")
            if is_license:
                if license_text is not None:
                    raise ValueError("Duplicate upstream license")
                license_text = text
            else:
                document = tomllib.loads(text)
                colors = document.get("colors", {})
                if not isinstance(colors, dict):
                    raise ValueError(f"Invalid colors table in {name}")
                primary = colors.get("primary", {})
                if not isinstance(primary, dict) or not all(
                    isinstance(primary.get(key), str) and
                    re.fullmatch(r"#[0-9a-fA-F]{6}", primary[key])
                    for key in ("background", "foreground")
                ):
                    raise ValueError(f"Invalid primary palette colors in {name}")
                if name in themes:
                    raise ValueError(f"Duplicate upstream theme: {name}")
                themes[name] = text
    if not themes or not license_text:
        raise ValueError("Upstream archive is missing themes or its license")
    # Validate the entire download before writing any theme files.
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, text in sorted(themes.items()):
        target = destination / name
        if not target.exists() and not target.is_symlink():
            write_file(target, text)
            count += 1
    provenance = destination / ".sources/alacritty-theme"
    write_file(provenance / "LICENSE", license_text)
    write_file(provenance / "SOURCE.txt", f"Repository: {THEME_REPOSITORY}\nArchive: {THEME_ARCHIVE}\n")
    return count


def migrate_selection(library, config, data):
    """One-time copy of a legacy selection; never modify application files."""
    state_root = expanded(os.environ.get("XDG_STATE_HOME") or "~/.local/state")
    state_file = state_root / "chthm/current.toml"
    settings = config / "chthm/config.toml"
    if settings.is_file():
        with settings.open("rb") as stream:
            options = tomllib.load(stream)
        if "state_file" in options:
            if not isinstance(options["state_file"], str):
                raise ValueError("state_file must be a path string")
            state_file = expanded(options["state_file"])
    selection = config / "alacritty/theme.toml"
    if state_file.exists() or not selection.is_file():
        return
    with selection.open("rb") as stream:
        old = tomllib.load(stream)
    if "colors" in old:
        theme_file = selection
    else:
        imports = old.get("general", {}).get("import", old.get("import", []))
        if not isinstance(imports, list) or len(imports) != 1 or not isinstance(imports[0], str):
            raise ValueError("Legacy theme selection must import exactly one palette")
        theme_file = Path(os.path.expandvars(imports[0])).expanduser()
        if not theme_file.is_absolute():
            theme_file = selection.parent / theme_file
    copied = data / "chthm/themes" / theme_file.name
    if copied.is_file() and copied.read_bytes() == theme_file.read_bytes():
        theme_file = copied
    # This is the newly installed user's data model, never the privileged helper.
    sys.path.insert(0, str(library))
    try:
        from chthm.theme import Theme
        theme = Theme.load(theme_file)
        theme.exports  # Validate export collisions before publishing a snapshot.
        write_file(state_file, theme.snapshot_toml(), mode=0o600)
    finally:
        sys.path.pop(0)
    print(f"Migrated the selected palette to {state_file}; original application files kept")


def alacritty_import_plan(source, config):
    """Adopt an existing palette/selector file without changing terminal colors."""
    selector = config / "alacritty/theme.toml"
    if not selector.is_file():
        return []
    document = tomllib.loads(selector.read_bytes().decode("utf-8"))
    general = document.get("general", {})
    if (set(document) - {"colors", "general", "import"}
            or not isinstance(general, dict) or set(general) - {"import"}):
        raise ValueError("Alacritty theme.toml must contain only palette colors and imports; keep other settings in alacritty.toml")
    groups = (document.get("import", []), general.get("import", []))
    if not all(isinstance(group, list) and all(isinstance(value, str) for value in group) for group in groups):
        raise ValueError("Alacritty theme imports must be an array of paths")
    imports = groups[0] + groups[1]
    palette = selector.parent / "chthm-colors.toml"
    sys.path.insert(0, str(source / "src"))
    try:
        from chthm.theme import Theme
        if "colors" in document:
            theme = Theme.from_document(document, selector)
        elif imports:
            previous = Path(os.path.expandvars(imports[-1])).expanduser()
            if not previous.is_absolute():
                previous = selector.parent / previous
            theme = Theme.load(previous)
        else:
            return []  # No current palette to migrate.
        content = theme.palette_toml()
    finally:
        sys.path.pop(0)
    # theme.toml is the palette selector; alacritty.toml remains untouched.
    selection = "general.import = [" + json.dumps(str(palette), ensure_ascii=False) + "]\n"
    return [(palette, content), (selector, selection)]


def qt6ct_install_plan(source, config, data):
    if (not shutil.which("qt6ct")
            or not any(shutil.which(application) for application in QT6_DEFAULT_APPLICATIONS)):
        return [], []
    sys.path.insert(0, str(source / "src"))
    try:
        from chthm.qt6ct import install_cleanup, scheme_text, settings_text
        from chthm.qtile_palette import load_palette
        from chthm.theme import Theme
        options_file = config / "chthm/config.toml"
        options = tomllib.loads(options_file.read_text()) if options_file.is_file() else {}
        settings = expanded(options.get("qt6ct_config", config / "qt6ct/qt6ct.conf"))
        palette = expanded(options.get("qt6ct_palette", config / "qt6ct/colors/chthm.conf"))
        if settings.resolve() == palette.resolve() or options_file.resolve() in (settings.resolve(), palette.resolve()):
            raise ValueError("qt6ct palette, configuration and chthm settings paths must be distinct")
        theme = Theme.from_document(load_palette(), config / "chthm/current.toml")
        scheme = scheme_text(theme)
        current = settings.read_text(encoding="utf-8") if settings.exists() else ""
        writes, removals = install_cleanup(config, data)
        writes = [(palette, scheme), (settings, settings_text(current, palette, scheme)),
                  (config / "environment.d/60-chthm-qt6ct.conf", "QT_QPA_PLATFORMTHEME=qt6ct\n")] + writes
        return writes, removals
    finally:
        sys.path.pop(0)


def install(source, theme_source=None):
    home = Path.home()
    config = expanded(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    data = expanded(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    library = data / "chthm/lib"
    binary_dir = home / ".local/bin"
    integration = config / "chthm/chthm.zsh"
    # zsh honors ZDOTDIR when deciding where to read .zshrc.
    zshrc = expanded(os.environ.get("ZDOTDIR") or home) / ".zshrc"
    original = zshrc.read_text(encoding="utf-8") if zshrc.exists() else ""
    updated = shell_config(original, integration)
    validate_zsh(updated)
    if (not (source / "src/chthm/cli.py").is_file()
            or not (source / "chthm.zsh").is_file()
            or not (source / "themes" / FALLBACK_THEME).is_file()
            or not (source / "themes" / FALLBACK_THEME_LICENSE).is_file()):
        raise ValueError("Run install.py from a complete downloaded chthm source package")
    if library.resolve().is_relative_to(source.resolve()):
        raise ValueError("Installation directory must be outside the downloaded source tree")
    # Preflight both existing configs before performing any installation writes.
    config_updates = []
    for application, transform in (("qtile", qtile_config), ("qutebrowser", qutebrowser_config)):
        if not shutil.which(application):
            continue
        filename = config / application / "config.py"
        if filename.is_file():
            updated_config = transform(filename.read_bytes().decode("utf-8"),
                                       library / "chthm/qtile_palette.py")
            config_updates.append((filename, updated_config))
    alacritty_updates = alacritty_import_plan(source, config) if shutil.which("alacritty") else []
    collection = data / "chthm/themes"
    legacy = config / "alacritty/themes/themes"
    if theme_source is not None:
        count = import_themes(collection, expanded(theme_source))
        print(f"Imported {count} theme files into {collection} (existing files kept)")
    else:
        try:
            count = fetch_upstream_themes(collection)
            print(f"Added {count} themes from {THEME_REPOSITORY} to {collection} (existing files kept)")
            if legacy.is_dir():
                migrated = import_themes(collection, legacy)
                if migrated:
                    print(f"Also preserved {migrated} additional local themes from the older collection")
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
            print(f"Warning: could not download upstream themes: {error}", file=sys.stderr)
            count = import_themes(collection, legacy if legacy.is_dir() else None)
            print(f"Using local themes in {collection}; imported {count} fallback files")
            if install_bundled_fallback(source, collection):
                print(f"Installed bundled offline fallback: {collection / FALLBACK_THEME}")
            if not any(collection.glob("*.toml")):
                raise ValueError("No usable themes are available; repair the theme collection and reinstall")
    # Install a private package copy; it does not depend on the download location.
    library.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "src/chthm", library / "chthm", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # Remove modules deleted upstream when upgrading this private package copy.
    for module in (library / "chthm").rglob("*.py"):
        relative = module.relative_to(library / "chthm")
        if not (source / "src/chthm" / relative).is_file():
            module.unlink()
    # Clear old bytecode so rapid reinstalls cannot reuse a stale module cache.
    for cache in (library / "chthm").rglob("__pycache__"):
        shutil.rmtree(cache)
    try:
        migrate_selection(library, config, data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Warning: could not migrate the previous theme selection: {error}", file=sys.stderr)
    qt6ct_updates, qt6ct_removals = qt6ct_install_plan(source, config, data)
    write_file(binary_dir / "chthm", launcher_text(library, "cli"), mode=0o755)
    # Preserve a dotfile-manager symlink while updating the integration target.
    integration_target = integration.resolve() if integration.is_symlink() else integration
    write_file(integration_target, (source / "chthm.zsh").read_text(encoding="utf-8"))
    if original != updated:
        destination = zshrc.resolve() if zshrc.is_symlink() else zshrc
        mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
        write_file(destination, updated, mode=mode)
    for filename, content in alacritty_updates + qt6ct_updates:
        destination = filename.resolve()
        mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
        write_file(destination, content, mode=mode)
    if alacritty_updates:
        print(f"Configured Alacritty palette import in {config / 'alacritty/theme.toml'}")
    for filename, updated_config in config_updates:
        destination = filename.resolve()  # Preserve dotfile-manager symlinks.
        mode = stat.S_IMODE(destination.stat().st_mode)
        write_file(destination, updated_config, mode=mode)
        print(f"Configured palette variables in {filename}; existing settings preserved")
    for filename in qt6ct_removals:
        filename.unlink()
    if qt6ct_updates:
        print("Configured shared qt6ct colors. Reload Qtile or log in again for desktop apps to inherit qt6ct.")
    return zshrc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme-source", help="Copy missing TOML themes from this directory into chthm's collection")
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 11):
            raise ValueError("Python 3.11 or newer is required")
        if os.geteuid() == 0:
            raise ValueError("Run this installer as your normal user, without sudo")
        source = Path(__file__).resolve().parent
        zshrc = install(source, theme_source=args.theme_source)
        print("Installed chthm in ~/.local/bin")
        print(f"Configured PATH and shell integration in {zshrc}")
        print("Open a new terminal to use chthm. No applications were restarted.")
        return 0
    except (OSError, ValueError, configparser.Error) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
