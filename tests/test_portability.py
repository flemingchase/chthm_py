import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main


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
        self.assertIn('Skipping', error)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.data.exists())

    def test_only_configured_app_is_changed(self):
        rofi = self.config / 'rofi/config.rasi'
        rofi.parent.mkdir(parents=True)
        rofi.write_text('* {background:black; foreground:white;}\n')
        result, _, error = self.run_cli()
        self.assertEqual(result, 0, error)
        self.assertIn('#112233', rofi.read_text())
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
        self.assertIn('Skipping rofi', error)
        self.assertIn('Skipping sioyek', error)
        self.assertEqual({p.name for p in self.config.iterdir()}, {'chthm'})

    def test_explicit_targets_and_custom_destinations_can_preconfigure_apps(self):
        result, _, error = self.run_cli('--targets', 'sioyek')
        self.assertEqual(result, 0, error)
        self.assertTrue((self.config / 'sioyek/prefs_user.config').is_file())
        custom = self.root / 'future-reader/prefs_user.config'
        result, _, error = self.run_cli('--sioyek-config', str(custom))
        self.assertEqual(result, 0, error)
        self.assertTrue(custom.is_file())
        self.assertFalse((self.config / 'alacritty').exists())

    def test_dry_run_probes_presence_without_privilege_or_writes(self):
        result, _, error = self.run_cli('--dry-run')
        self.assertEqual(result, 0, error)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.data.exists())

    def test_invalid_theme_is_still_an_error_when_no_apps_exist(self):
        self.theme.write_text('[colors.primary]\nbackground="invalid"\nforeground="#ffffff"\n')
        result, _, _ = self.run_cli()
        self.assertEqual(result, 1)
        self.assertFalse(self.config.exists())


if __name__ == '__main__':
    unittest.main()
