import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main
from chthm.integrations import (firefox_css, firefox_profiles,
                                 firefox_writes, ini_section_text, managed_block,
                                 rofi_text)

VALUES = {"CHTHM_BACKGROUND": "#0a0f14", "CHTHM_FOREGROUND": "#98d1ce"}
OTHER = {"CHTHM_BACKGROUND": "#221a0f", "CHTHM_FOREGROUND": "#d3af86"}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_rofi_rewrites_globals_preserving_widget_and_comments(self):
        old = '''/* * { foreground: env(EXAMPLE, red); } */
configuration { font: "literal * { } ;"; }
* {
 foreground: env(CHTHM_FOREGROUND, #aaaaaa);
 background: env(CHTHM_BACKGROUND, #000000);
 normal-foreground: @foreground;
 selected-normal-background: @foreground;
}
entry { foreground: pink; text-color: @foreground; }
'''
        new = rofi_text(old, VALUES)
        self.assertIn("foreground: #98d1ce;", new)
        self.assertIn("background: #0a0f14;", new)
        self.assertIn("normal-foreground: @foreground;", new)
        self.assertIn("selected-normal-background: @foreground;", new)
        self.assertIn("entry { foreground: pink; text-color: @foreground; }", new)
        self.assertIn("/* * { foreground: env(EXAMPLE, red); } */", new)
        self.assertEqual(rofi_text(new, VALUES), new)
        self.assertNotIn("env(CHTHM_", new)

    def test_rofi_quoted_values_and_missing_keys(self):
        new = rofi_text('* { foreground: "white"; }\n', VALUES)
        self.assertNotIn('"white"', new)
        self.assertIn("foreground: #98d1ce;", new)
        self.assertIn("background: #0a0f14;", new)
        self.assertEqual(rofi_text(new, VALUES), new)
        self.assertIn("background: #0a0f14;", rofi_text("configuration {}\n", VALUES))

    def test_rofi_multiple_global_blocks(self):
        old = '* { foreground:red; background:black; }\n* { foreground:blue; }\n'
        new = rofi_text(old, VALUES)
        self.assertEqual(new.count("foreground:#98d1ce;"), 2)
        self.assertNotIn("foreground:blue", new)

    def test_rofi_malformed_config_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unbalanced"):
            rofi_text("* { foreground: black;", VALUES)


    def test_ini_missing_or_duplicate_sections(self):
        self.assertEqual(ini_section_text("[Appearance]", "Appearance", {"a": "b"}), "[Appearance]\na=b\n")
        self.assertIn("[Appearance]\n", ini_section_text("[Other]\na=b\n", "Appearance", {"custom_palette": "true"}))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            ini_section_text("[Appearance]\na=b\n[Appearance]\nx=y\n", "Appearance", {"custom_palette": "true"})


    def make_profiles(self, extra_install=False):
        (self.root / "release").mkdir()
        (self.root / "old-default").mkdir()
        (self.root / "profiles.ini").write_text('''[Profile0]
Name=default-release
IsRelative=1
Path=release
[Profile1]
Name=default
IsRelative=1
Path=old-default
Default=1
[InstallABC]
Default=release
Locked=1
''')
        if extra_install:
            (self.root / "installs.ini").write_text("[DEF]\nDefault=old-default\n")

    def test_firefox_install_default_wins_over_legacy_default(self):
        self.make_profiles()
        self.assertEqual(firefox_profiles([self.root]), [self.root / "release"])

    def test_firefox_ambiguous_defaults_require_explicit_choice(self):
        self.make_profiles(extra_install=True)
        with self.assertRaisesRegex(ValueError, "Multiple"):
            firefox_profiles([self.root])
        self.assertEqual(firefox_profiles([self.root], [self.root / "old-default"]), [self.root / "old-default"])

    def test_firefox_absolute_profile_and_missing_profile(self):
        external = self.root / "external"
        external.mkdir()
        (self.root / "profiles.ini").write_text(f"[Profile0]\nPath={external}\nIsRelative=0\nDefault=1\n")
        self.assertEqual(firefox_profiles([self.root]), [external])
        self.assertEqual(firefox_profiles([self.root], []), [])
        with self.assertRaisesRegex(ValueError, "not found"):
            firefox_profiles([], [self.root / "missing"])

    def test_firefox_preserves_customizations_and_manages_only_own_block(self):
        profile = self.root / "release"
        (profile / "chrome").mkdir(parents=True)
        old_css = '/* personal */\n#custom { color: pink; }\n'
        old_js = 'user_pref("browser.startup.page", 3);\n'
        (profile / "chrome/userChrome.css").write_text(old_css)
        (profile / "user.js").write_text(old_js)
        writes = firefox_writes(profile, VALUES)
        for target, text, _ in writes:
            if target.name == "userChrome.css":
                self.assertTrue(text.startswith(old_css))
            elif target.name == "userContent.css":
                self.assertTrue(text.startswith("/* chthm:begin firefox */"))
            elif target.suffix == ".js":
                self.assertTrue(text.startswith(old_js))
            target.write_text(text)
        for target, text, _ in firefox_writes(profile, VALUES):
            self.assertEqual(text, target.read_text())
        for target, text, _ in firefox_writes(profile, OTHER):
            if target.suffix == ".css":
                self.assertNotIn("#0a0f14", text)
                self.assertIn("#221a0f", text)
                self.assertEqual(text.count("/* chthm:begin firefox */"), 1)
            elif target.suffix == ".js":
                self.assertIn('user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);', text)
            else:
                self.assertIn('background-color: #221a0f', text)

    def test_selected_firefox_tabs_invert_palette(self):
        css = firefox_css(VALUES)
        self.assertIn('--tab-background-color-selected: #98d1ce !important;', css)
        self.assertIn('--tab-text-color-selected: #0a0f14 !important;', css)
        self.assertIn('.tabbrowser-tab[selected] .tab-background', css)
        self.assertIn('.tabbrowser-tab:not([selected]) .tab-label', css)
        self.assertIn('#nav-bar', css)

    def test_firefox_context_menus_use_and_invert_palette(self):
        css = firefox_css(VALUES)
        self.assertIn('--panel-background-color: #0a0f14 !important;', css)
        self.assertIn('--panel-text-color: #98d1ce !important;', css)
        self.assertIn('menupopup::part(content)', css)
        self.assertIn('background: var(--chthm-background) !important;', css)
        self.assertIn(':is(menu, menuitem):is([_moz-menuactive], :hover):not([disabled])', css)
        self.assertIn('background-color: var(--chthm-foreground) !important;', css)
        self.assertIn('color: var(--chthm-background) !important;', css)
        self.assertIn('menuseparator::before', css)

    def test_firefox_chrome_uses_square_geometry(self):
        css = firefox_css(VALUES)
        self.assertIn('--border-radius-circle: 0px !important;', css)
        self.assertIn('--toolbarbutton-border-radius: 0px !important;', css)
        self.assertIn('--urlbar-border-radius: 0px !important;', css)
        self.assertIn('--panel-menuitem-border-radius: 0px !important;', css)
        self.assertIn('#urlbar-background, #searchbar', css)
        self.assertIn('border-radius: 0 !important;', css)

    def test_firefox_search_fields_and_results_use_palette(self):
        css = firefox_css(VALUES)
        self.assertIn('--toolbar-field-background-color-focus: #0a0f14 !important;', css)
        self.assertIn('--toolbar-field-text-color-focus: #98d1ce !important;', css)
        self.assertIn('--urlbar-background-color: #0a0f14 !important;', css)
        self.assertIn('--urlbarview-background-color-selected: #98d1ce !important;', css)
        self.assertIn('--urlbarview-text-color-selected: #0a0f14 !important;', css)
        self.assertIn('#PopupSearchAutoComplete::part(content)', css)
        self.assertIn('.searchbar-engine-one-off-item', css)

    def test_malformed_managed_block_rejected(self):
        with self.assertRaisesRegex(ValueError, "Malformed"):
            managed_block("/* chthm:begin firefox */\n", "new", "firefox")
        with self.assertRaisesRegex(ValueError, "Malformed"):
            managed_block("/* chthm:end firefox */\n/* chthm:begin firefox */", "new", "firefox")

    def test_all_new_targets_end_to_end_with_backups_and_no_reloads(self):
        config = self.root / "config"
        themes = self.root / "data/chthm/themes"
        themes.mkdir(parents=True)
        (themes / "kimbie_dark.toml").write_text('[colors.primary]\nbackground="#0a0f14"\nforeground="#98d1ce"\n')
        rofi = config / "rofi/config.rasi"
        rofi.parent.mkdir(parents=True)
        old_rofi = "* { foreground:env(CHTHM_FOREGROUND, white); background:black; }\n"
        rofi.write_text(old_rofi)
        clementine = config / "Clementine/Clementine.conf"
        clementine.parent.mkdir()
        old_clementine = "[Appearance]\nuse-custom-set=false\n[Other]\nkeep=true\n"
        clementine.write_text(old_clementine)
        profile = config / "mozilla/firefox/profile"
        profile.mkdir(parents=True)
        profile.parent.joinpath("profiles.ini").write_text("[Profile0]\nIsRelative=1\nPath=profile\nDefault=1\n")
        env = {"HOME": str(self.root), "XDG_CONFIG_HOME": str(config), "XDG_STATE_HOME": str(self.root / "state"), "XDG_DATA_HOME": str(self.root / "data")}
        available = lambda name, config: None if name in {"rofi", "firefox", "qt6ct"} else "not installed"
        with patch.dict(os.environ, env), patch("chthm.cli.reload_apps") as reloads, \
                patch("chthm.cli.unavailable_reason", side_effect=available):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["--targets", "rofi,firefox,qt6ct", "--no-reload"])
            self.assertEqual(code, 0)
            reloads.assert_not_called()
            first_rofi_backup = Path(str(rofi) + ".bak").read_text()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--targets", "rofi,firefox,qt6ct", "--no-reload"]), 0)
        self.assertEqual(first_rofi_backup, old_rofi)
        self.assertEqual(Path(str(rofi) + ".bak").read_text(), old_rofi)
        self.assertEqual(clementine.read_text(), old_clementine)
        self.assertIn("background:#0a0f14", rofi.read_text())
        self.assertIn("[Other]\nkeep=true", clementine.read_text())
        self.assertTrue((profile / "chrome/userChrome.css").exists())
        self.assertTrue((profile / "user.js").exists())
        self.assertTrue((config / "qt6ct/colors/chthm.conf").exists())
        self.assertFalse((config / "chthm/pcmanfm-qt.qss").exists())
        self.assertFalse((self.root / "data/applications/pcmanfm-qt.desktop").exists())

    def test_missing_explicit_firefox_profile_prevents_all_writes(self):
        theme = self.root / "theme.toml"
        theme.write_text('[colors.primary]\nbackground="#0a0f14"\nforeground="#98d1ce"\n')
        config = self.root / "config"
        with patch.dict(os.environ, {"HOME": str(self.root), "XDG_CONFIG_HOME": str(config), "XDG_STATE_HOME": str(self.root / "state")}), \
                patch("chthm.cli.unavailable_reason", side_effect=lambda name, options: None if name == "firefox" else "not installed"):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = main([str(theme), "--firefox-profile", str(self.root / "missing"), "--no-reload"])
        self.assertEqual(result, 1)
        self.assertFalse(config.exists())


if __name__ == "__main__":
    unittest.main()
