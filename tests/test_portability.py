import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main
from chthm.targets import DEFAULT_TARGETS


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config'
        self.data = self.root / 'data'
        self.theme = self.root / 'theme.toml'
        self.theme.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        environment = patch.dict(os.environ, {'HOME': str(self.root),
            'XDG_CONFIG_HOME': str(self.config), 'XDG_STATE_HOME': str(self.root / 'state'), 'XDG_DATA_HOME': str(self.data)})
        environment.start()
        self.addCleanup(environment.stop)
        commands = patch('chthm.cli.shutil.which', return_value=None)
        self.commands = commands.start()
        self.addCleanup(commands.stop)

    def run_cli(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = main([str(self.theme), '--no-reload', *args])
        return result, output.getvalue(), error.getvalue()

    def test_no_apps_exports_palette_without_creating_configuration(self):
        result, output, error = self.run_cli('--shell')
        self.assertEqual(result, 0, error)
        self.assertIn("export CHTHM_BACKGROUND='#112233'", output)
        self.assertEqual(error, '')
        self.assertFalse(self.config.exists())
        self.assertFalse(self.data.exists())

    def test_stale_configuration_does_not_count_as_installed(self):
        rofi = self.config / 'rofi/config.rasi'
        rofi.parent.mkdir(parents=True)
        rofi.write_text('* {background:black; foreground:white;}\n')
        result, _, error = self.run_cli()
        self.assertEqual(result, 0, error)
        self.assertNotIn('#112233', rofi.read_text())
        self.assertEqual(error, '')
        self.assertEqual({p.name for p in self.config.iterdir()}, {'rofi'})
        self.assertFalse(self.data.exists())

    def test_installed_app_can_receive_its_first_configuration(self):
        self.commands.side_effect = lambda name, **kwargs: '/usr/bin/sioyek' if name == 'sioyek' else None
        result, _, error = self.run_cli()
        self.assertEqual(result, 0, error)
        self.assertTrue((self.config / 'sioyek/prefs_user.config').is_file())
        self.assertEqual({p.name for p in self.config.iterdir()}, {'sioyek'})
        self.assertFalse(self.data.exists())

    def test_saved_targets_still_skip_absent_applications(self):
        settings = self.config / 'chthm/config.toml'
        settings.parent.mkdir(parents=True)
        settings.write_text('targets=["rofi", "sioyek"]\n')
        result, _, error = self.run_cli()
        self.assertEqual(result, 0, error)
        self.assertEqual(error, '')
        self.assertEqual({p.name for p in self.config.iterdir()}, {'chthm'})

    def test_explicit_targets_and_custom_destinations_cannot_preconfigure_apps(self):
        result, _, error = self.run_cli('--targets', 'sioyek')
        self.assertEqual(result, 0, error)
        self.assertFalse((self.config / 'sioyek/prefs_user.config').exists())
        self.assertEqual(error, '')
        custom = self.root / 'future-reader/prefs_user.config'
        result, _, error = self.run_cli('--sioyek-config', str(custom))
        self.assertEqual(result, 0, error)
        self.assertFalse(custom.exists())
        self.assertFalse((self.config / 'alacritty').exists())

    def test_user_can_add_an_installed_target_and_custom_command(self):
        executable = self.root / 'apps/sioyek-custom'
        executable.parent.mkdir()
        executable.write_text('#!/bin/sh\n')
        executable.chmod(0o755)
        settings = self.config / 'chthm/config.toml'
        settings.parent.mkdir(parents=True)
        settings.write_text(
            'targets=[]\nadditional_targets=["sioyek"]\n'
            f'target_commands={{sioyek=["{executable}"]}}\nreload=false\n')
        result, _, error = self.run_cli()
        self.assertEqual(result, 0, error)
        self.assertTrue((self.config / 'sioyek/prefs_user.config').is_file())

    def test_cli_can_add_a_target_without_replacing_the_selection(self):
        self.commands.side_effect = lambda name, **kwargs: '/usr/bin/rofi' if name == 'rofi' else None
        result, _, error = self.run_cli('--targets', '', '--add-targets', 'rofi')
        self.assertEqual(result, 0, error)
        self.assertTrue((self.config / 'rofi/config.rasi').is_file())

    def test_default_targets_include_existing_apps_and_requested_terminals(self):
        self.assertEqual(DEFAULT_TARGETS, {
            'alacritty', 'zathura', 'rofi', 'firefox', 'librewolf',
            'clementine', 'sioyek', 'pcmanfm-qt', 'qtile', 'qutebrowser',
            'ghostty', 'kitty', 'wezterm', 'foot',
        })

    def test_dry_run_probes_presence_without_privilege_or_writes(self):
        result, _, error = self.run_cli('--dry-run')
        self.assertEqual(result, 0, error)
        self.assertIn('Skipping', error)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.data.exists())

    def test_invalid_theme_is_still_an_error_when_no_apps_exist(self):
        self.theme.write_text('[colors.primary]\nbackground="invalid"\nforeground="#ffffff"\n')
        result, _, error = self.run_cli()
        self.assertEqual(result, 1)
        self.assertIn('chthm: colors.primary.background must have the form #RRGGBB', error)
        self.assertFalse(self.config.exists())


if __name__ == '__main__':
    unittest.main()
