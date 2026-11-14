chthm
=====

.. note::

   **Vibe-coding disclaimer:** this project was "vibe coded" with OpenAI Codex.
   Review and test the code and configuration before relying on it.

Switch Linux desktop colors from a shared TOML palette.

chthm keeps a theme collection and a snapshot of your selected palette in
standard user directories. Application adapters write the colors each program
needs. Qtile and qutebrowser can read the same palette through small snippets
added to their existing Python configurations by the installer.

Themes are independent of Alacritty. The installer uses the
`alacritty/alacritty-theme collection <https://github.com/alacritty/alacritty-theme>`_
as its default source, and you can supply your own TOML files instead.

Requirements
------------

* Linux and Python 3.11 or newer.
* zsh for the automatic shell integration.
* Internet access for the default theme download, or a local theme directory.

The runtime and installer use Python's standard library. Applications are
optional: missing default targets are skipped. Installation and theme changes
run as your normal user without administrator privileges.

Install and update
------------------

From the downloaded project directory, run::

    python3 install.py

Then open a new terminal and choose a theme::

    chthm list
    chthm kimbie_dark --dry-run
    chthm kimbie_dark

The installer:

1. Copies the program into your user data directory and installs commands in
   ~/.local/bin. The downloaded source directory can then be moved or removed.
2. Downloads missing TOML themes from the upstream collection's master branch.
   Existing theme files are kept, including any edits you made to them.
3. Adds a marked block to .zshrc to put ~/.local/bin on PATH and load the shell
   integration. If ZDOTDIR is set, it uses $ZDOTDIR/.zshrc.
4. Adds palette-variable snippets to existing Qtile and qutebrowser config.py
   files. It preserves the other configuration text and updates files directly.
   Missing config.py files are left absent.
5. Adopts an existing Alacritty theme.toml palette or selector: saves its colors
   to chthm-colors.toml and installs the import in theme.toml.
   Missing theme.toml files are left absent during installation.
6. When qt6ct is installed, initializes its shared palette from the saved theme
   (or the built-in fallback), configures the Qt platform environment, and
   removes PCManFM-Qt's previous stylesheet override.

Close Qt applications before installation, especially Clementine, so they do
not overwrite their settings on exit. Installation does not restart applications. Qtile and qutebrowser will read
newly added snippets when their configurations next load. The snippets provide
variables and connect recognized template palettes as described below. Other
color assignments need to adopt those variables explicitly. Existing personal
loaders and hardcoded defaults are preserved.

For an offline installation or a different collection::

    python3 install.py --theme-source /path/to/themes

The directory must contain .toml files directly. This option bypasses the
upstream download and copies missing theme files into chthm's collection.

Rerun the installer after updating the downloaded program. Repeated installation
keeps one shell block and one palette block per application. The installed
program is a copy; editing the downloaded source alone does not update it.
Theme files already present in the destination are not refreshed automatically.

If the download fails, the installer uses available local themes and imports
missing files from ~/.config/alacritty/themes/themes when that older collection
exists. Without any themes, commands can still be installed, but applying a
theme requires supplying a collection first. The installer also attempts to
migrate an older Alacritty selection into chthm's state when no snapshot exists.
Existing state is preserved, and an unsuccessful migration produces a warning.

Files and directories
---------------------

These are the default locations:

.. list-table::
   :header-rows: 1
   :widths: 48 52

   * - Path
     - Purpose
   * - ~/.local/bin/chthm
     - Main command.
   * - ~/.local/share/chthm/lib
     - Private installed Python package and standalone palette loader.
   * - ~/.config/qt6ct/colors/chthm.conf
     - Shared Qt 6 color palette.
   * - ~/.config/qt6ct/qt6ct.conf
     - Existing qt6ct settings, with the generated palette selected.
   * - ~/.config/environment.d/60-chthm-qt6ct.conf
     - Platform-theme environment for user services and sessions which load it.
   * - ~/.local/share/chthm/themes
     - User-owned TOML theme collection.
   * - ~/.local/share/chthm/themes/.sources/alacritty-theme
     - Upstream source information and license copied with the download.
   * - ~/.local/share/chthm/qutebrowser/blank.html
     - Generated blank page using the selected background color.
   * - ~/.local/state/chthm/current.toml
     - Selected theme metadata and resolved palette snapshot.
   * - ~/.config/chthm/config.toml
     - Optional user settings; create this file when needed.
   * - ~/.config/chthm/chthm.zsh
     - Installed shell integration.

