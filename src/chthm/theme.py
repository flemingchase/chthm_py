"""Application-independent palette model and TOML compatibility loader."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import tomllib

SCHEMA_VERSION = 1
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def read_toml(filename):
    with Path(filename).open("rb") as stream:
        return tomllib.load(stream)


def _hex(value, name):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError(f"{name} must have the form #RRGGBB")
    return value.lower()


def normalize_colors(colors):
    if not isinstance(colors, dict):
        raise ValueError("Theme must contain a [colors] table")
    primary = colors.get("primary", {})
    if not isinstance(primary, dict):
        raise ValueError("colors.primary must be a table")
    background = _hex(primary.get("background"), "colors.primary.background")
    foreground = _hex(primary.get("foreground"), "colors.primary.foreground")
    aliases = {"CellBackground": background, "CellForeground": foreground}

    def normalize(value, name):
        if isinstance(value, dict):
            return {key: normalize(item, name + "." + key) for key, item in value.items()}
        if isinstance(value, list):
            if name != "colors.indexed_colors":
                raise ValueError(f"Unsupported palette array: {name}")
            entries, seen = [], set()
            for entry in value:
                if not isinstance(entry, dict) or set(entry) != {"index", "color"}:
                    raise ValueError("Each indexed color needs index and color")
                index = entry["index"]
                if type(index) is not int or not 0 <= index <= 255 or index in seen:
                    raise ValueError("Indexed color indices must be unique integers from 0 to 255")
                seen.add(index)
                entries.append({"index": index, "color": _hex(entry["color"], name)})
            return entries
        if isinstance(value, bool) and name == "colors.transparent_background_colors":
            return value
        if isinstance(value, str) and value in aliases:
            return aliases[value]
        return _hex(value, name)

    result = normalize(colors, "colors")
    names = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")
    for group in ("normal", "bright"):
        table = result.setdefault(group, {})
        if not isinstance(table, dict):
            raise ValueError(f"colors.{group} must be a table")
        for name in names:
            default = background if name == "black" else foreground
            table.setdefault(name, result.get("normal", {}).get(name, default))
    return result


def toml_text(document):
    """Serialize our small data-only TOML schema, including indexed colors."""
    lines = []

    def key_text(key):
        return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key, ensure_ascii=False)

    def scalar(value):
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, bool):
            return str(value).lower()
        if type(value) is int:
            return str(value)
        raise ValueError(f"Unsupported TOML value: {value!r}")

    def section(table, keys=(), array=False):
        if keys:
            label = ".".join(key_text(key) for key in keys)
            lines.append(("[[" if array else "[") + label + ("]]" if array else "]"))
        for key, value in table.items():
            if not isinstance(value, (dict, list)):
                lines.append(f"{key_text(key)} = {scalar(value)}")
        lines.append("")
        for key, value in table.items():
            if isinstance(value, dict):
                section(value, keys + (key,))
            elif isinstance(value, list):
                for item in value:
                    section(item, keys + (key,), array=True)

    section(document)
    return "\n".join(lines).rstrip() + "\n"


def shell_exports(values):
    return "".join(f"export {name}={shlex.quote(value)}\n" for name, value in values.items())


@dataclass(frozen=True)
class Theme:
    name: str
    source: Path
    colors: dict
    roles: dict

    @classmethod
    def from_document(cls, document, source):
        colors = normalize_colors(document.get("colors"))
        metadata = document.get("theme", {})
        if not isinstance(metadata, dict):
            raise ValueError("theme metadata must be a table")
        name = metadata.get("name", Path(source).stem)
        if not isinstance(name, str) or not name or any(char in name for char in "\n\r\0"):
            raise ValueError("Theme name must be a nonempty single-line string")
        roles = document.get("roles", {})
        if not isinstance(roles, dict):
            raise ValueError("roles must be a table")
        roles = {key: _hex(value, "roles." + key) for key, value in roles.items()}
        normal = colors.get("normal", {})
        if not isinstance(normal, dict):
            raise ValueError("colors.normal must be a table")
        defaults = {"accent": "blue", "error": "red", "warning": "yellow", "success": "green"}
        for role, color in defaults.items():
            roles.setdefault(role, normal.get(color, colors["primary"]["foreground"]))
        return cls(name, Path(source).absolute(), colors, roles)

    @classmethod
    def load(cls, filename):
        return cls.from_document(read_toml(filename), filename)

    @property
    def exports(self):
        values = {"CHTHM_BACKGROUND": self.colors["primary"]["background"],
                  "CHTHM_FOREGROUND": self.colors["primary"]["foreground"],
                  "CHTHM_THEME": self.name}

        def flatten(table, prefix):
            for key, value in table.items():
                name = prefix + "_" + re.sub(r"[^A-Za-z0-9_]", "_", key).upper()
                if isinstance(value, dict):
                    flatten(value, name)
                elif isinstance(value, (str, bool, int)):
                    if name in values:
                        raise ValueError(f"Export name collision: {name}")
                    values[name] = str(value)

        flatten(self.colors, "CHTHM_COLORS")
        flatten(self.roles, "CHTHM_ROLES")
        return values

    def palette_toml(self):
        return toml_text({"colors": self.colors})

    def snapshot_toml(self):
        return toml_text({"schema_version": SCHEMA_VERSION,
                          "selection": {"name": self.name, "file": str(self.source)},
                          "colors": self.colors, "roles": self.roles})

    @classmethod
    def from_snapshot(cls, filename):
        document = read_toml(filename)
        if type(document.get("schema_version")) is not int or document["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported current palette schema version")
        selection = document.get("selection", {})
        if not isinstance(selection, dict) or not isinstance(selection.get("file"), str):
            raise ValueError("Current palette is missing selection.file")
        source = Path(selection["file"])
        if not source.is_absolute():
            raise ValueError("Current palette selection.file must be absolute")
        return cls.from_document({"theme": {"name": selection.get("name")},
                                  "colors": document.get("colors"),
                                  "roles": document.get("roles", {})}, source)
