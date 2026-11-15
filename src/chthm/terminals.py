"""Terminal-emulator palette generators and minimally managed config edits."""

import json
import re


COLOR_NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")


def palettes(theme):
    """Return the normalized ANSI and primary colors used by terminal adapters."""
    colors = theme.colors
    return (colors["primary"]["background"], colors["primary"]["foreground"],
            [colors["normal"][name] for name in COLOR_NAMES],
            [colors["bright"][name] for name in COLOR_NAMES])


def single_line_path(value, application):
    value = str(value)
    if any(character in value for character in "\n\r\0"):
        raise ValueError(f"{application} palette path must be a single line")
    return value


def line_block(text, body, name, comment="#", before=None):
    """Replace one exact, line-delimited managed block without parsing user config."""
    begin = f"{comment} >>> chthm {name} >>>"
    end = f"{comment} <<< chthm {name} <<<"
    lines = text.splitlines(keepends=True)
    begins = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == begin]
    ends = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == end]
    if len(begins) != len(ends) or len(begins) > 1 or (begins and ends[0] < begins[0]):
        raise ValueError(f"Malformed chthm block: {name}")
    if begins:
        del lines[begins[0]:ends[0] + 1]
    text = "".join(lines).rstrip("\r\n")
    block = begin + "\n" + body.rstrip("\r\n") + "\n" + end
    if before is None:
        return text + ("\n\n" if text else "") + block + "\n"
    match = before(text)
    if match is None:
        raise ValueError(f"Cannot safely place chthm {name} block")
    prefix, suffix = text[:match.start()].rstrip("\r\n"), text[match.start():]
    return prefix + ("\n\n" if prefix else "") + block + "\n\n" + suffix.rstrip("\r\n") + "\n"


def ghostty_theme(theme):
    background, foreground, normal, bright = palettes(theme)
    lines = [
        f"background = {background}",
        f"foreground = {foreground}",
        f"cursor-color = {foreground}",
        f"cursor-text = {background}",
        f"selection-background = {foreground}",
        f"selection-foreground = {background}",
    ]
    lines.extend(f"palette = {index}={color}" for index, color in enumerate(normal + bright))
    return "\n".join(lines) + "\n"


def ghostty_config(text, palette):
    value = json.dumps(single_line_path(palette, "Ghostty"), ensure_ascii=False)
    return line_block(text, "config-file = " + value, "ghostty colors")


def kitty_theme(theme):
    background, foreground, normal, bright = palettes(theme)
    lines = [
        f"background {background}",
        f"foreground {foreground}",
        f"cursor {foreground}",
        f"cursor_text_color {background}",
        f"selection_background {foreground}",
        f"selection_foreground {background}",
    ]
    lines.extend(f"color{index} {color}" for index, color in enumerate(normal + bright))
    return "\n".join(lines) + "\n"


def kitty_config(text, palette):
    return line_block(text, "include " + single_line_path(palette, "kitty"), "kitty colors")


def wezterm_scheme(theme):
    background, foreground, normal, bright = palettes(theme)
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    array = lambda values: "[" + ", ".join(quote(value) for value in values) + "]"
    return "\n".join([
        "[colors]",
        f"foreground = {quote(foreground)}",
        f"background = {quote(background)}",
        f"cursor_bg = {quote(foreground)}",
        f"cursor_border = {quote(foreground)}",
        f"cursor_fg = {quote(background)}",
        f"selection_bg = {quote(foreground)}",
        f"selection_fg = {quote(background)}",
        f"ansi = {array(normal)}",
        f"brights = {array(bright)}",
        "",
    ])


def mask_lua(text):
    """Blank Lua comments and strings while preserving offsets and line endings."""
    result = list(text)
    index, size = 0, len(text)

    def blank(start, stop):
        for position in range(start, stop):
            if result[position] not in "\r\n":
                result[position] = " "

    while index < size:
        if text.startswith("--", index):
            long = re.match(r"--\[(=*)\[", text[index:])
            if long:
                close = "]" + long[1] + "]"
                stop = text.find(close, index + long.end())
                stop = size if stop < 0 else stop + len(close)
            else:
                stop = text.find("\n", index)
                stop = size if stop < 0 else stop
            blank(index, stop)
            index = stop
            continue
        long = re.match(r"\[(=*)\[", text[index:])
        if long:
            close = "]" + long[1] + "]"
            stop = text.find(close, index + long.end())
            stop = size if stop < 0 else stop + len(close)
            blank(index, stop)
            index = stop
            continue
        if text[index] in "'\"":
            quote, stop = text[index], index + 1
            while stop < size:
                if text[stop] == "\\":
                    stop += 2
                elif text[stop] == quote:
                    stop += 1
                    break
                else:
                    stop += 1
            blank(index, min(stop, size))
            index = stop
            continue
        index += 1
    return "".join(result)


def _wezterm_return(text):
    masked = mask_lua(text)
    matches = list(re.finditer(r"(?m)^return[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*$", masked))
    if len(matches) != 1:
        raise ValueError("WezTerm config needs exactly one top-level 'return NAME' line so chthm can update it safely")
    return matches[0]


def wezterm_config(text, scheme):
    scheme = single_line_path(scheme, "WezTerm")
    if not text.strip():
        text = "local wezterm = require 'wezterm'\nlocal config = wezterm.config_builder()\n\nreturn config\n"

    def before(current):
        return _wezterm_return(current)

    returned = _wezterm_return(text)[1]
    lua_path = json.dumps(scheme, ensure_ascii=False)
    body = (f"wezterm.add_to_config_reload_watch_list({lua_path})\n"
            f"{returned}.color_scheme = \"chthm\"")
    return line_block(text, body, "wezterm colors", "--", before)


def foot_theme(theme):
    background, foreground, normal, bright = palettes(theme)
    clean = lambda color: color.removeprefix("#")
    entries = [
        f"foreground={clean(foreground)}",
        f"background={clean(background)}",
        f"selection-foreground={clean(background)}",
        f"selection-background={clean(foreground)}",
        f"cursor={clean(background)} {clean(foreground)}",
    ]
    entries.extend(f"regular{index}={clean(color)}" for index, color in enumerate(normal))
    entries.extend(f"bright{index}={clean(color)}" for index, color in enumerate(bright))
    body = "\n".join(entries)
    return f"[colors-dark]\n{body}\n\n[colors-light]\n{body}\n"


def foot_config(text, palette):
    # Appending a fresh [main] section makes the include independent of whichever
    # section ended the user's file. foot accepts repeated sections.
    return line_block(text, "[main]\ninclude=" + single_line_path(palette, "foot"), "foot colors")