XDG_DATA_HOME, XDG_CONFIG_HOME and XDG_STATE_HOME override the corresponding
data, configuration and state roots. The command directory remains
~/.local/bin. There is no dependency on the location of the downloaded project.

Everyday commands
-----------------

List themes in readable columns, with the current source file marked::

    chthm list

Print one name per line for scripts or selectors::

    chthm list --plain

Apply a theme by collection filename or explicit path::

    chthm kimbie_dark
    chthm /path/to/custom.toml

Preview planned file updates without writes or reloads::

    chthm kimbie_dark --dry-run

Apply without requesting application reloads::

    chthm kimbie_dark --no-reload

Choose targets for one invocation::

    chthm kimbie_dark --targets alacritty,rofi

Show the available options::

    chthm --help

Running chthm without a theme argument applies default_theme, initially
kimbie_dark. It does not reapply the saved current selection.

The zsh function exports the selected colors into the current shell. Running
``command chthm`` bypasses that function and still updates files, but cannot
change its parent shell's environment. ``chthm exports`` reads palette exports
without changing files or restarting applications. Shell startup uses this
read-only operation. Common exported names include CHTHM_BACKGROUND,
CHTHM_FOREGROUND, CHTHM_THEME, CHTHM_COLORS_NORMAL_BLUE and CHTHM_ROLES_ACCENT.

Configuration and target selection
----------------------------------

All nine registered targets are selected by default: alacritty, zathura,
rofi, firefox, clementine, sioyek, qt6ct, qtile and qutebrowser. An application is
available when its executable is found or its relevant configuration exists.
Missing defaults are reported and skipped without creating application files.
Firefox also needs a usable profile.

Create ~/.config/chthm/config.toml to override defaults. For example::

    default_theme = "kimbie_dark"
    themes_dir = "~/.local/share/chthm/themes"
    state_file = "~/.local/state/chthm/current.toml"
    reload = true
    targets = ["alacritty", "rofi", "qtile"]

Omit targets to inherit all registered defaults. A saved targets array replaces
the defaults, and --targets replaces that array for one invocation. A saved
array still skips absent applications. Explicit CLI targets and explicit
application destination settings allow deliberate preconfiguration even when
an application is absent. Invalid themes or malformed configuration files
still report errors.

Even with no available targets, chthm saves the palette snapshot and can export
shell colors. ``targets = []`` saves state without application output files;
use ``reload = false`` as well to disable reload hooks.

qutebrowser is a selectable target and is included in the defaults. If you
saved a target list before it was added, add qutebrowser or remove that list
to inherit the defaults. Installer palette-snippet integration for Qtile and
qutebrowser remains independent of the runtime targets setting.

Additional destination settings are available:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Setting
     - Default or meaning
   * - alacritty_dir
     - ~/.config/alacritty
   * - zathura_config
     - ~/.config/zathura/zathurarc
   * - rofi_config
     - ~/.config/rofi/config.rasi
   * - rofi_env
     - ~/.config/rofi/theme.env
   * - firefox_root
     - Override automatic discovery of the Firefox profile registry.
   * - firefox_profiles
     - Array of explicit profile directory paths.
   * - clementine_config
     - ~/.config/Clementine/Clementine.conf (compatibility adapter).
   * - qt6ct_config
     - ~/.config/qt6ct/qt6ct.conf
   * - qt6ct_palette
     - ~/.config/qt6ct/colors/chthm.conf
   * - sioyek_config
     - ~/.config/sioyek/prefs_user.config
   * - qutebrowser_config
     - ~/.config/qutebrowser/config.py
   * - qutebrowser_page
     - ~/.local/share/chthm/qutebrowser/blank.html

Paths accept ~ and environment variables. Corresponding command-line options
use hyphens; --firefox-profile is repeatable. --config selects a different
settings file for the command.

For a custom snapshot location shared with the snippets, set state_file in
the normal ~/.config/chthm/config.toml, honoring XDG_CONFIG_HOME. The snippet
loader reads that file; it does not inherit a command's --config or --state-file
option. Use --themes-dir to select a collection for one command, or themes_dir
in the settings file for a persistent change.

Qtile and qutebrowser palette snippets
--------------------------------------

The installer checks these existing files under XDG_CONFIG_HOME, or ~/.config:

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

Standalone template palettes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A config can start with an ordinary hardcoded palette and use it throughout,
without mentioning chthm or depending on an installed loader::

    colors = {
        "primary": {"background": "#0a0f14", "foreground": "#98d1ce"},
        "normal": {"blue": "#195465"},
    }

