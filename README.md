# chthm

> [!NOTE]
> **Vibe-coding disclaimer:** this project was "vibe coded" with OpenAI Codex.
> Review and test the code and configuration before relying on it.

Switch Linux desktop colors from a shared TOML palette.

chthm keeps a theme collection and a snapshot of your selected palette in
standard user directories. Application adapters write the colors each program
needs. Qtile and qutebrowser can read the same palette through small snippets
added to their existing Python configurations by the installer.

Themes are independent of Alacritty. The installer uses the
[alacritty/alacritty-theme collection](https://github.com/alacritty/alacritty-theme)
as its default source, and you can supply your own TOML files instead.

## Requirements

* Linux and Python 3.11 or newer.
* zsh for the automatic shell integration.
* Internet access for the default theme download, or a local theme directory.

The runtime and installer use Python's standard library. Applications are
optional: missing default targets are skipped. Installation and theme changes
run as your normal user without administrator privileges.

## Install and update

From the downloaded project directory, run:

```
python3 install.py
```

Then open a new terminal and choose a theme:

```
chthm list
chthm kimbie_dark --dry-run
chthm kimbie_dark
```

The installer:

1. Copies the program into your user data directory and installs commands in
   ~/.local/bin. The downloaded source directory can then be moved or removed.
2. Downloads missing TOML themes from the upstream collection's master branch.
   If that download fails, installs the bundled `kimbie_dark.toml` so the
   initial default remains usable offline. Existing theme files are kept,
   including any edits you made to them.
3. Adds a marked block to .zshrc to put ~/.local/bin on PATH and load the shell
   integration. If ZDOTDIR is set, it uses $ZDOTDIR/.zshrc.
4. Adds palette-variable snippets to existing Qtile and qutebrowser config.py
   files only when the corresponding executable is installed. It preserves the
   other configuration text and updates files directly. Missing config.py files
   and stale configs for uninstalled applications are left untouched.
5. When Alacritty is installed, adopts an existing theme.toml palette or
   selector: saves its colors to chthm-colors.toml and installs the import in
   theme.toml. Missing theme.toml files are left absent during installation.
6. When qt6ct and at least one default Qt 6 application are installed,
   initializes its shared palette from the saved theme (or the built-in
   fallback), configures the Qt platform environment, and removes PCManFM-Qt's
   previous stylesheet override.

Close Qt applications before installation, especially Clementine, so they do
not overwrite their settings on exit. Installation does not restart applications. Qtile and qutebrowser will read
newly added snippets when their configurations next load. The snippets provide
variables and connect recognized template palettes as described below. Other
color assignments need to adopt those variables explicitly. Existing personal
loaders and hardcoded defaults are preserved.

For an offline installation or a different collection:

```
python3 install.py --theme-source /path/to/themes
```

The directory must contain .toml files directly. This option bypasses the
upstream download and copies missing theme files into chthm's collection.

Rerun the installer after updating the downloaded program. Repeated installation
keeps one shell block and one palette block per application. The installed
program is a copy; editing the downloaded source alone does not update it.
Theme files already present in the destination are not refreshed automatically.

If the download fails, the installer uses available local themes, imports
missing files from ~/.config/alacritty/themes/themes when that older collection
exists, and installs its bundled `kimbie_dark.toml` fallback if that theme is
not already present. A fresh offline installation therefore always has the
initial default theme without requiring Alacritty or network access. Existing
theme files are never replaced. The installer also attempts to migrate an older
Alacritty selection into chthm's state when no snapshot exists. Existing state
is preserved, and an unsuccessful migration produces a warning.

## Files and directories

These are the default locations:

| Path | Purpose |
| --- | --- |
| ~/.local/bin/chthm | Main command. |
| ~/.local/share/chthm/lib | Private installed Python package and standalone palette loader. |
| ~/.config/qt6ct/colors/chthm.conf | Shared Qt 6 color palette. |
| ~/.config/qt6ct/qt6ct.conf | Existing qt6ct settings, with the generated palette selected. |
| ~/.config/environment.d/60-chthm-qt6ct.conf | Platform-theme environment for user services and sessions which load it. |
| ~/.config/ghostty/chthm-colors.conf | Generated Ghostty palette, when Ghostty is installed and selected. |
| ~/.config/kitty/chthm-theme.conf | Generated kitty palette, when kitty is installed and selected. |
| ~/.config/wezterm/colors/chthm.toml | Generated WezTerm color scheme, when WezTerm is installed and selected. |
| ~/.config/foot/chthm.ini | Generated foot dark and light palettes, when foot is installed and selected. |
| ~/.local/share/chthm/themes | User-owned TOML theme collection. |
| ~/.local/share/chthm/themes/.sources/alacritty-theme | Upstream source information and license copied with the download. |
| ~/.local/share/chthm/themes/.sources/bundled-kimbie-dark | Source information and license for the bundled offline fallback. |
| ~/.local/share/chthm/qutebrowser/blank.html | Generated blank page using the selected background color. |
| ~/.local/state/chthm/current.toml | Selected theme metadata and resolved palette snapshot. |
| ~/.config/chthm/config.toml | Optional user settings; create this file when needed. |
| ~/.config/chthm/chthm.zsh | Installed shell integration. |

XDG_DATA_HOME, XDG_CONFIG_HOME and XDG_STATE_HOME override the corresponding
data, configuration and state roots. The command directory remains
~/.local/bin. There is no dependency on the location of the downloaded project.

## Everyday commands

List themes in readable columns, with the current source file marked:

```
chthm list
```

Print one name per line for scripts or selectors:

```
chthm list --plain
```

Apply a theme by collection filename or explicit path:

```
chthm kimbie_dark
chthm /path/to/custom.toml
```

Preview planned file updates without writes or reloads:

```
chthm kimbie_dark --dry-run
```

Apply without requesting application reloads:

```
chthm kimbie_dark --no-reload
```

Choose targets for one invocation:

```
chthm kimbie_dark --targets alacritty,rofi
```

Add targets to the configured or default selection:

```
chthm kimbie_dark --add-targets qt6ct
```

Show the available options:

```
chthm --help
```

Running chthm without a theme argument applies default_theme, initially
kimbie_dark. It does not reapply the saved current selection.

A successful theme application is quiet. chthm writes to standard error only
when an error occurs or an explicit reload hook fails. Read-only commands such
as `list`, `exports`, `--help` and `--version` still produce their requested
output, and `--shell` still prints exports. `--dry-run` is intentionally verbose
because its purpose is to preview files, skipped targets and application notes.

The zsh function exports the selected colors into the current shell. Running
`command chthm` bypasses that function and still updates files, but cannot
change its parent shell's environment. `chthm exports` reads palette exports
without changing files or restarting applications. Shell startup uses this
read-only operation. Common exported names include CHTHM_BACKGROUND,
CHTHM_FOREGROUND, CHTHM_THEME, CHTHM_COLORS_NORMAL_BLUE and CHTHM_ROLES_ACCENT.

## Configuration and target selection

### Default applications

The original default set comes from the applications represented in
`template_config` and `chase_arch`, with LibreWolf added. Ghostty, kitty,
WezTerm and foot are also defaults so the five supported terminal emulators,
including Alacritty, follow the selected palette. chthm selects these fourteen
targets by default, but edits a target only when that application is installed:

| Target | chthm integration | Shared Qt 6 palette |
| --- | --- | --- |
| alacritty | Generates the palette imported by Alacritty. | No |
| ghostty | Generates a Ghostty palette and adds a managed `config-file` entry. | No |
| kitty | Generates a kitty palette and adds a managed `include` entry. | No |
| wezterm | Generates a TOML color scheme and selects and watches it from wezterm.lua. | No |
| foot | Generates dark and light foot color sections and adds a managed include. | No |
| zathura | Updates Zathura interface colors. | No |
| rofi | Updates Rofi colors and its compatibility environment file. | No |
| firefox | Updates selected profiles' browser CSS, startup preferences and local themed home pages. | No |
| librewolf | Provides the Firefox-compatible integration using separate LibreWolf profile discovery and managed blocks. | No |
| clementine | Updates Clementine's application-specific compatibility colors. | Yes, when qt6ct is installed. |
| sioyek | Updates interface colors while preserving PDF recoloring settings. | Yes, when qt6ct is installed. |
| pcmanfm-qt | Uses the shared qt6ct palette without generating an application stylesheet or special launch command. | Yes, when qt6ct is installed. |
| qtile | Reloads the installed Qtile palette snippet, which reads chthm's shared palette snapshot. | Not applicable. |
| qutebrowser | Updates its palette variables, native website appearance and local themed blank page. | Yes, when qt6ct is installed. |

`qt6ct` is a registered platform adapter rather than a fifteenth default
application. chthm activates it automatically when an installed, selected Qt 6
target needs it and qt6ct itself is installed.

A target is available only when chthm finds one of its executables, an executable
path supplied by the user, or a recognized installed Flatpak desktop entry.
An old configuration file is not installation evidence. Missing applications
are silently skipped without creating or editing their files. `--targets`,
`--add-targets` and application destination options never bypass this check.
Firefox and LibreWolf additionally need a usable profile before their adapters
can plan any writes. chthm does not install target applications.

Create ~/.config/chthm/config.toml to override defaults. For example:

```
default_theme = "kimbie_dark"
themes_dir = "~/.local/share/chthm/themes"
state_file = "~/.local/state/chthm/current.toml"
reload = true
targets = ["alacritty", "rofi", "qtile"]
```

### Selecting an additional registered target

Omit targets to inherit the fourteen defaults. A saved targets array replaces the
defaults, and --targets replaces that array for one invocation. Use
additional_targets or --add-targets to extend rather than replace the selection:

```
additional_targets = ["qt6ct"]
```

Selection still skips absent applications. Invalid themes or malformed
configuration files still report errors.

`additional_targets` and `--add-targets` accept registered target names;
they do not teach chthm how to edit an unknown application's configuration. For
an installed registered application whose executable is not on PATH, such as a
custom AppImage, provide one or more executable names or paths. This supplies
installation evidence; it does not define a new adapter:

```
[target_commands]
sioyek = ["/opt/sioyek/sioyek"]
```

### Adding support for a new application

A previously unknown application needs a small adapter because each program has
its own configuration syntax and safe files to edit. Add the adapter to
`src/chthm/targets.py` in two parts:

1. Define a plan function. It receives the selected `Theme` and resolved
   configuration, and returns a list of planned writes plus optional dry-run
   notes. A write is `(destination, content, backup_existing_file)`. The plan
   function should not install software, start the application or write files
   directly.
2. Add a `Target` entry to the `TARGETS` registry with the executable names
   that prove the application is installed.

For example, a simple text-configuration adapter could look like this:

```
def myapp_plan(theme, config):
    destination = config["config_root"] / "myapp/colors.conf"
    colors = theme.exports
    content = (
        f'background={colors["CHTHM_BACKGROUND"]}\n'
        f'foreground={colors["CHTHM_FOREGROUND"]}\n'
    )
    return [(destination, content, True)], ["MyApp: colors updated"]
```

Register it alongside the existing entries:

```
Target("myapp", myapp_plan, ("myapp",)),
```

The target is then selectable without replacing the defaults:

```
chthm kimbie_dark --add-targets myapp
```

Or persistently:

```
additional_targets = ["myapp"]
```

Use `default=True` on the `Target` entry only when the application should
join the built-in default set. Use `qt6ct_covered=True` when the installed
application is Qt 6 based and should automatically request the shared qt6ct
palette. For a Flatpak, add an `installed_paths` probe, for example
`installed_paths=flatpak_desktop("com.example.MyApp")`. If the adapter needs a
custom destination setting, add and validate that setting in
`src/chthm/cli.py`. If it needs an explicit live-reload action, extend the
reload handling as well. Add tests covering installed, absent and dry-run cases
so an old configuration file can never make an absent application appear
installed.

Even with no available targets, chthm saves the palette snapshot and can export
shell colors. `targets = []` saves state without application output files;
use `reload = false` as well to disable reload hooks.

Installer palette-snippet integration for installed Qtile and qutebrowser
remains independent of the runtime targets setting, but it also requires an
existing config.py and never creates one for an absent application.

Additional destination settings are available:

| Setting | Default or meaning |
| --- | --- |
| alacritty_dir | ~/.config/alacritty |
| ghostty_config | ~/.config/ghostty/config.ghostty, or an existing legacy ~/.config/ghostty/config |
| ghostty_theme | ~/.config/ghostty/chthm-colors.conf |
| kitty_config | ~/.config/kitty/kitty.conf |
| kitty_theme | ~/.config/kitty/chthm-theme.conf |
| wezterm_config | An existing ~/.config/wezterm/wezterm.lua, then an existing ~/.wezterm.lua, otherwise ~/.config/wezterm/wezterm.lua |
| wezterm_scheme | ~/.config/wezterm/colors/chthm.toml |
| foot_config | ~/.config/foot/foot.ini |
| foot_theme | ~/.config/foot/chthm.ini |
| zathura_config | ~/.config/zathura/zathurarc |
| rofi_config | ~/.config/rofi/config.rasi |
| rofi_env | ~/.config/rofi/theme.env |
| firefox_root | Override automatic discovery of the Firefox profile registry. |
| firefox_profiles | Array of explicit profile directory paths. |
| librewolf_root | Override automatic discovery of the LibreWolf profile registry. |
| librewolf_profiles | Array of explicit LibreWolf profile directory paths. |
| clementine_config | ~/.config/Clementine/Clementine.conf (compatibility adapter). |
| qt6ct_config | ~/.config/qt6ct/qt6ct.conf |
| qt6ct_palette | ~/.config/qt6ct/colors/chthm.conf |
| sioyek_config | ~/.config/sioyek/prefs_user.config |
| qutebrowser_config | ~/.config/qutebrowser/config.py |
| qutebrowser_page | ~/.local/share/chthm/qutebrowser/blank.html |

Paths accept ~ and environment variables. Corresponding command-line options
use hyphens; --firefox-profile and --librewolf-profile are repeatable. --config
selects a different settings file for the command.

For a custom snapshot location shared with the snippets, set state_file in
the normal ~/.config/chthm/config.toml, honoring XDG_CONFIG_HOME. The snippet
loader reads that file; it does not inherit a command's --config or --state-file
option. Use --themes-dir to select a collection for one command, or themes_dir
in the settings file for a persistent change.

## Qtile and qutebrowser palette snippets

The installer checks these existing files under XDG_CONFIG_HOME, or ~/.config,
only when the corresponding application executable is installed:

* qtile/config.py
* qutebrowser/config.py

It inserts a marked block near the top, after any module docstring and
__future__ imports, so palette variables are available to later definitions.
For a recognized default colors table, it inserts the block immediately after
that table instead.
The rest of the file is preserved. Reinstallation replaces only the marked
block. Existing symlinks and permission bits are retained. Syntax is checked
without executing your configuration. Invalid syntax or malformed markers
stop installation before its file writes.

Both snippets expose:

* chthm_palette: the complete palette, including colors and roles.
* chthm_colors: the color tables, including primary, normal and bright.
* chthm_background: primary background color.
* chthm_foreground: primary foreground color.
* chthm_accent: the accent role.

The standalone loader reads the selected TOML snapshot. It requires Python
3.11 or newer in the application's Python environment, but no import of the
chthm package, Alacritty configuration or shell exports. Missing or invalid
state uses a built-in fallback palette. Each configuration load rereads state.

### Standalone template palettes

A config can start with an ordinary hardcoded palette and use it throughout,
without mentioning chthm or depending on an installed loader:

```
colors = {
    "primary": {"background": "#0a0f14", "foreground": "#98d1ce"},
    "normal": {"blue": "#195465"},
}
```

Use expressions such as colors["primary"]["background"] and
colors["normal"]["blue"] in the application's color settings. The installer
recognizes one top-level literal dictionary assigned to colors, containing
primary background/foreground and optional normal/bright tables with #RRGGBB
values. It preserves that default table and inserts its managed block after
it, including `colors = chthm_colors`. Later settings then use the selected
palette automatically. Removing that block restores the hardcoded defaults.

Other configurations receive the palette variables without automatic rewrites
of their color assignments. Personal loaders and arbitrary hardcoded settings
are preserved. An existing loader that reads Alacritty remains dependent on
Alacritty until you replace its references. No user code is executed to detect
a template palette.

### Qtile example

Use the variables in existing widget or layout definitions:

```
widget_defaults = dict(
    font="sans",
    fontsize=12,
    background=chthm_background,
    foreground=chthm_foreground,
)
layouts = [layout.MonadTall(
    border_focus=chthm_accent,
    border_normal=chthm_background,
)]
```

Adapt these entries inside your current configuration rather than replacing
its complete widget_defaults or layouts definitions. More palette values are
available through expressions such as `chthm_colors["normal"]["blue"]`.

### qutebrowser example

Use the palette for ordinary tabs and invert the selected tab colors:

```
c.colors.tabs.even.bg = chthm_background
c.colors.tabs.even.fg = chthm_foreground
c.colors.tabs.odd.bg = chthm_background
c.colors.tabs.odd.fg = chthm_foreground
c.colors.tabs.selected.even.bg = chthm_foreground
c.colors.tabs.selected.even.fg = chthm_background
c.colors.tabs.selected.odd.bg = chthm_foreground
c.colors.tabs.selected.odd.fg = chthm_background
```

Other interface color assignments can use the same variables. The installer
palette snippet preserves existing browser options and color assignments. The
qutebrowser runtime target additionally manages native website appearance, the blank page
and URL settings described below.

## Application adapters

### Alacritty

The installer can adopt an existing standalone theme.toml containing hardcoded
colors. It saves those colors in ~/.config/alacritty/chthm-colors.toml and
replaces theme.toml with an import of that file. Existing palette selectors
are also supported when their final import points directly to a palette.
The installer updates these files directly; repeated installation does not
duplicate imports. Keep other terminal settings in alacritty.toml: installer
adoption accepts theme.toml files containing only colors and import settings.

Theme changes then update the generated palette and its selector. Keep an
import of theme.toml in alacritty.toml; chthm does not edit that file.
For example, use an absolute path appropriate to your account:

```
[general]
import = ["/home/YOUR_USER/.config/alacritty/theme.toml"]
```

Alacritty's live-reload settings determine when colors appear. The generated
import-file shape also supports older personal palette readers.

### Terminal emulators

The Ghostty, kitty, WezTerm and foot adapters create separate generated palette
files and add only a marked include or selection block to the main application
configuration. Unrelated font, window, key-binding and shell settings remain
in place. Existing files receive `.bak` backups before a changed write, and
repeated theme changes keep exactly one managed block.

Ghostty writes ~/.config/ghostty/chthm-colors.conf and references it from
config.ghostty. If only the older ~/.config/ghostty/config name exists, chthm
uses that file instead. Press Ctrl+Shift+Comma in Ghostty to reload the config, or
restart it. See Ghostty's [configuration reference](https://ghostty.org/docs/config) and [theme format](https://ghostty.org/docs/features/theme).

kitty writes ~/.config/kitty/chthm-theme.conf and includes it from kitty.conf.
kitty normally watches its configuration and reloads the colors automatically;
Ctrl+Shift+F5 requests a manual reload. See kitty's [configuration reference](https://sw.kovidgoyal.net/kitty/conf.html) and [theme documentation](https://sw.kovidgoyal.net/kitty/kittens/themes/).

WezTerm writes the `chthm` color scheme to
~/.config/wezterm/colors/chthm.toml. Its managed Lua block selects that scheme
and adds the generated file to WezTerm's reload watch list. For safety, chthm
does not execute or broadly rewrite Lua: an existing wezterm.lua must contain
exactly one top-level `return NAME` line. A missing config is initialized with
WezTerm's config-builder form; an unsupported existing layout produces an error
before any palette or state file is written. WezTerm normally reloads watched
configuration automatically, and Ctrl+Shift+R requests a manual reload. See
the official [color-scheme guide](https://wezterm.org/config/appearance.html),
[config-file guide](https://wezterm.org/config/files.html) and
[reload-watch function](https://wezterm.org/config/lua/wezterm/add_to_config_reload_watch_list.html).

foot writes ~/.config/foot/chthm.ini with both `[colors-dark]` and
`[colors-light]` so either of foot's active modes receives the selected
palette, then includes it from foot.ini. Restart existing foot terminals after
a change; the user signals switch between already loaded light and dark
palettes rather than rereading the file. See the [foot.ini reference](https://man.archlinux.org/man/foot.ini.5.en) and [foot signal reference](https://dyn.manpages.debian.org/unstable/foot/foot.1.en.html).

All four remain subject to the same installed-only rule as every other target.
A stale config alone is ignored. The `footclient` executable also counts as
foot installation evidence. If an executable has a custom name or location,
add it under `target_commands`; destination options do not bypass the
installation check.

### Zathura

Updates default, status-bar and input-bar foreground/background colors, along
with recolor-lightcolor and recolor-darkcolor. It does not toggle recoloring
on or off. This differs from the Sioyek adapter's interface-only behavior.

### Rofi

Writes literal foreground and background values into the global * block in
config.rasi. Existing @foreground and @background references can use them.
The adapter also writes a compatibility theme.env file containing shell
exports; Rofi does not need environment-variable expressions for these colors.

### Firefox and LibreWolf

Adds application-specific marked blocks to each selected browser profile's
chrome/userChrome.css, chrome/userContent.css and user.js.
The latter enables custom browser stylesheets. Toolbars and unselected tabs
use the background/foreground pair; selected tabs invert the pair. Restart
the affected browser to apply. Browser interface changes can require CSS updates
on future Firefox or LibreWolf releases.

The userContent.css block applies the same background and foreground to the
Firefox or LibreWolf Settings page (about:preferences), including its canvas,
cards, dialogs, inputs and ordinary/deemphasized text. This replaces the
browsers' built-in dark gray Settings surfaces and follows every later theme
change.

The userChrome.css block also applies the palette to browser context menus and
popup panels. Menu surfaces, text, borders, icons and separators use the theme
pair; hovered or keyboard-active menu rows invert the pair in the same style as
the selected tab. Browser chrome and Settings controls use square geometry:
tabs, address/search fields, toolbar buttons, popup panels, menu rows, cards,
dialogs, inputs and buttons have zero-radius corners.

Toolbar address/search fields, their focus states, autocomplete panels, result
rows and one-off search buttons use the theme pair as well. Hovered or selected
results invert it. Firefox Home and New Tab search controls receive the same
background, foreground and square geometry through userContent.css.

Each selected profile also receives a local chthm-home.html blank page. The
page uses the theme's background color with no visible content, scripts,
remote assets or web server. Its foreground uses the theme foreground.
Every theme change updates the page, keeping the same local file URL.

The managed user.js block sets browser.startup.homepage to that URL and
browser.startup.page to 1 so ordinary startup opens the home page. These
preferences take effect when the browser starts; chthm does not restart it
automatically. After the initial restart, reload an already open home page
to see a later color update. The separate new-tab preference is preserved.
See Mozilla's [homepage and startup reference](https://firefox-admin-docs.mozilla.org/reference/policies/homepage/).

Firefox and LibreWolf disable website color overriding
(`browser.display.document_color_use = 1`). The native website appearance
preference advertises light or dark according to the theme background; sites
can choose how to respond. Current Gecko uses standard document colors with
forced colors off, so arbitrary theme hex colors are not applied to websites.
Explicit website colors take precedence. chthm does not inject website CSS,
recolor icons, remove gradients, or add exceptions for particular sites. The
content stylesheet only themes browser-owned Settings, Home and New Tab pages.
See Mozilla's [website appearance documentation](https://support.mozilla.org/en-US/kb/change-website-appearance-settings-firefox).

Neither browser's fingerprint-resistance settings are changed. LibreWolf may
standardize appearance preferences under its privacy protections; chthm accepts
that behavior instead of forcing custom website colors.

The page stays inside its profile rather than relying on the original theme
file or an external server. Multiple selected profiles each get their own
copy and home URL. Changed existing pages and preferences receive .bak
backups, and unrelated preferences and CSS outside the managed blocks remain.

Firefox profile discovery checks its XDG/native, Flatpak and Snap locations.
LibreWolf discovery checks ~/.librewolf first because the legacy directory takes
precedence when it exists, then $XDG_CONFIG_HOME/librewolf/librewolf and the
Flatpak app directory. See LibreWolf's [Linux profile documentation](https://librewolf.net/docs/faq/#how-can-i-recover-my-data-after-using-the-refresh-librewolf-option).
Ambiguous defaults require an explicit profile. Select one or more profiles:

```
chthm kimbie_dark --firefox-profile /path/to/profile
chthm kimbie_dark --firefox-profile /path/to/first --firefox-profile /path/to/second
chthm kimbie_dark --librewolf-profile /path/to/profile
chthm kimbie_dark --librewolf-profile /path/to/first --librewolf-profile /path/to/second
```

### Shared Qt 6 colors through qt6ct

When qt6ct is already installed, chthm generates one shared
palette in ~/.config/qt6ct/colors/chthm.conf and selects it in qt6ct.conf with
custom_palette=true. Existing fonts, icons, style and other preferences are
preserved; a new config uses Fusion. The palette defines all 22 modern Qt
color roles for active, inactive and disabled widgets. Normal windows, inputs
and buttons use the background/foreground pair; selected items invert it.
Disabled text and shading are derived from the theme, with links and accent
colors taken from its semantic palette.

PCManFM-Qt is a default target whose only color integration is the shared
platform palette; chthm does not generate PCManFM-Qt stylesheets or themed
launch commands during theme changes. Launch PCManFM-Qt normally, including
from Qtile:

```
lazy.spawn("pcmanfm-qt")
```

When qt6ct and at least one of the four default Qt 6 applications are installed,
the installer seeds the shared palette. It removes
the known generated stylesheet argument from PCManFM-Qt's user desktop entry
and removes the old generated stylesheet. Other application settings and
custom stylesheets are preserved. Remove any manually added -stylesheet
arguments from your own launch commands if they override the shared palette.

In the current Arch application set, PCManFM-Qt, qutebrowser, Sioyek and
Clementine are Qt 6 builds. When any of these installed targets is selected,
chthm automatically applies the qt6ct target if qt6ct is installed. qutebrowser,
Sioyek and Clementine retain their application-specific adapters because they
also control surfaces or palettes that do not simply inherit QPalette.

qt6ct is a process-wide platform theme, not an application-specific stylesheet.
Its palette can therefore affect every Qt 6 application that inherits qt6ct,
including Qt 6 applications outside the selected target list. A dry run reports
this when it would enable the shared layer. Use --no-qt6ct for one invocation,
or set `qt6ct_integration = false` in config.toml, if that broader effect is
not wanted. Older or differently packaged builds that use Qt 5 do not inherit
qt6ct.

The platform plugin must be selected before a Qt application starts. The
installer writes an environment.d entry; that entry enables
QT_QPA_PLATFORMTHEME=qt6ct in the installed zsh integration and managed Qtile
block. The integration and Qtile block do not enable qt6ct without the entry.
These steps are conditional on qt6ct and at least one default Qt 6 target
application being installed.
Reload Qtile or log out and back in, then restart existing Qt applications
once to load the plugin. User services read the environment entry according
to their session setup. A .zshrc export alone does not update an already
running desktop session.

On later color changes, compatible running Qt widgets can refresh through
qt6ct's configuration watcher. chthm updates a palette signature in qt6ct.conf
so a changed scheme reliably triggers that watcher. The native plugin was
verified to reload a test widget without restarting it. Some applications or
custom widgets still need restarting. --no-reload disables chthm's explicit
reload hooks, but does not suppress an application's own file watcher.

Use --targets qt6ct to update only the shared palette and configuration; the
installed-only check still applies. The runtime also maintains the environment.d
entry when it activates qt6ct.
Qt 5 applications require their own integration. Custom QSS, application
palettes and styles which draw their own colors can override qt6ct. See
[qt6ct](https://github.com/trialuser02/qt6ct) and
[Qt's palette documentation](https://doc.qt.io/qt-6/qpalette.html).

The old pcmanfm_qss and pcmanfm_desktop_entry settings and command-line options
remain removed. Keep pcmanfm-qt in a saved application target list; its metadata
now requests the installed shared qt6ct layer automatically.

### Clementine compatibility

The installed Clementine version explicitly builds and sets its own palette;
its System mode is not a general pass-through to an arbitrary qt6ct palette.
The minimal Clementine adapter is therefore retained: it sets the two custom
colors and enables use-custom-set so your selected background and foreground
continue to apply. This is a necessary compatibility exception, not a separate
Qt theme framework. Close Clementine before changing its settings and restart
it to apply. Other settings remain unchanged. Versions that override their
palette can also retain their own selection/accent colors.

### Sioyek

Updates window background, UI text, menus, selected items and status-bar
colors in prefs_user.config. Selected items invert the color pair. PDF page
recoloring settings and modes are preserved. Restart Sioyek to load changes;
which UI color settings are honored depends on the installed Sioyek version.
This small adapter remains necessary: Sioyek explicitly styles its UI and
renders its own drawing area, so these surfaces do not simply inherit a
QPalette. It complements qt6ct while preserving PDF page recoloring. See the
[Sioyek implementation](https://raw.githubusercontent.com/ahrm/sioyek/main/pdf_viewer/main_widget.cpp).

### qutebrowser website appearance and blank page

The qutebrowser target advertises a light/dark website preference derived from
the theme background and disables automatic dark-mode recoloring. Websites
keep their own CSS, icons, text, animations and controls. No website stylesheet
is generated or loaded, and there are no per-site exceptions.

qutebrowser exposes a fallback page background but no matching default text
color. A dark fallback alone makes unstyled black text unreadable, so chthm
keeps the native white fallback. Sites supporting a light/dark preference can
select their own matching palette; this does not give arbitrary sites the
exact theme background. The local blank page and browser interface use the
exact palette colors. See qutebrowser's
[appearance settings](https://qutebrowser.org/doc/help/settings.html#colors.webpage.preferred_color_scheme).

On a theme change, the qutebrowser target writes a local blank HTML page at
~/.local/share/chthm/qutebrowser/blank.html, honoring XDG_DATA_HOME. The entire
page uses the selected background color, with no visible content, scripts,
remote assets or web server. Each successful theme change updates that file.

The target adds or updates a separate marked block at the end of config.py.
It sets url.default_page and url.start_pages to the page's file URL, so empty
new tabs and normal startup use the themed page. It disables automatic webpage
dark-mode recoloring for the local page through a matching file-URL rule.
See qutebrowser's
[URL settings](https://qutebrowser.org/doc/help/settings.html#url.default_page).

Existing configuration text is retained; the managed block follows earlier
URL assignments so it takes effect. Changed existing files receive .bak
backups. An installed qutebrowser without config.py receives a minimal config
which loads autoconfig and sets the blank-page and native website appearance options. Absent applications
are skipped even when explicitly selected or given a custom destination.

To update only qutebrowser:

```
chthm kimbie_dark --targets qutebrowser
```

The generated files and config settings are first created when you apply a
theme, rather than during installation. Default reload behavior requests a
browser restart after writing the files and palette snapshot. With --no-reload,
the files still update. Restart qutebrowser to adopt its native color-scheme settings. Existing tabs retain their URLs and normal
session-restore behavior; they are not redirected to the blank page.

Override locations with qutebrowser_config and qutebrowser_page in config.toml,
or --qutebrowser-config and --qutebrowser-page for one invocation. Explicit
--targets excluding qutebrowser leave its files alone.

## Reload behavior

After writing application output files and the shared snapshot, chthm requests
a Qtile config reload when that target is selected and available. It requests
a qutebrowser restart when that target is selected, the command and pgrep are
available, and a matching process is found.

Use --no-reload or reload = false to disable both hooks. Other applications
follow the restart or launch behavior described above. Hook failures produce
warnings without undoing the written files.

## Adding themes and palette format

Add a theme after installation by copying a TOML file directly into chthm's
user-owned collection. The default collection follows `XDG_DATA_HOME` and is
otherwise `~/.local/share/chthm/themes`:

```
theme_dir="${XDG_DATA_HOME:-$HOME/.local/share}/chthm/themes"
mkdir -p "$theme_dir"
cp -i /path/to/my_theme.toml "$theme_dir/"
```

Collection files must end in `.toml` and must be directly inside that
directory; subdirectories are not scanned. The filename stem is the command-line
theme name, so the example is selected as `my_theme`. Lowercase names using
letters, numbers, hyphens or underscores are recommended. `cp -i` asks before
replacing an existing theme because chthm treats collection files as user data
and does not refresh or overwrite them automatically.

Validate and apply the new theme:

```
chthm list
chthm my_theme --dry-run
chthm my_theme
```

The dry run parses and validates the complete palette and all planned target
output without changing files or reloading applications. An invalid theme is
rejected before any theme-change writes occur.

A theme can also be used directly without copying it into the collection:

```
chthm /absolute/path/to/my_theme.toml --dry-run
chthm /absolute/path/to/my_theme.toml
```

An explicit-path theme does not appear in `chthm list`. To use a different
directory as the persistent collection, configure it and optionally choose its
default theme in `~/.config/chthm/config.toml`:

```
themes_dir = "/path/to/my-themes"
default_theme = "my_theme"
```

For a new or offline installation, import every top-level `.toml` file from a
directory with:

```
python3 install.py --theme-source /path/to/my-themes
```

That option bypasses the upstream collection download and copies only themes
whose filenames are not already present. Later edits should be made in the
installed collection, or copied there deliberately, because rerunning the
installer preserves existing destination files.

A minimal theme needs just two colors:

```
[colors.primary]
background = "#112233"
foreground = "#ddeeff"
```

Optional metadata, ANSI colors and semantic roles can extend it:

```
[theme]
name = "My palette"

[colors.primary]
background = "#112233"
foreground = "#ddeeff"

[colors.normal]
blue = "#5d90cd"
red = "#c87e5a"
yellow = "#e4b581"
green = "#879a6b"

[roles]
accent = "#5d90cd"
```

Colors use #RRGGBB. Missing normal and bright ANSI entries receive fallback
values. The accent, error, warning and success roles derive from normal blue,
red, yellow and green unless explicitly supplied. Alacritty's CellBackground
and CellForeground references and indexed-color arrays are also supported.
Theme metadata is data and is never evaluated as code.

The optional `[theme] name` is the descriptive name exported to applications;
it does not change the collection filename used by `chthm list` and the theme
selection command. Use unique filenames when adding several palettes.

Applying a theme creates a self-contained snapshot with schema_version = 1,
selection metadata, normalized colors and roles. Removing the original theme
file does not break subsequent exports or snapshot readers. Editing a source
theme takes effect when you apply it again.

To add an adapter, implement an output planner and register a Target in
src/chthm/targets.py, including availability detection. Parsing and snapshot
serialization live in theme.py; application text transformations live in
integrations.py, with shared Qt palettes in qt6ct.py and Clementine
compatibility in clementine.py; the CLI coordinates writes and reloads. Installer palette
insertion is shared by the two Python-configured applications.

## Backups and recovery

The installer updates its destination files without creating backup copies.
Palette switches still use sibling .bak files for changed application outputs
and the shared snapshot. Rofi's compatibility theme.env has no automatic backup. Unchanged
files are skipped, retaining their earlier backups.

A .bak file holds the previous changed version, which may already contain a
chthm theme. Inspect it before restoring. Files are replaced atomically one
at a time, preserving existing permission bits and dotfile symlinks. Updates
across applications are not one transaction: a failure can leave earlier files
changed. A dry run validates planned content but does not verify write access.

If colors do not change, check the relevant restart instructions first. For
Qtile and qutebrowser, confirm that your color assignments actually reference
the chthm_* variables. For a missing command, open a new terminal and check
that ~/.local/bin is on PATH. For a missing theme directory, set themes_dir or
rerun installation with a usable collection.

## Uninstall

1. Remove the shell setup block from .zshrc or $ZDOTDIR/.zshrc, including both
   marker lines:

   ```
   # >>> chthm installer >>>
   # <<< chthm installer <<<
   ```

2. Before deleting the loader, remove the palette blocks from the Qtile and
   qutebrowser config.py files, including their markers:

   ```
   # >>> chthm Qtile palette >>>
   # <<< chthm Qtile palette <<<

   # >>> chthm qutebrowser palette >>>
   # <<< chthm qutebrowser palette <<<
   ```

   Remove its separate blank-page/website-appearance block as well:

   ```
   # >>> chthm qutebrowser blank page >>>
   # <<< chthm qutebrowser blank page <<<
   ```

   The generated qutebrowser/blank.html under the chthm data directory can then
   be removed if no longer wanted. Restore
   any preferred URL, dark-mode and website background settings.

   Template configs using colors return to their hardcoded defaults when the
   managed block is removed. Replace any chthm_* variables you adopted directly
   with your own colors, or restore a configuration you saved yourself.

3. Remove the installed commands and shell integration:

   ```
   rm ~/.local/bin/chthm
   rm -r ~/.local/share/chthm/lib
   rm ~/.config/chthm/chthm.zsh
   ```

4. To stop selecting qt6ct for applications, remove the environment.d entry
   at ~/.config/environment.d/60-chthm-qt6ct.conf and any remaining explicit
   QT_QPA_PLATFORMTHEME=qt6ct exports, then start a new desktop session.
   Choose another palette in qt6ct before deleting its generated colors file.
   Keep your fonts, icons and other qt6ct settings if you still use the tool.

5. To undo other application colors, restore appropriate backups or remove
   generated customizations. Firefox and LibreWolf blocks are marked with their
   respective application names in userChrome.css and user.js. Before deleting a
   profile's generated chthm-home.html, remove its managed preference block and
   choose a replacement home/startup setting in the browser, or restore the desired
   preferences. Previously applied user.js preferences can persist after the
   file or block is removed. Restart affected applications after restoring
   settings.

Adjust paths for XDG overrides. Keep or remove the theme collection, state,
settings separately. Open a new terminal after removing shell
integration. Removing the commands alone leaves the last applied colors in
place. For pipx installations, use pipx uninstall chthm for the package and
handle shell integration and application changes separately.

## Development and alternative installation

Run the CLI from the source directory without installing:

```
PYTHONPATH=src python3 -m chthm --help
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The project also exposes chthm as a Python package entry point. Installing the package with pipx does not run install.py, download
themes, configure the shell or add application snippets. Use the bundled
installer when you want those setup steps.

## License

Original chthm code and documentation are released under the Zero-Clause BSD
license; see `LICENSE`. Theme collections downloaded by the installer retain
their upstream licenses, which the installer copies beside the installed
themes. The bundled `themes/kimbie_dark.toml` fallback comes from the
Apache-2.0-licensed alacritty-theme collection; its license is included as
`themes/alacritty-theme.LICENSE` and is copied beside the installed fallback.
