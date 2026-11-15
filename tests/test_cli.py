import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main, exports, palette, atomic_write


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.themes = self.root / "data/chthm/themes"
        self.themes.mkdir(parents=True)
        self.theme = self.themes / "kimbie_dark.toml"
        self.theme.write_text('[colors.primary]\nbackground = "#112233"\nforeground = "#ddeeff"\n')
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config), "XDG_STATE_HOME": str(self.root / "state"), "XDG_DATA_HOME": str(self.root / "data"), "HOME": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.reload = patch("chthm.cli.reload_apps")
        self.reload_mock = self.reload.start()
        self.addCleanup(self.reload.stop)
        self.availability = patch("chthm.cli.unavailable_reason", return_value=None)
        self.availability.start()
        self.addCleanup(self.availability.stop)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_apply_preserves_settings_deduplicates_and_backs_up(self):
        target = self.config / "zathura/zathurarc"
        target.parent.mkdir(parents=True)
        old = '# keep comment\nset font "Mono 12"\nset default-bg "old"\nset default-bg "duplicate"\n'
        target.write_text(old)
        target.chmod(0o640)
        code, out, err = self.run_cli("--no-reload", "--shell")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertIn("export CHTHM_BACKGROUND=", out)
        self.assertIn('set font "Mono 12"', target.read_text())
        self.assertEqual(target.read_text().count("set default-bg"), 1)
        self.assertEqual(Path(str(target) + ".bak").read_text(), old)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertIn("chthm-colors.toml", (self.config / "alacritty/theme.toml").read_text())
        self.assertIn("#112233", (self.config / "alacritty/chthm-colors.toml").read_text())
        self.assertIn("#112233", (self.config / "rofi/theme.env").read_text())
        self.assertTrue((self.config / "sioyek/prefs_user.config").is_file())
        self.assertTrue((self.config / "qt6ct/colors/chthm.conf").is_file())
        self.reload_mock.assert_not_called()

    def test_successful_normal_application_is_quiet(self):
        code, out, err = self.run_cli("--targets", "alacritty", "--no-reload")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        self.assertEqual(err, "")
        self.assertTrue((self.config / "alacritty/chthm-colors.toml").is_file())

    def test_dry_run_and_invalid_theme_write_nothing(self):
        before = sorted(self.config.rglob("*"))
        code, out, err = self.run_cli("--dry-run", "--shell")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        self.assertEqual(sorted(self.config.rglob("*")), before)
        self.reload_mock.assert_not_called()
        self.theme.write_text('[colors.primary]\nbackground="bad"\nforeground="#ddeeff"\n')
        code, _, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(sorted(self.config.rglob("*")), before)

    def test_readonly_exports_use_current_selection(self):
        other = self.themes / "other.toml"
        other.write_text('[colors.primary]\nbackground="#abcdef"\nforeground="#fedcba"\n')
        self.assertEqual(self.run_cli("other", "--targets", "alacritty", "--no-reload")[0], 0)
        other.unlink()  # The snapshot must survive removal of the source theme.
        code, out, err = self.run_cli("exports")
        self.assertEqual(code, 0, err)
        self.assertIn("#abcdef", out)
        self.assertFalse((self.config / "zathura").exists())
        self.reload_mock.assert_not_called()

    def test_config_targets_and_cli_override(self):
        directory = self.config / "chthm"
        directory.mkdir(parents=True)
        (directory / "config.toml").write_text('targets=["rofi"]\nreload=false\n')
        code, _, err = self.run_cli()
        self.assertEqual(code, 0, err)
        self.assertTrue((self.config / "rofi/theme.env").exists())
        self.assertFalse((self.config / "alacritty/theme.toml").exists())
        self.assertFalse((self.config / "zathura").exists())
        code, _, err = self.run_cli("--targets", "alacritty")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.config / "alacritty/theme.toml").exists())
        self.reload_mock.assert_not_called()

    def test_symlink_is_preserved(self):
        real = self.root / "dotfiles/zathurarc"
        real.parent.mkdir()
        real.write_text("original\n")
        link = self.root / "linked"
        link.symlink_to(real)
        atomic_write(link, "changed\n", backup=True)
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_text(), "changed\n")
        self.assertEqual(Path(str(real) + ".bak").read_text(), "original\n")

    def test_conflicting_paths_rejected_before_writes(self):
        code, _, _ = self.run_cli("--rofi-env", str(self.theme))
        self.assertEqual(code, 1)
        self.assertFalse((self.config / "zathura").exists())

    def test_shell_quoting_prevents_execution(self):
        marker = self.root / "should-not-exist"
        payload = f"$(touch {marker}); 'quoted'"
        code = exports({"CHTHM_TEST": payload}) + 'printf "%s" "$CHTHM_TEST"'
        result = subprocess.run(["sh", "-c", code], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, payload)
        self.assertFalse(marker.exists())

    def test_flatten_collision_rejected(self):
        self.theme.write_text(self.theme.read_text() + '\n[colors.extra]\n"a-b"="#112233"\na_b="#445566"\n')
        with self.assertRaisesRegex(ValueError, "collision"):
            palette(self.theme)

    @unittest.skipUnless(shutil.which("zsh"), "zsh unavailable")
    def test_zsh_wrapper_exports_lists_and_help(self):
        binary = self.root / "bin"
        binary.mkdir()
        executable = binary / "chthm"
        executable.write_text('#!/bin/sh\nexec python3 -m chthm "$@"\n')
        executable.chmod(0o755)
        integration = Path(__file__).resolve().parents[1] / "chthm.zsh"
        env = os.environ | {"PATH": str(binary) + os.pathsep + os.environ["PATH"]}
        result = subprocess.run(["zsh", "-f", "-c",
                                 'source "$1"; chthm --targets alacritty,zathura,rofi --no-reload || exit; '
                                 '[[ $CHTHM_BACKGROUND == "#112233" ]] || exit 2; '
                                 'chthm list || exit; chthm --help', "test", str(integration)],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("kimbie_dark", result.stdout)
        self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
