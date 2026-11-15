import contextlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from chthm.cli import main
from chthm.integrations import firefox_writes

VALUES = {'CHTHM_BACKGROUND': '#112233', 'CHTHM_FOREGROUND': '#ddeeff'}


def preferences(text):
    return {name: json.loads(value) for name, value in
            re.findall(r'^user_pref\("([^"]+)", (.*)\);$', text, re.M)}


class FirefoxHomeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.profile = self.root / 'a space #100%|profile'
        self.profile.mkdir()
        self.theme = self.root / 'theme.toml'
        self.theme.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        environment = patch.dict(os.environ, {'HOME': str(self.root),
            'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_STATE_HOME': str(self.root / 'state')})
        environment.start()
        self.addCleanup(environment.stop)
        commands = patch('chthm.cli.shutil.which',
                         side_effect=lambda name: '/usr/bin/firefox' if name == 'firefox' else None)
        commands.start()
        self.addCleanup(commands.stop)

    def apply(self, *arguments):
        error = io.StringIO()
        with contextlib.redirect_stderr(error), contextlib.redirect_stdout(io.StringIO()):
            result = main([str(self.theme), '--targets', 'firefox', '--firefox-profile',
                           str(self.profile), '--no-reload', *arguments])
        return result, error.getvalue()

    def test_local_home_and_startup_preferences_preserve_other_customizations(self):
        original = 'user_pref("browser.startup.homepage", "https://example.org/");\nuser_pref("browser.startup.page", 3);\nuser_pref("custom.keep", true);\n'
        (self.profile / 'user.js').write_text(original)
        result, error = self.apply()
        self.assertEqual(result, 0, error)
        page = self.profile / 'chthm-home.html'
        self.assertIn('background-color: #112233', page.read_text())
        self.assertIn('<body></body>', page.read_text())
        self.assertNotIn('<script', page.read_text())
        self.assertNotIn('https:', page.read_text())
        content = (self.profile / 'chrome/userContent.css').read_text()
        self.assertIn('@-moz-document url-prefix("about:preferences")', content)
        self.assertIn('--chthm-background: #112233', content)
        self.assertIn('--chthm-foreground: #ddeeff', content)
        self.assertIn('--background-color-canvas: var(--chthm-background)', content)
        self.assertIn('--text-color: var(--chthm-foreground)', content)
        self.assertIn('--card-border-radius: 0px', content)
        self.assertIn('--input-border-radius: 0px', content)
        self.assertIn('@-moz-document url("about:newtab"), url("about:home")', content)
        self.assertIn('--newtab-background-color: var(--chthm-background)', content)
        self.assertIn('--content-search-handoff-ui-color: var(--chthm-foreground)', content)
        user = (self.profile / 'user.js').read_text()
        self.assertTrue(user.startswith(original))
        prefs = preferences(user)
        self.assertEqual(prefs['browser.startup.homepage'], page.as_uri())
        self.assertEqual(prefs['browser.startup.page'], 1)
        self.assertIs(prefs['custom.keep'], True)
        self.assertIs(prefs['toolkit.legacyUserProfileCustomizations.stylesheets'], True)
        self.assertEqual(prefs['browser.display.document_color_use'], 1)
        self.assertEqual(prefs['layout.css.prefers-color-scheme.content-override'], 0)
        self.assertFalse(any(name.startswith(('browser.display.background_color',
                                              'browser.display.foreground_color'))
                             for name in prefs))
        self.assertNotIn('layout.css.always_underline_links', prefs)
        for name in ('browser.anchor_color', 'browser.visited_color', 'browser.active_color'):
            self.assertNotIn(name, prefs)
        self.assertNotIn('domain(', content)
        self.assertNotIn('forced-color', content)
        self.assertNotIn('privacy.resistFingerprinting', prefs)
        self.assertEqual((self.profile / 'user.js.bak').read_text(), original)
        self.assertIn('%7C', prefs['browser.startup.homepage'])

    def test_switch_updates_page_backup_and_keeps_one_preferences_block(self):
        self.assertEqual(self.apply()[0], 0)
        page = self.profile / 'chthm-home.html'
        before = page.read_bytes()
        content = self.profile / 'chrome/userContent.css'
        content_before = content.read_bytes()
        prefs_before = (self.profile / 'user.js').read_bytes()
        self.theme.write_text('[colors.primary]\nbackground="#fafafa"\nforeground="#111111"\n')
        self.assertEqual(self.apply()[0], 0)
        self.assertIn('background-color: #fafafa', page.read_text())
        self.assertIn('--chthm-background: #fafafa', content.read_text())
        self.assertIn('--chthm-foreground: #111111', content.read_text())
        self.assertEqual((content.with_name('userContent.css.bak')).read_bytes(),
                         content_before)
        prefs = preferences((self.profile / 'user.js').read_text())
        self.assertEqual(prefs['browser.display.document_color_use'], 1)
        self.assertEqual(prefs['layout.css.prefers-color-scheme.content-override'], 1)
        for name in ('browser.anchor_color', 'browser.visited_color', 'browser.active_color'):
            self.assertNotIn(name, prefs)
        self.assertEqual((self.profile / 'user.js.bak').read_bytes(), prefs_before)
        self.assertEqual((self.profile / 'chthm-home.html.bak').read_bytes(), before)
        self.assertNotEqual((self.profile / 'user.js').read_bytes(), prefs_before)
        self.assertEqual((self.profile / 'user.js').read_text().count('// chthm:begin firefox'), 1)

    def test_existing_managed_block_moves_after_later_homepage_overrides(self):
        for filename, text, _ in firefox_writes(self.profile, VALUES):
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text(text)
        user = self.profile / 'user.js'
        user.write_text(user.read_text() + 'user_pref("browser.startup.homepage", "about:blank");\n')
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(preferences(user.read_text())['browser.startup.homepage'],
                         (self.profile / 'chthm-home.html').as_uri())

    def test_multiple_profiles_get_independent_local_home_pages(self):
        second = self.root / 'another-profile'
        second.mkdir()
        result, error = self.apply('--firefox-profile', str(second))
        self.assertEqual(result, 0, error)
        for profile in (self.profile, second):
            page = profile / 'chthm-home.html'
            self.assertTrue(page.is_file())
            self.assertEqual(preferences((profile / 'user.js').read_text())['browser.startup.homepage'], page.as_uri())

    def test_dry_run_creates_no_page_or_preferences(self):
        result, error = self.apply('--dry-run')
        self.assertEqual(result, 0, error)
        self.assertFalse(any(self.profile.iterdir()))
        self.assertIn('chthm-home.html', error)

    def test_invalid_preferences_block_cannot_publish_home_page(self):
        user = self.profile / 'user.js'
        user.write_text('// chthm:begin firefox\n')
        result, _ = self.apply()
        self.assertEqual(result, 1)
        self.assertFalse((self.profile / 'chthm-home.html').exists())
        self.assertFalse((self.root / 'state/chthm/current.toml').exists())


if __name__ == '__main__':
    unittest.main()
