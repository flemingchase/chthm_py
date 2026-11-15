"""Application-specific configuration edits; only the standard library is used."""

import configparser
import json
import os
from pathlib import Path
import re

from .pages import blank_page_html, color_scheme


def read_text(filename):
    return filename.read_text(encoding="utf-8") if filename.exists() else ""


def managed_block(text, body, name, comment="css"):
    """Replace our own block, keeping all other customization untouched."""
    if comment == "css":
        begin, end = f"/* chthm:begin {name} */", f"/* chthm:end {name} */"
    else:
        begin, end = f"// chthm:begin {name}", f"// chthm:end {name}"
    block = begin + "\n" + body.rstrip() + "\n" + end
    if text.count(begin) != text.count(end) or text.count(begin) > 1:
        raise ValueError(f"Malformed chthm block: {name}")
    if begin in text:
        start, stop = text.index(begin), text.index(end)
        if stop < start:
            raise ValueError(f"Malformed chthm block: {name}")
        # Append at the end so subsequent existing rules/preferences do not win.
        text = text[:start] + text[stop + len(end):]
    return text.rstrip("\n") + ("\n\n" if text.rstrip("\n") else "") + block + "\n"


def mask_comments_strings(text):
    """Keep offsets and newlines while hiding Rasi comments and quoted strings."""
    token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
    return token.sub(lambda m: "".join("\n" if c == "\n" else " " for c in m[0]), text)


