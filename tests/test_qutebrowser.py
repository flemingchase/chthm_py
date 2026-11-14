import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main
from chthm.pages import blank_page_html
from chthm.qutebrowser import BEGIN, END, blank_page_config


class QutebrowserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'config/qutebrowser/config.py'
        self.page = self.root / 'data/chthm/qutebrowser/blank.html'
        self.theme = self.root / 'theme.toml'
        self.theme.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        environment = patch.dict(os.environ, {'HOME': str(self.root),
            'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_STATE_HOME': str(self.root / 'state')})
        environment.start()
        self.addCleanup(environment.stop)
        commands = patch('chthm.cli.shutil.which', return_value=None)
        self.commands = commands.start()
        self.addCleanup(commands.stop)

    def run_cli(self, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = main([str(self.theme), '--no-reload', *arguments])
        return result, error.getvalue()

    def test_default_target_updates_page_and_keeps_existing_settings(self):
        self.config.parent.mkdir(parents=True)
        original = "config.load_autoconfig(False)\nconfig.bind('J', 'tab-prev')\nc.url.default_page = 'about:blank'\n"
        self.config.write_text(original)
        result, error = self.run_cli()
        self.assertEqual(result, 0, error)
        self.assertIn('background-color: #112233', self.page.read_text())
        self.assertTrue(self.config.read_text().startswith(original))
        self.assertEqual(self.config.with_name('config.py.bak').read_text(), original)
        self.assertIn(self.page.as_uri(), self.config.read_text())
        self.assertIn('url.start_pages', self.config.read_text())
        config_before = self.config.read_bytes()
        page_before = self.page.read_bytes()
        self.theme.write_text('[colors.primary]\nbackground="#445566"\nforeground="#ffffff"\n')
        result, error = self.run_cli()
        self.assertEqual(result, 0, error)
        self.assertIn('background-color: #445566', self.page.read_text())
        self.assertEqual(self.page.with_name('blank.html.bak').read_bytes(), page_before)
        self.assertEqual(self.config.read_bytes(), config_before)
        self.assertEqual(self.config.read_text().count(BEGIN), 1)

    def test_fresh_app_and_custom_page_path(self):
        self.commands.side_effect = lambda name, **kwargs: '/usr/bin/qutebrowser' if name == 'qutebrowser' else None
        custom = self.root / 'some space/100% #blank.html'
        result, error = self.run_cli('--qutebrowser-page', str(custom))
        self.assertEqual(result, 0, error)
        self.assertTrue(custom.is_file())
        self.assertTrue(self.config.read_text().startswith('config.load_autoconfig()'))
        self.assertIn(custom.as_uri(), self.config.read_text())
        self.assertIn('%20', self.config.read_text())
        self.assertIn('%25', self.config.read_text())

    def test_dry_run_does_not_write_or_change_default_url(self):
        self.config.parent.mkdir(parents=True)
        original = "c.url.default_page = 'about:blank'\n"
        self.config.write_text(original)
        result, error = self.run_cli('--dry-run')
        self.assertEqual(result, 0, error)
        self.assertEqual(self.config.read_text(), original)
        self.assertFalse(self.page.exists())
        self.assertIn('blank.html', error)

    def test_invalid_config_cannot_publish_page_or_state(self):
        self.config.parent.mkdir(parents=True)
        for original in ('if then\n', BEGIN + '\n', END + '\n' + BEGIN + '\n'):
            self.config.write_text(original)
            result, _ = self.run_cli()
            self.assertEqual(result, 1)
            self.assertEqual(self.config.read_text(), original)
            self.assertFalse(self.page.exists())
            self.assertFalse((self.root / 'state/chthm/current.toml').exists())

    def test_explicit_other_targets_do_not_update_or_restart_qutebrowser(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text('config.load_autoconfig()\n')
        with patch('chthm.cli.reload_apps') as reload:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(self.theme), '--targets', 'rofi']), 0)
            self.assertFalse(reload.call_args.kwargs['qutebrowser_enabled'])
        self.assertFalse(self.page.exists())

    def test_page_source_cannot_be_overwritten(self):
        before = self.theme.read_bytes()
        result, _ = self.run_cli('--qutebrowser-page', str(self.theme))
        self.assertEqual(result, 1)
        self.assertEqual(self.theme.read_bytes(), before)
        self.assertFalse(self.config.exists())

    def test_blank_page_settings_remain_last_and_markers_in_strings_are_ignored(self):
        original = 'text = """\n' + BEGIN + '\n' + END + '\n"""\n'
        first = blank_page_config(original, self.page)
        self.assertTrue(first.startswith(original))
        self.assertEqual(blank_page_config(first, self.page), first)
        appended = first + "c.url.default_page = 'about:blank'\n"
        updated = blank_page_config(appended, self.page)
        self.assertGreater(updated.rindex(BEGIN), updated.index('c.url.default_page'))
        self.assertEqual(blank_page_config(updated, self.page), updated)

    def test_html_is_empty_offline_and_validates_colors(self):
        page = blank_page_html('#112233', '#ddeeff')
        self.assertIn('<body></body>', page)
        self.assertIn('background-color: #112233', page)
        self.assertNotIn('<script', page)
        self.assertNotIn('https:', page)
        with self.assertRaises(ValueError):
            blank_page_html('red; invalid', '#ffffff')

    def test_settings_are_accepted_by_qutebrowser_and_darkmode_is_page_specific(self):
        import importlib.util
        if importlib.util.find_spec('qutebrowser') is None:
            self.skipTest('Optional qutebrowser installation unavailable')
        page = self.root / 'a space/100% #blank.html'
        source = self.root / 'validate.py'
        settings = blank_page_config('config.load_autoconfig(False)\n', page)
        source.write_text('''
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from unittest.mock import patch
from qutebrowser.qt.gui import QGuiApplication
from qutebrowser.qt.core import QUrl
from qutebrowser.config import config, configfiles, configdata
from qutebrowser.utils import standarddir
app = QGuiApplication([])
with patch.object(standarddir, 'config', return_value=os.environ['HOME']), patch.object(standarddir, 'data', return_value=os.environ['HOME']):
    configdata.init()
    conf = config.Config(configfiles.YamlConfig())
    config.instance = conf
    api = configfiles.ConfigAPI(conf, config.KeyConfig(conf), warn_autoconfig=False)
    conf.set_obj('colors.webpage.darkmode.enabled', True)
    exec(''' + repr(settings) + ''', {'config': api})
    assert not api.errors, api.errors
    assert conf.get('url.default_page') == QUrl(''' + repr(page.as_uri()) + ''')
    assert conf.get('url.start_pages')[0] == QUrl(''' + repr(page.as_uri()) + ''')
    assert conf.get('colors.webpage.darkmode.enabled', url=QUrl(''' + repr(page.as_uri()) + ''')) is False
    assert conf.get('colors.webpage.darkmode.enabled', url=QUrl('https://example.org/')) is True
''')
        result = subprocess.run([sys.executable, str(source)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
