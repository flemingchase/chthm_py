import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main


class LibreWolfTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.theme = self.root / "theme.toml"
        self.theme.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        environment = patch.dict(os.environ, {
            "HOME": str(self.root), "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.state), "XDG_DATA_HOME": str(self.root / "data"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        commands = patch("chthm.cli.shutil.which",
                         side_effect=lambda name: "/usr/bin/librewolf" if name == "librewolf" else None)
        commands.start()
        self.addCleanup(commands.stop)

    def apply(self, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main([str(self.theme), "--targets", "librewolf", "--no-reload", *arguments])
        return code, error.getvalue()

    @staticmethod
    def registry(root, profile="profile"):
        selected = root / profile
        selected.mkdir(parents=True)
        (root / "profiles.ini").write_text(
            f"[Profile0]\nName=default\nIsRelative=1\nPath={profile}\nDefault=1\n")
        return selected

    def test_xdg_profile_is_themed_without_touching_firefox(self):
        profile = self.registry(self.config / "librewolf/librewolf")
        original = ('user_pref("privacy.resistFingerprinting", true);\n'
                    'user_pref("browser.display.document_color_use", 1);\n')
        (profile / "user.js").write_text(original)
        firefox = self.root / ".mozilla/firefox/keep"
        firefox.mkdir(parents=True)
        code, error = self.apply()
        self.assertEqual(code, 0, error)
        self.assertIn("background-color: #112233", (profile / "chthm-home.html").read_text())
        self.assertIn("/* chthm:begin librewolf */", (profile / "chrome/userChrome.css").read_text())
        self.assertIn("// chthm:begin librewolf", (profile / "user.js").read_text())
        user = (profile / "user.js").read_text()
        self.assertTrue(user.startswith(original))
        managed = user.split("// chthm:begin librewolf", 1)[1]
        self.assertIn('user_pref("browser.display.document_color_use", 1);', managed)
        self.assertNotIn('browser.display.background_color', managed)
        self.assertNotIn('browser.display.foreground_color', managed)
        self.assertIn('user_pref("layout.css.prefers-color-scheme.content-override", 0);', managed)
        self.assertNotIn("privacy.resistFingerprinting", managed)
        self.assertEqual((profile / "user.js.bak").read_text(), original)
        self.assertEqual(list(firefox.iterdir()), [])

    def test_legacy_profile_precedes_xdg_profile(self):
        legacy = self.registry(self.root / ".librewolf")
        xdg = self.registry(self.config / "librewolf/librewolf")
        code, error = self.apply()
        self.assertEqual(code, 0, error)
        self.assertTrue((legacy / "chthm-home.html").is_file())
        self.assertFalse((xdg / "chthm-home.html").exists())

    def test_flatpak_and_explicit_profiles_are_supported(self):
        flatpak = self.registry(self.root / ".var/app/io.gitlab.librewolf-community/.librewolf")
        code, error = self.apply()
        self.assertEqual(code, 0, error)
        self.assertTrue((flatpak / "chthm-home.html").is_file())

        first = self.root / "custom-one"
        second = self.root / "custom-two"
        first.mkdir()
        second.mkdir()
        code, error = self.apply("--librewolf-profile", str(first),
                                 "--librewolf-profile", str(second))
        self.assertEqual(code, 0, error)
        self.assertTrue((first / "chthm-home.html").is_file())
        self.assertTrue((second / "chthm-home.html").is_file())

    def test_flatpak_desktop_entry_is_installation_evidence(self):
        flatpak = self.registry(
            self.root / ".var/app/io.gitlab.librewolf-community/.librewolf")
        desktop = (self.root / "data/flatpak/exports/share/applications"
                   / "io.gitlab.librewolf-community.desktop")
        desktop.parent.mkdir(parents=True)
        desktop.write_text("[Desktop Entry]\nName=LibreWolf\n")
        with patch("chthm.cli.shutil.which", return_value=None):
            code, error = self.apply()
        self.assertEqual(code, 0, error)
        self.assertTrue((flatpak / "chthm-home.html").is_file())

    def test_missing_explicit_profile_stops_before_writes(self):
        code, error = self.apply("--librewolf-profile", str(self.root / "missing"))
        self.assertEqual(code, 1)
        self.assertIn("LibreWolf profile directory not found", error)
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