def rofi_text(text, values):
    """Rewrite only the foreground/background declarations in global * blocks."""
    masked = mask_comments_strings(text)
    colors = {"foreground": values["CHTHM_FOREGROUND"], "background": values["CHTHM_BACKGROUND"]}
    # Find top-level blocks rather than matching commented examples or widgets.
    depth, start, blocks, boundary = 0, None, [], 0
    for token in re.finditer(r"[{};]", masked):
        char = token[0]
        if char == "{" and depth == 0:
            selector = masked[boundary:token.start()].strip()
            start = token.end() if "*" in [s.strip() for s in selector.split(",")] else None
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced braces in Rofi config")
            if depth == 0:
                if start is not None:
                    blocks.append((start, token.start()))
                boundary = token.end()
        elif depth == 0:
            boundary = token.end()
    if depth:
        raise ValueError("Unbalanced braces in Rofi config")
    changes, seen = [], set()
    for start, end in blocks:
        for match in re.finditer(r"(?<![\w-])(foreground|background)\s*:([^;{}]*);", masked[start:end]):
            key = match[1]
            offset = start + match.start(2)
            whitespace = re.match(r"[ \t]*", text[offset:])[0]
            changes.append((offset, start + match.end(2), whitespace + colors[key]))
            seen.add(key)
    missing = [f"    {key}: {value};" for key, value in colors.items() if key not in seen]
    if missing:
        if blocks:
            end = blocks[-1][1]
            changes.append((end, end, "\n" + "\n".join(missing) + "\n"))
        else:
            text += ("\n" if text and not text.endswith("\n") else "") + "\n* {\n" + "\n".join(missing) + "\n}\n"
    for start, end, replacement in sorted(changes, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def ini_section_text(text, section, values):
    """Edit named INI keys without reserializing unrelated Qt settings."""
    lines = text.splitlines(keepends=True)
    headings = [(i, m[1]) for i, line in enumerate(lines)
                if (m := re.fullmatch(r"\s*\[([^\]]+)\]\s*", line))]
    matches = [(i, name) for i, name in headings if name == section]
    if len(matches) > 1:
        raise ValueError(f"Duplicate [{section}] sections")
    if not matches:
        return text.rstrip("\n") + ("\n\n" if text else "") + f"[{section}]\n" + "".join(f"{k}={v}\n" for k, v in values.items())
    start = matches[0][0]
    if not lines[start].endswith("\n"):
        lines[start] += "\n"
    stop = next((i for i, _ in headings if i > start), len(lines))
    body, seen = [], set()
    for line in lines[start + 1:stop]:
        match = re.match(r"\s*([^=\s]+)\s*=", line)
        if match and match[1] in values:
            key = match[1]
            if key not in seen:
                body.append(f"{key}={values[key]}\n")
                seen.add(key)
        else:
            body.append(line)
    if body and not body[-1].endswith("\n"):
        body[-1] += "\n"
    body.extend(f"{k}={v}\n" for k, v in values.items() if k not in seen)
    return "".join(lines[:start + 1] + body + lines[stop:])


def sioyek_text(text, values):
    """Update only interface colors, leaving PDF colors and modes untouched."""
    def rgb(color):
        return " ".join(f"{int(color[i:i + 2], 16) / 255:.6f}" for i in (1, 3, 5))

    background = rgb(values["CHTHM_BACKGROUND"])
    foreground = rgb(values["CHTHM_FOREGROUND"])
    colors = {
        "background_color": background,
        "dark_mode_background_color": background,
        "ui_background_color": background,
        "ui_text_color": foreground,
        "ui_selected_background_color": foreground,
        "ui_selected_text_color": background,
        "status_bar_color": background,
        "status_bar_text_color": foreground,
    }
    lines, seen = [], set()
    for line in text.splitlines(keepends=True):
        match = re.match(r"^([ \t]*)(\S+)(?:[ \t]+([^\r\n]*))?(\r?\n)?$", line)
        if match and match[2] in colors:
            key = match[2]
            # Preserve trailing comments on managed declarations, including when
            # the previous value was a hex color rather than normalized RGB.
            old_value = match[3] or ""
            comment = re.search(r"(?<!\S)#(?![0-9A-Fa-f]{6,8}(?:\s|$)).*$", old_value)
            suffix = " " + comment[0] if comment else ""
            line = f"{match[1]}{key} {colors[key]}{suffix}{match[4] or ''}"
            seen.add(key)
        lines.append(line)
    missing = [f"{key} {value}\n" for key, value in colors.items() if key not in seen]
    if missing:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append("\n# Interface colors managed by chthm\n" if lines else "# Interface colors managed by chthm\n")
        lines.extend(missing)
    return "".join(lines)


def profile_path(root, value, relative=True):
    candidate = Path(os.path.expandvars(value)).expanduser()
    return (root / candidate if relative and not candidate.is_absolute() else candidate).absolute()


def firefox_profiles(roots, explicit=None, application="Firefox"):
    """Respect install defaults before old ProfileN/Default flags."""
    if explicit is not None:
        profiles = list(dict.fromkeys(Path(p).resolve() for p in explicit))
        for profile in profiles:
            if not profile.is_dir():
                raise ValueError(f"{application} profile directory not found: {profile}")
        return profiles
    for root in roots:
        registry = root / "profiles.ini"
        if not registry.is_file():
            continue
        parser = configparser.RawConfigParser()
        parser.read_string(read_text(registry))
        installs = configparser.RawConfigParser()
        if (root / "installs.ini").exists():
            installs.read_string(read_text(root / "installs.ini"))
        defaults = set()
        for section in parser.sections():
            if section.startswith("Install") and parser.has_option(section, "Default"):
                defaults.add(profile_path(root, parser.get(section, "Default")))
        for section in installs.sections():
            if installs.has_option(section, "Default"):
                defaults.add(profile_path(root, installs.get(section, "Default")))
        profiles, legacy_defaults = [], set()
        for section in parser.sections():
            if section.startswith("Profile") and parser.has_option(section, "Path"):
                profile = profile_path(root, parser.get(section, "Path"), parser.get(section, "IsRelative", fallback="1") == "1")
                profiles.append(profile)
                if parser.get(section, "Default", fallback="0") == "1":
                    legacy_defaults.add(profile)
        candidates = defaults or legacy_defaults or set(profiles)
        if len(candidates) > 1:
            option = "--" + application.lower() + "-profile"
            raise ValueError(f"Multiple {application} defaults in {root}; select {option} explicitly")
        if candidates:
            selected = candidates.pop()
            if not selected.is_dir():
                raise ValueError(f"{application} default profile does not exist: {selected}")
            return [selected.resolve()]
    return []


def firefox_css(values):
    bg, fg = values["CHTHM_BACKGROUND"], values["CHTHM_FOREGROUND"]
    return f'''@-moz-document url("chrome://browser/content/browser.xhtml") {{
    :root {{
        --chthm-background: {bg} !important;
        --chthm-foreground: {fg} !important;
        --lwt-accent-color: {bg} !important;
        --lwt-text-color: {fg} !important;
        --toolbar-bgcolor: {bg} !important;
        --toolbar-color: {fg} !important;
        --toolbar-field-background-color: {bg} !important;
        --toolbar-field-color: {fg} !important;
        --toolbar-field-focus-background-color: {bg} !important;
        --toolbar-field-focus-color: {fg} !important;
        --toolbar-field-background-color-focus: {bg} !important;
        --toolbar-field-text-color: {fg} !important;
        --toolbar-field-text-color-focus: {fg} !important;
        --toolbar-field-border-color: {fg} !important;
        --toolbar-field-border-color-focus: {fg} !important;
        --urlbar-background-color: {bg} !important;
        --urlbar-background-color-focus: {bg} !important;
        --urlbar-box-background-color: {bg} !important;
        --urlbar-box-background-color-hover: {fg} !important;
        --urlbar-box-background-color-active: {fg} !important;
        --urlbar-box-background-color-focus: {bg} !important;
        --urlbar-box-text-color: {fg} !important;
        --urlbar-box-text-color-hover: {bg} !important;
        --urlbar-box-text-color-active: {bg} !important;
        --urlbar-box-text-color-focus: {fg} !important;
        --urlbarview-action-button-background-color: {bg} !important;
        --urlbarview-action-button-background-color-hover: {fg} !important;
        --urlbarview-background-color-hover: {fg} !important;
        --urlbarview-background-color-selected: {fg} !important;
        --urlbarview-separator-color: {fg} !important;
        --urlbarview-text-color-action: {fg} !important;
        --urlbarview-text-color-hover: {bg} !important;
        --urlbarview-text-color-secondary: {fg} !important;
        --urlbarview-text-color-selected: {bg} !important;
        --toolbox-background-color: {bg} !important;
        --toolbox-background-color-inactive: {bg} !important;
        --tab-background-color: {bg} !important;
        --tab-background-color-hover: {bg} !important;
        --tab-background-color-selected: {fg} !important;
        --tab-selected-bgcolor: {fg} !important;
        --tab-text-color: {fg} !important;
        --tab-text-color-selected: {bg} !important;
        --tab-selected-textcolor: {bg} !important;
        --panel-background-color: {bg} !important;
        --panel-text-color: {fg} !important;
        --panel-border-color: {fg} !important;
        --panel-separator-color: {fg} !important;
        --popup-background-color: {bg} !important;
        --popup-border-color: {fg} !important;
        --border-radius-xsmall: 0px !important;
        --border-radius-small: 0px !important;
        --border-radius-medium: 0px !important;
        --border-radius-large: 0px !important;
        --border-radius-xlarge: 0px !important;
        --border-radius-circle: 0px !important;
        --button-border-radius: 0px !important;
        --input-border-radius: 0px !important;
        --input-search-border-radius: 0px !important;
        --panel-border-radius: 0px !important;
        --panel-menuitem-border-radius: 0px !important;
        --popup-border-radius: 0px !important;
        --toolbarbutton-border-radius: 0px !important;
        --urlbar-background-border-radius: 0px !important;
        --urlbar-border-radius: 0px !important;
        --urlbar-inner-border-radius: 0px !important;
        --urlbarview-border-radius: 0px !important;
        --urlbarview-icon-border-radius: 0px !important;
        --urlbarview-row-border-radius: 0px !important;
    }}
    #navigator-toolbox, #titlebar, #TabsToolbar, #nav-bar,
    #PersonalToolbar, #toolbar-menubar, #sidebar-main,
    #urlbar-background, #searchbar {{
        background: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
    }}
    #urlbar-input, .searchbar-textbox {{
        color: var(--chthm-foreground) !important;
    }}
    #urlbar, .urlbar, #searchbar,
    #PopupSearchAutoComplete {{
        --toolbar-field-background-color: var(--chthm-background) !important;
        --toolbar-field-background-color-focus: var(--chthm-background) !important;
        --toolbar-field-text-color: var(--chthm-foreground) !important;
        --toolbar-field-text-color-focus: var(--chthm-foreground) !important;
        --toolbar-field-border-color: var(--chthm-foreground) !important;
        --toolbar-field-border-color-focus: var(--chthm-foreground) !important;
        --urlbar-background-color: var(--chthm-background) !important;
        --urlbar-background-color-focus: var(--chthm-background) !important;
        --urlbarview-background-color-hover: var(--chthm-foreground) !important;
        --urlbarview-background-color-selected: var(--chthm-foreground) !important;
        --urlbarview-text-color-hover: var(--chthm-background) !important;
        --urlbarview-text-color-selected: var(--chthm-background) !important;
        --urlbarview-text-color-action: var(--chthm-foreground) !important;
        --urlbarview-text-color-secondary: var(--chthm-foreground) !important;
        --urlbarview-separator-color: var(--chthm-foreground) !important;
        background-color: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
    }}
    .urlbarView, .urlbarView-results,
    #PopupSearchAutoComplete::part(content),
    .search-panel-tree {{
        background: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
    }}
    :is(.urlbarView-row, .searchbar-engine-one-off-item,
        .search-panel-tree > .autocomplete-richlistitem):is([selected], :hover) {{
        background-color: var(--chthm-foreground) !important;
        color: var(--chthm-background) !important;
    }}
    #urlbar-background, #searchbar,
    toolbarbutton, .toolbarbutton-icon,
    button, input, select, menulist {{
        border-radius: 0 !important;
    }}
    .tabbrowser-tab:not([selected]) .tab-background {{
        background: var(--chthm-background) !important;
        box-shadow: none !important;
    }}
    .tabbrowser-tab:not([selected]),
    .tabbrowser-tab:not([selected]) .tab-content,
    .tabbrowser-tab:not([selected]) .tab-label {{
        color: var(--chthm-foreground) !important;
    }}
    .tabbrowser-tab[selected] .tab-background {{
        background: var(--chthm-foreground) !important;
        box-shadow: none !important;
    }}
    .tabbrowser-tab[selected],
    .tabbrowser-tab[selected] .tab-content,
    .tabbrowser-tab[selected] .tab-label {{
        color: var(--chthm-background) !important;
    }}
    menupopup,
    panel {{
        --panel-background-color: var(--chthm-background) !important;
        --panel-text-color: var(--chthm-foreground) !important;
        --panel-border-color: var(--chthm-foreground) !important;
        --panel-separator-color: var(--chthm-foreground) !important;
        --popup-background-color: var(--chthm-background) !important;
        --popup-border-color: var(--chthm-foreground) !important;
        --text-color: var(--chthm-foreground) !important;
        --text-color-deemphasized: var(--chthm-foreground) !important;
        --text-color-disabled: var(--chthm-foreground) !important;
        color: var(--chthm-foreground) !important;
    }}
    menupopup::part(content),
    panel::part(content) {{
        background: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
        border-color: var(--chthm-foreground) !important;
    }}
    :is(menu, menuitem) {{
        color: var(--chthm-foreground) !important;
        fill: currentColor !important;
        border-radius: 0 !important;
    }}
    :is(menu, menuitem):is([_moz-menuactive], :hover):not([disabled]) {{
        background-color: var(--chthm-foreground) !important;
        color: var(--chthm-background) !important;
    }}
    :is(menu, menuitem)[disabled] {{
        color: var(--chthm-foreground) !important;
    }}
    menuseparator::before {{
        border-color: var(--chthm-foreground) !important;
    }}
}}'''


def firefox_content_css(values):
    bg, fg = values["CHTHM_BACKGROUND"], values["CHTHM_FOREGROUND"]
    return f'''@-moz-document url-prefix("about:preferences") {{
    :root {{
        --chthm-background: {bg} !important;
        --chthm-foreground: {fg} !important;
        --background-color-canvas: var(--chthm-background) !important;
        --background-color-box: var(--chthm-background) !important;
        --background-color-box-info: var(--chthm-background) !important;
        --card-background-color: var(--chthm-background) !important;
        --dialog-background-color: var(--chthm-background) !important;
        --input-background-color: var(--chthm-background) !important;
        --panel-background-color: var(--chthm-background) !important;
        --popup-background-color: var(--chthm-background) !important;
        --text-color: var(--chthm-foreground) !important;
        --text-color-deemphasized: var(--chthm-foreground) !important;
        --text-color-disabled: var(--chthm-foreground) !important;
        --button-text-color: var(--chthm-foreground) !important;
        --input-text-color: var(--chthm-foreground) !important;
        --panel-text-color: var(--chthm-foreground) !important;
        --border-color: var(--chthm-foreground) !important;
        --border-radius-xsmall: 0px !important;
        --border-radius-small: 0px !important;
        --border-radius-medium: 0px !important;
        --border-radius-large: 0px !important;
        --border-radius-xlarge: 0px !important;
        --border-radius-circle: 0px !important;
        --button-border-radius: 0px !important;
        --card-border-radius: 0px !important;
        --dialog-border-radius: 0px !important;
        --input-border-radius: 0px !important;
        --input-search-border-radius: 0px !important;
        --panel-border-radius: 0px !important;
        --panel-menuitem-border-radius: 0px !important;
        --popup-border-radius: 0px !important;
        --select-border-radius: 0px !important;
        background-color: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
    }}

    body, #preferences-root, .main-content {{
        background-color: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
    }}

    button, input, select, menulist, dialog,
    .card, .dialogBox, .info-box-container {{
        border-radius: 0 !important;
    }}
}}

@-moz-document url("about:newtab"), url("about:home") {{
    :root {{
        --chthm-background: {bg} !important;
        --chthm-foreground: {fg} !important;
        --newtab-background-color: var(--chthm-background) !important;
        --newtab-background-color-secondary: var(--chthm-background) !important;
        --newtab-text-primary-color: var(--chthm-foreground) !important;
        --newtab-text-secondary-color: var(--chthm-foreground) !important;
        background-color: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
    }}

    body, .activity-stream, .outer-wrapper,
    .search-wrapper, .search-inner-wrapper {{
        background-color: var(--chthm-background) !important;
        color: var(--chthm-foreground) !important;
    }}

    content-search-handoff-ui,
    moz-urlbar {{
        --content-search-handoff-ui-background-color: var(--chthm-background) !important;
        --content-search-handoff-ui-color: var(--chthm-foreground) !important;
        --content-search-handoff-ui-fill: var(--chthm-foreground) !important;
        --content-search-handoff-ui-caret-color: var(--chthm-foreground) !important;
        --urlbar-background-color: var(--chthm-background) !important;
        --urlbar-background-color-focus: var(--chthm-background) !important;
        --toolbar-field-text-color: var(--chthm-foreground) !important;
        --toolbar-field-text-color-focus: var(--chthm-foreground) !important;
        --urlbarview-background-color-hover: var(--chthm-foreground) !important;
        --urlbarview-background-color-selected: var(--chthm-foreground) !important;
        --urlbarview-text-color-hover: var(--chthm-background) !important;
        --urlbarview-text-color-selected: var(--chthm-background) !important;
        border-radius: 0 !important;
    }}
}}'''


def firefox_writes(profile, values, application="firefox"):
    chrome = profile / "chrome/userChrome.css"
    content = profile / "chrome/userContent.css"
    user = profile / "user.js"
    homepage = profile / "chthm-home.html"
    content_css = firefox_content_css(values)
    preferences = [
        'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);',
        'user_pref("browser.startup.homepage", ' + json.dumps(homepage.absolute().as_uri()) + ');',
        'user_pref("browser.startup.page", 1);',
    ]
    # Let sites choose their own palette using the native light/dark preference.
    # Custom document colors in current Gecko require forced-color mode.
    preferences.extend([
        'user_pref("browser.display.document_color_use", 1);',
        'user_pref("layout.css.prefers-color-scheme.content-override", ' +
        ('0' if color_scheme(values["CHTHM_BACKGROUND"]) == "dark" else '1') + ');',
    ])
    preferences = '\n'.join(preferences)
    return [
        (homepage, blank_page_html(values["CHTHM_BACKGROUND"], values["CHTHM_FOREGROUND"]), True),
        (chrome, managed_block(read_text(chrome), firefox_css(values), application), True),
        (content, managed_block(read_text(content), content_css, application), True),
        (user, managed_block(read_text(user), preferences, application, "js"), True),
    ]


BG_KEYS = ("default-bg", "statusbar-bg", "inputbar-bg", "recolor-lightcolor")
FG_KEYS = ("default-fg", "statusbar-fg", "inputbar-fg", "recolor-darkcolor")


def zathura_text(text, values):
    colors = dict.fromkeys(BG_KEYS, values["CHTHM_BACKGROUND"])
    colors.update(dict.fromkeys(FG_KEYS, values["CHTHM_FOREGROUND"]))
    seen, lines = set(), []
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] == "set" and words[1] in colors:
            key = words[1]
            if key not in seen:
                lines.append(f'set {key} "{colors[key]}"')
                seen.add(key)
        else:
            lines.append(line)
    lines.extend(f'set {key} "{value}"' for key, value in colors.items() if key not in seen)
    return "\n".join(lines) + "\n"