Use expressions such as colors["primary"]["background"] and
colors["normal"]["blue"] in the application's color settings. The installer
recognizes one top-level literal dictionary assigned to colors, containing
primary background/foreground and optional normal/bright tables with #RRGGBB
values. It preserves that default table and inserts its managed block after
it, including ``colors = chthm_colors``. Later settings then use the selected
palette automatically. Removing that block restores the hardcoded defaults.

Other configurations receive the palette variables without automatic rewrites
of their color assignments. Personal loaders and arbitrary hardcoded settings
are preserved. An existing loader that reads Alacritty remains dependent on
Alacritty until you replace its references. No user code is executed to detect
a template palette.

Qtile example
~~~~~~~~~~~~~

Use the variables in existing widget or layout definitions::

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

Adapt these entries inside your current configuration rather than replacing
its complete widget_defaults or layouts definitions. More palette values are
available through expressions such as ``chthm_colors["normal"]["blue"]``.

qutebrowser example
~~~~~~~~~~~~~~~~~~~

Use the palette for ordinary tabs and invert the selected tab colors::

    c.colors.tabs.even.bg = chthm_background
    c.colors.tabs.even.fg = chthm_foreground
    c.colors.tabs.odd.bg = chthm_background
    c.colors.tabs.odd.fg = chthm_foreground
    c.colors.tabs.selected.even.bg = chthm_foreground
    c.colors.tabs.selected.even.fg = chthm_background
    c.colors.tabs.selected.odd.bg = chthm_foreground
    c.colors.tabs.selected.odd.fg = chthm_background

Other interface color assignments can use the same variables. The installer
palette snippet preserves existing browser options and color assignments. The qutebrowser runtime target additionally manages the blank
page and URL settings described below.

Application adapters
--------------------

Alacritty
~~~~~~~~~

The installer can adopt an existing standalone theme.toml containing hardcoded
colors. It saves those colors in ~/.config/alacritty/chthm-colors.toml and
replaces theme.toml with an import of that file. Existing palette selectors
are also supported when their final import points directly to a palette.
The installer updates these files directly; repeated installation does not
duplicate imports. Keep other terminal settings in alacritty.toml: installer
adoption accepts theme.toml files containing only colors and import settings.

Theme changes then update the generated palette and its selector. Keep an
import of theme.toml in alacritty.toml; chthm does not edit that file.
For example, use an absolute path appropriate to your account::

    [general]
    import = ["/home/YOUR_USER/.config/alacritty/theme.toml"]

Alacritty's live-reload settings determine when colors appear. The generated
import-file shape also supports older personal palette readers.

Zathura
~~~~~~~

Updates default, status-bar and input-bar foreground/background colors, along
with recolor-lightcolor and recolor-darkcolor. It does not toggle recoloring
on or off. This differs from the Sioyek adapter's interface-only behavior.

Rofi
~~~~

Writes literal foreground and background values into the global * block in
config.rasi. Existing @foreground and @background references can use them.
The adapter also writes a compatibility theme.env file containing shell
exports; Rofi does not need environment-variable expressions for these colors.

Firefox
~~~~~~~

Adds marked blocks to the selected profile's chrome/userChrome.css and user.js.
The latter enables custom browser stylesheets. Toolbars and unselected tabs
use the background/foreground pair; selected tabs invert the pair. Restart
Firefox to apply. Browser interface changes can require CSS updates on future
Firefox releases.

Each selected profile also receives a local chthm-home.html blank page. The
page uses the theme's background color with no visible content, scripts,
remote assets or web server. Its foreground uses the theme foreground.
Every theme change updates the page, keeping the same local file URL.

The managed user.js block sets browser.startup.homepage to that URL and
browser.startup.page to 1 so ordinary startup opens the home page. These
preferences take effect when Firefox starts; chthm does not restart Firefox
automatically. After the initial restart, reload an already open home page
to see a later color update. Firefox's separate new-tab preference is preserved.
See Mozilla's `homepage and startup reference <https://firefox-admin-docs.mozilla.org/reference/policies/homepage/>`_.

The page stays inside its profile rather than relying on the original theme
file or an external server. Multiple selected profiles each get their own
copy and home URL. Changed existing pages and preferences receive .bak
backups, and unrelated preferences and CSS outside the managed blocks remain.

