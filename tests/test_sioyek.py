import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main
from chthm.integrations import sioyek_text

VALUES = {"CHTHM_BACKGROUND": "#0a0f14", "CHTHM_FOREGROUND": "#98d1ce"}
PDF_SETTINGS = (
    'custom_background_color 0.18 0.20 0.25\n'
    'custom_text_color #aabbcc\n'
    'custom_color_mode_empty_background_color 0.1 0.1 0.1\n'
    'custom_color_contrast 0.8\n'
    'default_dark_mode 1\n'
    'dark_mode_contrast 0.7\n'
    'startup_commands toggle_custom_color;toggle_visual_scroll\n'
    'page_separator_color 0.5 0.5 0.5\n'
    'text_highlight_color 1.0 1.0 0.0\n'
)


class SioyekTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config'
        self.env = patch.dict(os.environ, {'HOME': str(self.root),
            'XDG_CONFIG_HOME': str(self.config), 'XDG_STATE_HOME': str(self.root / 'state'), 'XDG_DATA_HOME': str(self.root / 'data')})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.theme = self.root / 'theme.toml'
        self.theme.write_text('[colors.primary]\nbackground="#0a0f14"\nforeground="#98d1ce"\n')
        commands = patch('chthm.cli.shutil.which',
                         side_effect=lambda name: '/usr/bin/sioyek' if name == 'sioyek' else None)
        commands.start()
        self.addCleanup(commands.stop)

    def run_cli(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main([str(self.theme), '--no-reload', *args])
        return code, output.getvalue(), error.getvalue()

    def test_pdf_settings_and_comments_preserved_across_theme_changes(self):
        original = '# My preferences\n' + PDF_SETTINGS + '# ui_text_color 1 0 0\nfont_size 18\n'
        first = sioyek_text(original, VALUES)
        second = sioyek_text(first, {'CHTHM_BACKGROUND': '#000000', 'CHTHM_FOREGROUND': '#ffffff'})
        self.assertTrue(first.startswith(original))
        self.assertTrue(second.startswith(original))
        self.assertEqual(sioyek_text(first, VALUES), first)
        # No additional PDF mode or recoloring declaration may be introduced.
        for prefix in ('custom_', 'startup_commands', 'default_dark_mode', 'dark_mode_contrast', 'page_separator_color', 'text_highlight_color'):
            self.assertEqual([line for line in first.splitlines() if line.startswith(prefix)],
                             [line for line in original.splitlines() if line.startswith(prefix)])

    def test_interface_colors_and_inverted_selection_are_normalized_rgb(self):
        text = sioyek_text('', VALUES)
        settings = dict(line.split(None, 1) for line in text.splitlines() if line and not line.startswith('#'))
        self.assertEqual(len(settings), 8)
        expected = {
            'background_color': '#0a0f14', 'dark_mode_background_color': '#0a0f14',
            'ui_background_color': '#0a0f14', 'ui_text_color': '#98d1ce',
            'ui_selected_background_color': '#98d1ce', 'ui_selected_text_color': '#0a0f14',
            'status_bar_color': '#0a0f14', 'status_bar_text_color': '#98d1ce',
        }
        for key, hex_color in expected.items():
            channels = [round(float(value) * 255) for value in settings[key].split()]
            self.assertEqual(channels, [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)])

    def test_existing_declarations_comments_and_duplicates_are_handled(self):
        original = 'ui_text_color #ffffff # menu text\nui_text_color 1 1 1\nbackground_color 0 0 0 # window\n' + PDF_SETTINGS.rstrip('\n')
        result = sioyek_text(original, VALUES)
        active = [line for line in result.splitlines() if line.startswith('ui_text_color ')]
        self.assertEqual(len(active), 2)
        self.assertTrue(all('0.596078 0.819608 0.807843' in line for line in active))
        self.assertIn('# menu text', result)
        self.assertIn('# window', result)
        self.assertIn(PDF_SETTINGS, result)
        self.assertEqual(sioyek_text(result, VALUES), result)

    def test_cli_writes_only_selected_target_with_backup_and_preserves_pdf(self):
        target = self.config / 'sioyek/prefs_user.config'
        target.parent.mkdir(parents=True)
        target.write_text(PDF_SETTINGS)
        with patch('chthm.cli.reload_apps') as reloads:
            code, _, error = self.run_cli('--targets', 'sioyek')
        self.assertEqual(code, 0, error)
        reloads.assert_not_called()
        self.assertEqual(Path(str(target) + '.bak').read_text(), PDF_SETTINGS)
        self.assertTrue(target.read_text().startswith(PDF_SETTINGS))
        self.assertFalse((self.config / 'alacritty').exists())
        self.assertFalse((self.config / 'rofi').exists())
        code, _, error = self.run_cli('--targets', 'sioyek')
        self.assertEqual(code, 0, error)
        self.assertEqual(Path(str(target) + '.bak').read_text(), PDF_SETTINGS)

    def test_dry_run_and_path_override(self):
        target = self.root / 'custom/prefs_user.config'
        code, _, error = self.run_cli('--targets', 'sioyek', '--sioyek-config', str(target), '--dry-run')
        self.assertEqual(code, 0, error)
        self.assertIn(str(target), error)
        self.assertFalse(target.exists())
        code, _, error = self.run_cli('--targets', 'sioyek', '--sioyek-config', str(target))
        self.assertEqual(code, 0, error)
        self.assertTrue(target.is_file())
        self.assertFalse((self.config / 'sioyek').exists())

    def test_saved_target_and_path_settings(self):
        directory = self.config / 'chthm'
        directory.mkdir(parents=True)
        (directory / 'config.toml').write_text('targets=["sioyek"]\nsioyek_config="~/reader/prefs_user.config"\nreload=false\n')
        code, _, error = self.run_cli()
        self.assertEqual(code, 0, error)
        self.assertTrue((self.root / 'reader/prefs_user.config').is_file())


if __name__ == '__main__':
    unittest.main()
