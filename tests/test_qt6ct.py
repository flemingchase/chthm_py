import configparser
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main
from chthm.qt6ct import install_cleanup, scheme_text, settings_text
from chthm.theme import Theme

ROOT = Path(__file__).resolve().parents[1]


class Qt6ctTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'config'
        self.data = self.root / 'data'
        self.theme = self.root / 'theme.toml'
        self.theme.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        environment = patch.dict(os.environ, {'HOME': str(self.root),
            'XDG_CONFIG_HOME': str(self.config), 'XDG_DATA_HOME': str(self.data),
            'XDG_STATE_HOME': str(self.root / 'state')})
        environment.start()
        self.addCleanup(environment.stop)
        commands = patch('chthm.cli.shutil.which',
                         side_effect=lambda name: '/usr/bin/qt6ct' if name == 'qt6ct' else None)
        commands.start()
        self.addCleanup(commands.stop)

    def apply(self, *arguments):
        error = io.StringIO()
        with contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
            result = main([str(self.theme), '--targets', 'qt6ct', '--no-reload', *arguments])
        return result, error.getvalue()

    def test_scheme_has_complete_active_inactive_disabled_palettes(self):
        parser = configparser.RawConfigParser()
        parser.read_string(scheme_text(Theme.load(self.theme)))
        palettes = {name: [value.strip() for value in parser['ColorScheme'][name].split(',')]
                    for name in ('active_colors', 'inactive_colors', 'disabled_colors')}
        for colors in palettes.values():
            self.assertEqual(len(colors), 22)
            self.assertTrue(all(len(value) == 9 and value.startswith('#ff') for value in colors))
        active = palettes['active_colors']
        self.assertEqual(active[9:11], ['#ff112233', '#ff112233'])
        self.assertEqual(active[6], '#ffddeeff')
        self.assertEqual(active[12:14], ['#ffddeeff', '#ff112233'])
        self.assertEqual(palettes['inactive_colors'], active)
        self.assertNotEqual(palettes['disabled_colors'][6], active[6])

    def test_settings_preserve_fonts_icons_style_and_other_preferences(self):
        original = '[Appearance]\nstyle=Fusion\nicon_theme=Adwaita\ncustom_palette=false\n[Fonts]\ngeneral="Cantarell,22"\n[Interface]\nwheel_scroll_lines=3\n'
        palette = self.config / 'qt6ct/colors/a space, 100%.conf'
        scheme = scheme_text(Theme.load(self.theme))
        updated = settings_text(original, palette, scheme)
        self.assertIn('icon_theme=Adwaita', updated)
        self.assertIn('general="Cantarell,22"', updated)
        self.assertIn('wheel_scroll_lines=3', updated)
        self.assertIn('custom_palette=true', updated)
        self.assertEqual(updated.count('palette-sha256='), 1)
        self.assertEqual(settings_text(updated, palette, scheme), updated)
        self.assertNotEqual(settings_text(updated, palette, scheme.replace('#ff112233', '#ff334455')), updated)

    def test_switch_changes_only_shared_qt_files_and_creates_backups(self):
        files = {
            self.config / 'Clementine/Clementine.conf': '[Appearance]\nbackground-color=original\nuse-custom-set=false\n',
            self.config / 'pcmanfm-qt/default/settings.conf': '[FolderView]\nShowHidden=true\n',
            self.data / 'applications/pcmanfm-qt.desktop': '[Desktop Entry]\nExec=pcmanfm-qt %U\n',
        }
        for filename, text in files.items():
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text(text)
        result, error = self.apply()
        self.assertEqual(result, 0, error)
        palette = self.config / 'qt6ct/colors/chthm.conf'
        settings = self.config / 'qt6ct/qt6ct.conf'
        old_palette, old_settings = palette.read_bytes(), settings.read_bytes()
        self.theme.write_text('[colors.primary]\nbackground="#445566"\nforeground="#ffffff"\n')
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(palette.with_name('chthm.conf.bak').read_bytes(), old_palette)
        self.assertEqual(settings.with_name('qt6ct.conf.bak').read_bytes(), old_settings)
        for filename, text in files.items():
            self.assertEqual(filename.read_text(), text)
        self.assertFalse((self.config / 'chthm/pcmanfm-qt.qss').exists())

    def test_custom_paths_and_dry_run(self):
        palette = self.root / 'qt palette/theme.conf'
        settings = self.root / 'qt settings/qt6ct.conf'
        arguments = ('--qt6ct-config', str(settings), '--qt6ct-palette', str(palette))
        self.assertEqual(self.apply(*arguments, '--dry-run')[0], 0)
        self.assertFalse(palette.exists())
        self.assertEqual(self.apply(*arguments)[0], 0)
        self.assertTrue(palette.exists())
        self.assertIn(str(palette), settings.read_text())

    def test_installed_qt6_target_automatically_uses_qt6ct(self):
        def installed(name):
            return f'/usr/bin/{name}' if name in {'pcmanfm-qt', 'qt6ct'} else None
        error = io.StringIO()
        with patch('chthm.cli.shutil.which', side_effect=installed), \
                contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
            result = main([str(self.theme), '--targets', 'pcmanfm-qt', '--no-reload'])
        self.assertEqual(result, 0, error.getvalue())
        self.assertTrue((self.config / 'qt6ct/colors/chthm.conf').is_file())
        self.assertEqual((self.config / 'environment.d/60-chthm-qt6ct.conf').read_text(),
                         'QT_QPA_PLATFORMTHEME=qt6ct\n')
        self.assertFalse((self.config / 'pcmanfm-qt').exists())
        self.assertEqual(error.getvalue(), '')

    def test_qt6ct_integration_can_be_disabled(self):
        def installed(name):
            return f'/usr/bin/{name}' if name in {'pcmanfm-qt', 'qt6ct'} else None
        error = io.StringIO()
        with patch('chthm.cli.shutil.which', side_effect=installed), \
                contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
            result = main([str(self.theme), '--targets', 'pcmanfm-qt,qt6ct',
                           '--no-qt6ct', '--no-reload'])
        self.assertEqual(result, 0, error.getvalue())
        self.assertFalse((self.config / 'qt6ct').exists())
        self.assertEqual(error.getvalue(), '')

    def test_install_cleanup_removes_only_the_previous_pcmanfm_stylesheet_override(self):
        clementine = self.config / 'Clementine/Clementine.conf'
        clementine.parent.mkdir(parents=True)
        clementine.write_text('[Appearance]\nuse-custom-set=true\nbackground-color=keep\nforeground-color=keep-too\n[Other]\nsetting=keep\n')
        stylesheet = self.config / 'chthm/pcmanfm-qt.qss'
        stylesheet.parent.mkdir()
        stylesheet.write_text('/* Generated by chthm: PCManFM-Qt only. */\nQWidget { color:red; }\n')
        desktop = self.data / 'applications/pcmanfm-qt.desktop'
        desktop.parent.mkdir(parents=True)
        desktop.write_text('[Desktop Entry]\nName=Files\nExec="/usr/bin/pcmanfm-qt" "-stylesheet" "' + str(stylesheet) + '" %U\n')
        writes, removals = install_cleanup(self.config, self.data)
        changed = dict(writes)
        self.assertNotIn(clementine, changed)
        self.assertIn('use-custom-set=true', clementine.read_text())
        self.assertIn('Exec="/usr/bin/pcmanfm-qt" %U', changed[desktop])
        self.assertIn('Name=Files', changed[desktop])
        self.assertEqual(removals, [stylesheet])

    def test_install_cleanup_preserves_unmanaged_stylesheets(self):
        stylesheet = self.config / 'chthm/pcmanfm-qt.qss'
        stylesheet.parent.mkdir(parents=True)
        stylesheet.write_text('/* my own style */\n')
        self.assertEqual(install_cleanup(self.config, self.data), ([], []))

    def test_clementine_compatibility_serializes_native_qt_colors(self):
        try:
            from PyQt6.QtCore import QSettings
            from PyQt6.QtGui import QColor
        except ImportError:
            self.skipTest('Optional Qt bindings unavailable')
        from chthm.clementine import clementine_text
        config = self.root / 'Clementine.conf'
        config.write_text(clementine_text('[Other]\nkeep=true\n', {
            'CHTHM_BACKGROUND': '#112233', 'CHTHM_FOREGROUND': '#ddeeff'}))
        settings = QSettings(str(config), QSettings.Format.IniFormat)
        self.assertEqual(settings.value('Appearance/background-color').name(), '#112233')
        self.assertEqual(settings.value('Appearance/foreground-color').name(), '#ddeeff')
        self.assertTrue(settings.value('Appearance/use-custom-set', type=bool))
        self.assertIn('[Other]\nkeep=true', config.read_text())

    def test_native_qt6ct_plugin_and_live_palette_reload(self):
        if not shutil.which('qt6ct') or importlib.util.find_spec('PyQt6') is None:
            self.skipTest('Optional native qt6ct/Qt bindings unavailable')
        palette = self.config / 'qt6ct/colors/a space, 100%.conf'
        palette.parent.mkdir(parents=True)
        settings = self.config / 'qt6ct/qt6ct.conf'
        first = scheme_text(Theme.load(self.theme))
        palette.write_text(first)
        settings.write_text(settings_text('', palette, first))
        self.theme.write_text('[colors.primary]\nbackground="#445566"\nforeground="#ffffff"\n')
        second = scheme_text(Theme.load(self.theme))
        second_settings = settings_text(settings.read_text(), palette, second)
        code = '''
import os,sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication,QTreeView
from PyQt6.QtGui import QPalette
from PyQt6.QtCore import QTimer
app=QApplication([])
app.processEvents()
view=QTreeView();view.ensurePolished()
assert view.palette().color(QPalette.ColorRole.Base).name()=='#112233'
assert view.palette().color(QPalette.ColorRole.Text).name()=='#ddeeff'
assert view.palette().color(QPalette.ColorRole.Highlight).name()=='#ddeeff'
assert view.palette().color(QPalette.ColorRole.HighlightedText).name()=='#112233'
def replace(path,text):
    temporary=path.with_suffix('.new')
    temporary.write_text(text)
    os.replace(temporary,path)
def update():
    replace(Path(''' + repr(str(palette)) + '''),''' + repr(second) + ''')
    replace(Path(''' + repr(str(settings)) + '''),''' + repr(second_settings) + ''')
def check():
    if view.palette().color(QPalette.ColorRole.Base).name()=='#445566':
        app.exit(0)
QTimer.singleShot(200,update)
timer=QTimer();timer.timeout.connect(check);timer.start(50)
QTimer.singleShot(6500,lambda:app.exit(9))
sys.exit(app.exec())
'''
        env = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QPA_PLATFORMTHEME': 'qt6ct',
                            'XDG_CACHE_HOME': str(self.root / 'cache')}
        result = subprocess.run([sys.executable, '-c', code], env=env, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