Profile discovery checks the XDG/native, Flatpak and Snap Firefox locations.
Ambiguous defaults require an explicit profile. Select one or more profiles::

    chthm kimbie_dark --firefox-profile /path/to/profile
    chthm kimbie_dark --firefox-profile /path/to/first --firefox-profile /path/to/second

Shared Qt 6 colors through qt6ct
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Install qt6ct alongside your Qt 6 applications. chthm generates one shared
palette in ~/.config/qt6ct/colors/chthm.conf and selects it in qt6ct.conf with
custom_palette=true. Existing fonts, icons, style and other preferences are
preserved; a new config uses Fusion. The palette defines all 22 modern Qt
color roles for active, inactive and disabled widgets. Normal windows, inputs
and buttons use the background/foreground pair; selected items invert it.
Disabled text and shading are derived from the theme, with links and accent
colors taken from its semantic palette.

This replaces the PCManFM-Qt adapter and supplies a common palette to other
Qt 6 applications that follow the platform theme. chthm no longer generates
PCManFM-Qt stylesheets or themed launch commands during theme changes. Launch PCManFM-Qt normally, including
from Qtile::

    lazy.spawn("pcmanfm-qt")

The installer seeds the shared palette. It removes
the known generated stylesheet argument from PCManFM-Qt's user desktop entry
and removes the old generated stylesheet. Other application settings and
custom stylesheets are preserved. Remove any manually added -stylesheet
arguments from your own launch commands if they override the shared palette.

The platform plugin must be selected before a Qt application starts. The
installer writes an environment.d entry, enables QT_QPA_PLATFORMTHEME=qt6ct
in the installed zsh integration, and adds the environment setup to the
managed Qtile block. These steps are conditional on qt6ct being installed.
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

Use --targets qt6ct to update only the shared palette and configuration.
Qt 5 applications require their own integration. Custom QSS, application
palettes and styles which draw their own colors can override qt6ct. See
`qt6ct <https://github.com/trialuser02/qt6ct>`_ and
`Qt's palette documentation <https://doc.qt.io/qt-6/qpalette.html>`_.

For upgrades, replace pcmanfm-qt in a saved targets array with qt6ct. The old
pcmanfm_qss and pcmanfm_desktop_entry settings and command-line options have
been removed.

Clementine compatibility
~~~~~~~~~~~~~~~~~~~~~~~

The installed Clementine version explicitly builds and sets its own palette;
its System mode is not a general pass-through to an arbitrary qt6ct palette.
The minimal Clementine adapter is therefore retained: it sets the two custom
colors and enables use-custom-set so your selected background and foreground
continue to apply. This is a necessary compatibility exception, not a separate
Qt theme framework. Close Clementine before changing its settings and restart
it to apply. Other settings remain unchanged. Versions that override their
palette can also retain their own selection/accent colors.

Sioyek
~~~~~~

Updates window background, UI text, menus, selected items and status-bar
colors in prefs_user.config. Selected items invert the color pair. PDF page
recoloring settings and modes are preserved. Restart Sioyek to load changes;
which UI color settings are honored depends on the installed Sioyek version.
This small adapter remains necessary: Sioyek explicitly styles its UI and
renders its own drawing area, so these surfaces do not simply inherit a
QPalette. It complements qt6ct while preserving PDF page recoloring. See the
`Sioyek implementation <https://raw.githubusercontent.com/ahrm/sioyek/main/pdf_viewer/main_widget.cpp>`_.

qutebrowser blank page
~~~~~~~~~~~~~~~~~~~~~~

On a theme change, the qutebrowser target writes a local blank HTML page at
~/.local/share/chthm/qutebrowser/blank.html, honoring XDG_DATA_HOME. The entire
page uses the selected background color, with no visible content, scripts,
remote assets or web server. Each successful theme change updates that file.

The target adds or updates a separate marked block at the end of config.py.
It sets url.default_page and url.start_pages to the page's file URL, so empty
new tabs and normal startup use the themed page. It disables automatic webpage
dark-mode recoloring for the local page through a matching file-URL rule,
while leaving normal website settings unchanged. See qutebrowser's
`URL settings <https://qutebrowser.org/doc/help/settings.html#url.default_page>`_.

Existing configuration text is retained; the managed block follows earlier
URL assignments so it takes effect. Changed existing files receive .bak
backups. An installed qutebrowser without config.py receives a minimal config
which loads autoconfig and sets the blank-page options. Absent applications
are skipped unless explicitly selected.

