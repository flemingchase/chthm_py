import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from chthm.cli import main
from chthm.theme import Theme

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('standalone_palette_loader', ROOT / 'src/chthm/qtile_palette.py')
qtile_colors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qtile_colors)


class ThemeStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config'
        self.data = self.root / 'data'
        self.state = self.root / 'state/chthm/current.toml'
        self.themes = self.data / 'chthm/themes'
        self.themes.mkdir(parents=True)
        self.source = self.themes / 'kimbie_dark.toml'
        self.source.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        env = patch.dict(os.environ, {'HOME': str(self.root), 'XDG_CONFIG_HOME': str(self.config),
            'XDG_DATA_HOME': str(self.data), 'XDG_STATE_HOME': str(self.root / 'state')})
        env.start()
        self.addCleanup(env.stop)
        commands = patch('chthm.cli.shutil.which', return_value=None)
        self.commands = commands.start()
        self.addCleanup(commands.stop)

    def run_cli(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = main(list(args))
        return result, output.getvalue(), error.getvalue()

    def test_independent_collection_and_selection_survive_source_removal(self):
        code, _, error = self.run_cli('kimbie_dark', '--no-reload')
        self.assertEqual(code, 0, error)
        self.assertTrue(self.state.is_file())
        self.assertFalse(self.config.exists())
        self.source.unlink()
        code, output, error = self.run_cli('exports')
        self.assertEqual(code, 0, error)
        self.assertIn("CHTHM_BACKGROUND='#112233'", output)
        self.assertIn('CHTHM_THEME=kimbie_dark', output)
        self.assertEqual(Theme.from_snapshot(self.state).source, self.source)

    def test_snapshot_is_published_before_reload_with_current_colors(self):
        def reload(values, **kwargs):
            saved = Theme.from_snapshot(self.state)
            self.assertEqual(saved.exports['CHTHM_BACKGROUND'], values['CHTHM_BACKGROUND'])
        with patch('chthm.cli.reload_apps', side_effect=reload) as hook:
            code, _, error = self.run_cli('kimbie_dark')
        self.assertEqual(code, 0, error)
        hook.assert_called_once()

    def test_snapshot_backup_and_dry_run_preserve_last_selection(self):
        self.assertEqual(self.run_cli('kimbie_dark', '--no-reload')[0], 0)
        before = self.state.read_bytes()
        other = self.themes / 'other.toml'
        other.write_text('[colors.primary]\nbackground="#000000"\nforeground="#ffffff"\n')
        self.assertEqual(self.run_cli('other', '--dry-run', '--no-reload')[0], 0)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(self.run_cli('other', '--no-reload')[0], 0)
        self.assertEqual(Path(str(self.state) + '.bak').read_bytes(), before)
        self.assertEqual(Theme.from_snapshot(self.state).name, 'other')
        code, output, _ = self.run_cli('list')
        self.assertEqual(code, 0)
        self.assertIn('* other', output)

    def test_input_and_state_path_collision_is_rejected(self):
        original = self.source.read_bytes()
        code, _, _ = self.run_cli('kimbie_dark', '--state-file', str(self.source), '--no-reload')
        self.assertEqual(code, 1)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.state.exists())

    def test_alacritty_is_an_output_and_legacy_import_readers_still_work(self):
        self.commands.side_effect = lambda name: '/usr/bin/alacritty' if name == 'alacritty' else None
        code, _, error = self.run_cli('kimbie_dark', '--targets', 'alacritty', '--no-reload')
        self.assertEqual(code, 0, error)
        selector = self.config / 'alacritty/theme.toml'
        imported = tomllib.loads(selector.read_text())['general']['import'][0]
        generated = tomllib.loads(Path(imported).read_text())
        self.assertEqual(set(generated), {'colors'})
        self.assertEqual(generated['colors'], Theme.from_snapshot(self.state).colors)
        self.assertNotEqual(Path(imported), self.source)
        self.assertIn('blue', generated['colors']['normal'])

    def test_minimal_palette_gets_complete_colors_and_roles(self):
        theme = Theme.load(self.source)
        self.assertEqual(theme.roles['accent'], '#ddeeff')
        self.assertEqual(theme.colors['normal']['black'], '#112233')
        self.assertEqual(len(theme.colors['normal']), 8)
        self.assertEqual(theme.colors['bright'], theme.colors['normal'])

    def test_metadata_and_explicit_roles_are_data_only(self):
        self.source.write_text(self.source.read_text() + '\n[theme]\nname="My palette"\ndescription="ignored metadata"\n[roles]\naccent="#ABCDEF"\n')
        theme = Theme.load(self.source)
        self.assertEqual(theme.name, 'My palette')
        self.assertEqual(theme.roles['accent'], '#abcdef')
        self.assertEqual(theme.exports['CHTHM_ROLES_ACCENT'], '#abcdef')
        self.assertNotIn('CHTHM_THEME_DESCRIPTION', theme.exports)

    def test_symbolic_and_indexed_colors_round_trip(self):
        self.source.write_text(self.source.read_text() + '\n[colors.cursor]\ntext="CellBackground"\ncursor="CellForeground"\n[[colors.indexed_colors]]\nindex=16\ncolor="#ABCDEF"\n')
        theme = Theme.load(self.source)
        parsed = tomllib.loads(theme.palette_toml())
        self.assertEqual(parsed['colors']['cursor']['text'], '#112233')
        self.assertEqual(parsed['colors']['indexed_colors'], [{'index': 16, 'color': '#abcdef'}])

    def test_invalid_optional_color_cannot_replace_good_state(self):
        self.assertEqual(self.run_cli('kimbie_dark', '--no-reload')[0], 0)
        original = self.state.read_bytes()
        self.source.write_text(self.source.read_text() + '\n[colors.normal]\nblue="invalid"\n')
        code, _, _ = self.run_cli('kimbie_dark', '--no-reload')
        self.assertEqual(code, 1)
        self.assertEqual(self.state.read_bytes(), original)

    def test_qtile_loader_uses_saved_snapshot_without_importing_chthm(self):
        self.assertEqual(self.run_cli('kimbie_dark', '--no-reload')[0], 0)
        self.source.unlink()
        loaded = qtile_colors.load_palette()
        self.assertEqual(loaded['colors']['primary']['background'], '#112233')
        self.assertEqual(loaded['roles']['accent'], '#ddeeff')

    def test_qtile_loader_has_safe_independent_fallbacks(self):
        palette = qtile_colors.load_palette()
        self.assertEqual(palette['colors']['primary']['background'], '#221a0f')
        palette['colors']['primary']['background'] = '#000000'
        self.assertEqual(qtile_colors.load_palette()['colors']['primary']['background'], '#221a0f')
        self.state.parent.mkdir(parents=True)
        for content in ('not valid toml', 'schema_version=99\n', 'schema_version=1\n[colors.primary]\nbackground="bad"\nforeground="#ffffff"\n'):
            self.state.write_text(content)
            with self.assertLogs('libqtile', level='WARNING'):
                loaded = qtile_colors.load_palette()
            self.assertEqual(loaded['colors']['primary']['background'], '#221a0f')

    def test_saved_custom_state_path_is_shared_with_qtile(self):
        settings = self.config / 'chthm/config.toml'
        settings.parent.mkdir(parents=True)
        custom = self.root / 'custom/current.toml'
        settings.write_text(f'state_file="{custom}"\n')
        self.assertEqual(self.run_cli('kimbie_dark', '--no-reload')[0], 0)
        self.assertTrue(custom.is_file())
        self.assertEqual(qtile_colors.load_palette()['colors']['primary']['background'], '#112233')
        self.assertFalse(self.state.exists())



if __name__ == '__main__':
    unittest.main()
