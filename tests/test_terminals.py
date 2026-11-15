import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main


THEME = '''[theme]
name = "terminal-test"

[colors.primary]
background = "#010203"
foreground = "#f1f2f3"

[colors.normal]
black = "#101010"
red = "#202020"
green = "#303030"
yellow = "#404040"
blue = "#505050"
magenta = "#606060"
cyan = "#707070"
white = "#808080"

[colors.bright]
black = "#111111"
red = "#212121"
green = "#313131"
yellow = "#414141"
blue = "#515151"
magenta = "#616161"
cyan = "#717171"
white = "#818181"
'''


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.theme = self.root / "theme.toml"
        self.theme.write_text(THEME)
        environment = patch.dict(os.environ, {
            "HOME": str(self.root),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.state),
            "XDG_DATA_HOME": str(self.root / "data"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        commands = patch("chthm.cli.shutil.which", side_effect=self.which)
        commands.start()
        self.addCleanup(commands.stop)

    @staticmethod
    def which(name, **kwargs):
        if name in {"ghostty", "kitty", "wezterm", "foot", "footclient"}:
            return "/usr/bin/" + name
        return None

    def run_cli(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = main([str(self.theme), "--no-reload", *args])
        return result, output.getvalue(), error.getvalue()

    def seed_configs(self):
        files = {
            self.config / "ghostty/config.ghostty": "font-family = Keep Me\n",
            self.config / "kitty/kitty.conf": "font_family Keep Me\n",
            self.config / "wezterm/wezterm.lua": (
                "local wezterm = require 'wezterm'\n"
                "local config = wezterm.config_builder()\n"
                "config.font_size = 12\n"
                "return config\n"),
            self.config / "foot/foot.ini": "[main]\nfont=Keep Me\n\n[scrollback]\nlines=1000\n",
        }
        for filename, content in files.items():
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text(content)
        return files

    def test_all_terminal_formats_preserve_settings_and_repeat_cleanly(self):
        seeded = self.seed_configs()
        result, _, error = self.run_cli("--targets", "ghostty,kitty,wezterm,foot")
        self.assertEqual(result, 0, error)

        ghost = (self.config / "ghostty/chthm-colors.conf").read_text()
        self.assertIn("background = #010203", ghost)
        self.assertIn("palette = 0=#101010", ghost)
        self.assertIn("palette = 15=#818181", ghost)
        ghost_config = self.config / "ghostty/config.ghostty"
        self.assertIn("font-family = Keep Me", ghost_config.read_text())
        self.assertIn('config-file = "' + str(self.config / "ghostty/chthm-colors.conf") + '"',
                      ghost_config.read_text())

        kitty = (self.config / "kitty/chthm-theme.conf").read_text()
        self.assertIn("background #010203", kitty)
        self.assertIn("color0 #101010", kitty)
        self.assertIn("color15 #818181", kitty)
        kitty_config = self.config / "kitty/kitty.conf"
        self.assertIn("font_family Keep Me", kitty_config.read_text())
        self.assertIn("include " + str(self.config / "kitty/chthm-theme.conf"), kitty_config.read_text())

        wezterm = (self.config / "wezterm/colors/chthm.toml").read_text()
        self.assertIn('background = "#010203"', wezterm)
        self.assertIn('ansi = ["#101010", "#202020"', wezterm)
        self.assertIn('brights = ["#111111", "#212121"', wezterm)
        wezterm_config = self.config / "wezterm/wezterm.lua"
        wezterm_text = wezterm_config.read_text()
        self.assertIn("config.font_size = 12", wezterm_text)
        self.assertIn("wezterm.add_to_config_reload_watch_list", wezterm_text)
        self.assertIn('config.color_scheme = "chthm"', wezterm_text)
        self.assertLess(wezterm_text.index("-- >>> chthm"), wezterm_text.index("return config"))

        foot = (self.config / "foot/chthm.ini").read_text()
        self.assertEqual(foot.count("[colors-dark]"), 1)
        self.assertEqual(foot.count("[colors-light]"), 1)
        self.assertIn("background=010203", foot)
        self.assertIn("regular0=101010", foot)
        self.assertIn("bright7=818181", foot)
        self.assertNotIn("#", foot)
        foot_config = self.config / "foot/foot.ini"
        self.assertIn("font=Keep Me", foot_config.read_text())
        self.assertIn("lines=1000", foot_config.read_text())
        self.assertIn("include=" + str(self.config / "foot/chthm.ini"), foot_config.read_text())
        self.assertEqual(error, "")

        for filename, original in seeded.items():
            self.assertEqual(Path(str(filename) + ".bak").read_text(), original)

        result, _, error = self.run_cli("--targets", "ghostty,kitty,wezterm,foot")
        self.assertEqual(result, 0, error)
        for filename in (ghost_config, kitty_config, wezterm_config, foot_config):
            self.assertEqual(filename.read_text().count(">>> chthm"), 1)
            self.assertEqual(filename.read_text().count("<<< chthm"), 1)

    def test_generated_palettes_are_backed_up_when_the_theme_changes(self):
        result, _, error = self.run_cli("--targets", "ghostty,kitty,wezterm,foot")
        self.assertEqual(result, 0, error)
        generated = [
            self.config / "ghostty/chthm-colors.conf",
            self.config / "kitty/chthm-theme.conf",
            self.config / "wezterm/colors/chthm.toml",
            self.config / "foot/chthm.ini",
        ]
        previous = {filename: filename.read_text() for filename in generated}
        self.theme.write_text(THEME.replace("#010203", "#abcdef"))
        result, _, error = self.run_cli("--targets", "ghostty,kitty,wezterm,foot")
        self.assertEqual(result, 0, error)
        for filename in generated:
            self.assertEqual(Path(str(filename) + ".bak").read_text(), previous[filename])
            self.assertIn("abcdef", filename.read_text())

    def test_dry_run_reports_terminal_files_without_writing(self):
        result, _, error = self.run_cli("--targets", "ghostty,kitty,wezterm,foot", "--dry-run")
        self.assertEqual(result, 0, error)
        for relative in ("ghostty/chthm-colors.conf", "kitty/chthm-theme.conf",
                         "wezterm/colors/chthm.toml", "foot/chthm.ini"):
            self.assertIn(str(self.config / relative), error)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.state.exists())

    def test_stale_configs_do_not_activate_missing_terminals(self):
        self.seed_configs()
        with patch("chthm.cli.shutil.which", return_value=None):
            result, _, error = self.run_cli("--targets", "ghostty,kitty,wezterm,foot")
        self.assertEqual(result, 0, error)
        self.assertNotIn("chthm", (self.config / "ghostty/config.ghostty").read_text())
        self.assertNotIn("chthm", (self.config / "kitty/kitty.conf").read_text())
        self.assertNotIn("chthm", (self.config / "wezterm/wezterm.lua").read_text())
        self.assertNotIn("chthm", (self.config / "foot/foot.ini").read_text())
        self.assertFalse((self.config / "ghostty/chthm-colors.conf").exists())
        self.assertEqual(error, "")

    def test_ghostty_uses_existing_legacy_config_name(self):
        legacy = self.config / "ghostty/config"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("font-family = Legacy\n")
        result, _, error = self.run_cli("--targets", "ghostty")
        self.assertEqual(result, 0, error)
        self.assertIn(">>> chthm ghostty", legacy.read_text())
        self.assertFalse((self.config / "ghostty/config.ghostty").exists())

    def test_wezterm_ignores_return_examples_and_rejects_ambiguous_lua(self):
        target = self.config / "wezterm/wezterm.lua"
        target.parent.mkdir(parents=True)
        target.write_text("""local wezterm = require 'wezterm'
local config = wezterm.config_builder()
local example = [[return fake]]
-- return commented
return config
""")
        result, _, error = self.run_cli("--targets", "wezterm")
        self.assertEqual(result, 0, error)
        self.assertEqual(target.read_text().count(">>> chthm"), 1)

        target.write_text("return first\nreturn second\n")
        palette = self.config / "wezterm/colors/chthm.toml"
        palette.unlink()
        state = self.state / "chthm/current.toml"
        state.unlink()
        result, _, error = self.run_cli("--targets", "wezterm")
        self.assertEqual(result, 1)
        self.assertIn("exactly one top-level 'return NAME'", error)
        self.assertFalse(palette.exists())
        self.assertFalse(state.exists())

    def test_malformed_managed_block_cannot_publish_palette_or_state(self):
        target = self.config / "kitty/kitty.conf"
        target.parent.mkdir(parents=True)
        original = "font_family Keep\n# >>> chthm kitty colors >>>\n"
        target.write_text(original)
        result, _, error = self.run_cli("--targets", "kitty")
        self.assertEqual(result, 1)
        self.assertIn("Malformed chthm block: kitty colors", error)
        self.assertEqual(target.read_text(), original)
        self.assertFalse((self.config / "kitty/chthm-theme.conf").exists())
        self.assertFalse((self.state / "chthm/current.toml").exists())

    def test_custom_terminal_destinations_are_supported(self):
        destinations = {name: self.root / "custom" / name for name in (
            "ghost-main", "ghost-theme", "kitty-main", "kitty-theme",
            "wez-main", "wez-theme", "foot-main", "foot-theme")}
        arguments = ["--targets", "ghostty,kitty,wezterm,foot"]
        for option, key in (
                ("--ghostty-config", "ghost-main"), ("--ghostty-theme", "ghost-theme"),
                ("--kitty-config", "kitty-main"), ("--kitty-theme", "kitty-theme"),
                ("--wezterm-config", "wez-main"), ("--wezterm-scheme", "wez-theme"),
                ("--foot-config", "foot-main"), ("--foot-theme", "foot-theme")):
            arguments.extend((option, str(destinations[key])))
        result, _, error = self.run_cli(*arguments)
        self.assertEqual(result, 0, error)
        self.assertTrue(all(filename.is_file() for filename in destinations.values()))


if __name__ == "__main__":
    unittest.main()