To update only qutebrowser::

    chthm kimbie_dark --targets qutebrowser

The generated file and config settings are first created when you apply a
theme, rather than during installation. Default reload behavior requests a
browser restart after writing the files and palette snapshot. With --no-reload,
the HTML still updates. Reload the browser config with :config-source to adopt
new URL settings, and reload an already open blank page to see its new color.
Other tabs keep their own content and normal session-restore
behavior. No existing tabs are redirected to the blank page.

Override locations with qutebrowser_config and qutebrowser_page in config.toml,
or --qutebrowser-config and --qutebrowser-page for one invocation. Explicit
--targets excluding qutebrowser leave its files alone.

Reload behavior
---------------

After writing application output files and the shared snapshot, chthm requests
a Qtile config reload when that target is selected and available. It requests
a qutebrowser restart when that target is selected, the command and pgrep are
available, and a matching process is found.

Use --no-reload or reload = false to disable both hooks. Other applications
follow the restart or launch behavior described above. Hook failures produce
warnings without undoing the written files.

Theme format and extensions
---------------------------

A minimal theme needs just two colors::

    [colors.primary]
    background = "#112233"
    foreground = "#ddeeff"

Optional metadata, ANSI colors and semantic roles can extend it::

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

Colors use #RRGGBB. Missing normal and bright ANSI entries receive fallback
values. The accent, error, warning and success roles derive from normal blue,
red, yellow and green unless explicitly supplied. Alacritty's CellBackground
and CellForeground references and indexed-color arrays are also supported.
Theme metadata is data and is never evaluated as code.

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

Backups and recovery
--------------------

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

Uninstall
---------

1. Remove the shell setup block from .zshrc or $ZDOTDIR/.zshrc, including both
   marker lines::

       # >>> chthm installer >>>
       # <<< chthm installer <<<

2. Before deleting the loader, remove the palette blocks from the Qtile and
   qutebrowser config.py files, including their markers::

       # >>> chthm Qtile palette >>>
       # <<< chthm Qtile palette <<<

       # >>> chthm qutebrowser palette >>>
       # <<< chthm qutebrowser palette <<<

   Remove its separate blank-page block as well::

       # >>> chthm qutebrowser blank page >>>
       # <<< chthm qutebrowser blank page <<<

   The generated qutebrowser/blank.html under the chthm data directory can then
   be removed if no longer wanted. Restore any preferred URL settings.

   Template configs using colors return to their hardcoded defaults when the
   managed block is removed. Replace any chthm_* variables you adopted directly
   with your own colors, or restore a configuration you saved yourself.

3. Remove the installed commands and shell integration::

       rm ~/.local/bin/chthm
       rm -r ~/.local/share/chthm/lib
       rm ~/.config/chthm/chthm.zsh

4. To stop selecting qt6ct for applications, remove the environment.d entry
   at ~/.config/environment.d/60-chthm-qt6ct.conf and any remaining explicit
   QT_QPA_PLATFORMTHEME=qt6ct exports, then start a new desktop session.
   Choose another palette in qt6ct before deleting its generated colors file.
   Keep your fonts, icons and other qt6ct settings if you still use the tool.

5. To undo other application colors, restore appropriate backups or remove
   generated customizations. Firefox blocks are marked chthm:begin firefox
   through chthm:end firefox in userChrome.css and user.js. Before deleting a
   profile's generated chthm-home.html, remove its managed preference block and
   choose a replacement home/startup setting in Firefox, or restore the desired
   preferences. Previously applied user.js preferences can persist after the
   file or block is removed. Restart affected applications after restoring
   settings.

Adjust paths for XDG overrides. Keep or remove the theme collection, state,
settings separately. Open a new terminal after removing shell
integration. Removing the commands alone leaves the last applied colors in
place. For pipx installations, use pipx uninstall chthm for the package and
handle shell integration and application changes separately.

Development and alternative installation
----------------------------------------

Run the CLI from the source directory without installing::

    PYTHONPATH=src python3 -m chthm --help
    PYTHONPATH=src python3 -m unittest discover -s tests -v

The project also exposes chthm as a Python package entry point. Installing the package with pipx does not run install.py, download
themes, configure the shell or add application snippets. Use the bundled
installer when you want those setup steps.

License
-------

Original chthm code and documentation are released under the Zero-Clause BSD
license; see ``LICENSE``. Theme collections downloaded by the installer retain
their upstream licenses, which the installer copies beside the installed
themes.
