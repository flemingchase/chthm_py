import contextlib
import importlib.util
import zipfile
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('chthm_installer', SOURCE / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def theme_archive(entries=None):
    default = '[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n'
    entries = entries if entries is not None else {'themes/kimbie_dark.toml': default}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('alacritty-theme-master/LICENSE', 'Test license text')
        for name, content in entries.items():
            archive.writestr('alacritty-theme-master/' + name, content)
    return buffer.getvalue()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.home.mkdir()
        self.env = patch.dict(os.environ, {'HOME': str(self.home),
            'XDG_CONFIG_HOME': str(self.home / '.config'), 'XDG_STATE_HOME': str(self.home / '.local/state'),
            'XDG_DATA_HOME': str(self.home / '.local/share'), 'ZDOTDIR': str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.download_patch = patch.object(installer, "download_theme_archive", return_value=theme_archive())
        self.download = self.download_patch.start()
        self.addCleanup(self.download_patch.stop)
        real_which = installer.shutil.which
        self.commands_patch = patch.object(
            installer.shutil, "which",
            side_effect=lambda name, **kwargs: (f"/usr/bin/{name}"
                if name in {"alacritty", "qtile", "qutebrowser"} else real_which(name, **kwargs)))
        self.commands_patch.start()
        self.addCleanup(self.commands_patch.stop)

    def test_install_configures_shell_and_repeat_preserves_one_block(self):
        rc = self.home / '.zshrc'
        original = '# my shell settings\nexport KEEP_ME=yes\n'
        rc.write_text(original)
        filename = installer.install(SOURCE)
        self.assertEqual(filename, rc)
        self.assertTrue(rc.read_text().startswith(original))
        self.assertEqual(rc.read_text().count(installer.BEGIN), 1)
        before = rc.read_text()
        installer.install(SOURCE)
        self.assertEqual(rc.read_text(), before)
        self.assertTrue((self.home / '.local/bin/chthm').is_file())
        self.assertTrue((self.home / '.config/chthm/chthm.zsh').is_file())

    @unittest.skipUnless(shutil.which('zsh'), 'zsh unavailable')
    def test_new_shell_finds_commands_exports_palette_and_does_not_duplicate_path(self):
        theme = self.home / '.config/alacritty/themes/themes/kimbie_dark.toml'
        theme.parent.mkdir(parents=True)
        theme.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        (self.home / '.zshrc').write_text('export KEEP_ME=yes\n')
        installer.install(SOURCE)
        result = subprocess.run(['zsh', '-f', '-c',
            'source "$HOME/.zshrc"; source "$HOME/.zshrc"; '
            '[[ $KEEP_ME == yes && $CHTHM_BACKGROUND == "#112233" ]] || exit 2; '
            '[[ ${(M)#path:#$HOME/.local/bin} == 1 ]] || exit 3; '
            'command chthm --version; chthm --help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('chthm 2.0.0', result.stdout)
        self.assertIn('usage:', result.stdout)
        self.assertFalse((self.home / '.config/alacritty/theme.toml').exists())

    def test_download_can_be_removed_after_install(self):
        download = Path(self.temp.name) / 'download'
        shutil.copytree(SOURCE / 'src', download / 'src', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(SOURCE / 'themes', download / 'themes')
        shutil.copyfile(SOURCE / 'chthm.zsh', download / 'chthm.zsh')
        installer.install(download)
        shutil.rmtree(download)
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        result = subprocess.run([str(self.home / '.local/bin/chthm'), '--version'],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2.0.0', result.stdout)

    def test_dotfile_symlinks_are_preserved(self):
        real = self.home / 'dotfiles/zshrc'
        real.parent.mkdir()
        real.write_text('# keep\n')
        rc = self.home / '.zshrc'
        rc.symlink_to(real)
        installer.install(SOURCE)
        self.assertTrue(rc.is_symlink())
        self.assertIn(installer.BEGIN, real.read_text())

    def test_existing_command_symlink_is_replaced_without_modifying_target(self):
        old = self.home / 'old-command'
        old.write_text('old program\n')
        binary = self.home / '.local/bin/chthm'
        binary.parent.mkdir(parents=True)
        binary.symlink_to(old)
        installer.install(SOURCE)
        self.assertEqual(old.read_text(), 'old program\n')
        self.assertFalse(binary.is_symlink())

    def test_malformed_managed_block_and_invalid_zsh_leave_shell_untouched(self):
        rc = self.home / '.zshrc'
        for original in (installer.BEGIN + '\n', 'if then\n'):
            rc.write_text(original)
            with self.assertRaises(ValueError):
                installer.install(SOURCE)
            self.assertEqual(rc.read_text(), original)
            self.assertFalse((self.home / '.local/bin/chthm').exists())

    def test_installation_does_not_request_administrator_access(self):
        with patch.object(installer, 'install', return_value=self.home / '.zshrc'), \
             patch.object(installer.os, 'geteuid', return_value=1000), \
             patch.object(installer.subprocess, 'run') as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(installer.main([]), 0)
            run.assert_not_called()

    def test_upgrade_removes_obsolete_private_modules(self):
        package = self.home / '.local/share/chthm/lib/chthm'
        package.mkdir(parents=True)
        obsolete = package / 'obsolete_helper.py'
        obsolete.write_text('raise RuntimeError("retired module")\n')
        installer.install(SOURCE)
        self.assertFalse(obsolete.exists())
        self.assertTrue((package / 'cli.py').is_file())

    def test_qtile_snippet_preserves_config_and_loads_palette_before_widgets(self):
        from chthm.theme import Theme
        config = self.home / '.config/qtile/config.py'
        config.parent.mkdir(parents=True)
        original = ('# my config\n"""Qtile settings."""\n'
                    'from __future__ import annotations\n'
                    'widget_defaults = dict(background=chthm_background, foreground=chthm_foreground)\n'
                    'keys = ["keep me"]\n')
        config.write_text(original)
        config.chmod(0o640)
        state = self.home / '.local/state/chthm/current.toml'
        state.parent.mkdir(parents=True)
        source = self.home / 'custom.toml'
        source.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        state.write_text(Theme.load(source).snapshot_toml())
        installer.install(SOURCE)
        updated = config.read_text()
        self.assertEqual(updated.count(installer.QTILE_BEGIN), 1)
        start = updated.index(installer.QTILE_BEGIN)
        end = updated.index(installer.QTILE_END) + len(installer.QTILE_END) + 1
        self.assertEqual(updated[:start] + updated[end:], original)
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        import runpy
        loaded = runpy.run_path(str(config))
        self.assertEqual(loaded['widget_defaults'], {'background': '#112233', 'foreground': '#ddeeff'})
        self.assertEqual(loaded['keys'], ['keep me'])
        installer.install(SOURCE)
        self.assertEqual(config.read_text(), updated)

    def test_qtile_symlink_and_line_endings_survive(self):
        real = self.home / 'dotfiles/qtile.py'
        real.parent.mkdir()
        original = b'# settings\r\nkeys = []\r\n'
        real.write_bytes(original)
        config = self.home / '.config/qtile/config.py'
        config.parent.mkdir(parents=True)
        config.symlink_to(real)
        installer.install(SOURCE)
        self.assertTrue(config.is_symlink())
        self.assertTrue(real.read_bytes().endswith(b'keys = []\r\n'))
        self.assertTrue(real.read_bytes().startswith(b'# settings\r\n'))

    def test_invalid_qtile_config_stops_before_installation_writes(self):
        config = self.home / '.config/qtile/config.py'
        config.parent.mkdir(parents=True)
        for text in ('if then\n', installer.QTILE_BEGIN + '\n',
                     installer.QTILE_END + '\n' + installer.QTILE_BEGIN + '\n'):
            config.write_text(text)
            with self.assertRaises(ValueError):
                installer.install(SOURCE)
            self.assertEqual(config.read_text(), text)
            self.assertFalse((self.home / '.local/bin/chthm').exists())

    def test_qutebrowser_snippet_preserves_config_and_loads_palette_before_widgets(self):
        from chthm.theme import Theme
        config = self.home / '.config/qutebrowser/config.py'
        config.parent.mkdir(parents=True)
        original = ('# my config\n"""Qtile settings."""\n'
                    'from __future__ import annotations\n'
                    'widget_defaults = dict(background=chthm_background, foreground=chthm_foreground)\n'
                    'keys = ["keep me"]\n')
        config.write_text(original)
        config.chmod(0o640)
        state = self.home / '.local/state/chthm/current.toml'
        state.parent.mkdir(parents=True)
        source = self.home / 'custom.toml'
        source.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        state.write_text(Theme.load(source).snapshot_toml())
        installer.install(SOURCE)
        updated = config.read_text()
        self.assertEqual(updated.count(installer.QUTEBROWSER_BEGIN), 1)
        start = updated.index(installer.QUTEBROWSER_BEGIN)
        end = updated.index(installer.QUTEBROWSER_END) + len(installer.QUTEBROWSER_END) + 1
        self.assertEqual(updated[:start] + updated[end:], original)
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        import runpy
        loaded = runpy.run_path(str(config))
        self.assertEqual(loaded['widget_defaults'], {'background': '#112233', 'foreground': '#ddeeff'})
        self.assertEqual(loaded['keys'], ['keep me'])
        installer.install(SOURCE)
        self.assertEqual(config.read_text(), updated)

    def test_qutebrowser_symlink_and_line_endings_survive(self):
        real = self.home / 'dotfiles/qutebrowser.py'
        real.parent.mkdir()
        original = b'# settings\r\nkeys = []\r\n'
        real.write_bytes(original)
        config = self.home / '.config/qutebrowser/config.py'
        config.parent.mkdir(parents=True)
        config.symlink_to(real)
        installer.install(SOURCE)
        self.assertTrue(config.is_symlink())
        self.assertTrue(real.read_bytes().endswith(b'keys = []\r\n'))
        self.assertTrue(real.read_bytes().startswith(b'# settings\r\n'))

    def test_invalid_qutebrowser_config_stops_before_installation_writes(self):
        config = self.home / '.config/qutebrowser/config.py'
        config.parent.mkdir(parents=True)
        for text in ('if then\n', installer.QUTEBROWSER_BEGIN + '\n',
                     installer.QUTEBROWSER_END + '\n' + installer.QUTEBROWSER_BEGIN + '\n'):
            config.write_text(text)
            with self.assertRaises(ValueError):
                installer.install(SOURCE)
            self.assertEqual(config.read_text(), text)
            self.assertFalse((self.home / '.local/bin/chthm').exists())

    def test_snippet_ignores_markers_inside_strings_and_has_safe_fallback(self):
        import runpy
        loader = SOURCE / 'src/chthm/qtile_palette.py'
        original = 'text = """\n' + installer.QTILE_BEGIN + '\n' + installer.QTILE_END + '\n"""\n'
        updated = installer.qtile_config(original, loader)
        self.assertTrue(updated.endswith(original))
        namespace = {}
        exec(compile(updated, 'config.py', 'exec'), namespace)
        self.assertRegex(namespace['chthm_background'], r'^#[0-9a-fA-F]{6}$')
        self.assertEqual(namespace['text'], '\n' + installer.QTILE_BEGIN + '\n' + installer.QTILE_END + '\n')

    def test_qtile_snippet_enables_qt6ct_only_with_managed_environment_entry(self):
        loader = SOURCE / 'src/chthm/qtile_palette.py'
        updated = installer.qtile_config('', loader)
        marker = self.home / '.config/environment.d/60-chthm-qt6ct.conf'
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.home / '.config')}, clear=False), \
                patch.object(shutil, 'which', return_value='/usr/bin/qt6ct'):
            os.environ.pop('QT_QPA_PLATFORMTHEME', None)
            exec(compile(updated, 'config.py', 'exec'), {})
            self.assertNotIn('QT_QPA_PLATFORMTHEME', os.environ)
            marker.parent.mkdir(parents=True)
            marker.write_text('QT_QPA_PLATFORMTHEME=qt6ct\n')
            exec(compile(updated, 'config.py', 'exec'), {})
            self.assertEqual(os.environ['QT_QPA_PLATFORMTHEME'], 'qt6ct')

    def test_qutebrowser_palette_is_independent_and_keeps_other_settings(self):
        import runpy
        from types import SimpleNamespace
        from unittest.mock import Mock
        from chthm.theme import Theme
        config = self.home / '.config/qutebrowser/config.py'
        config.parent.mkdir(parents=True)
        original = ("config.load_autoconfig(False)\n"
                    "config.bind('J', 'tab-prev')\n"
                    "c.colors.tabs.even.bg = chthm_background\n"
                    "c.colors.tabs.even.fg = chthm_foreground\n")
        config.write_text(original)
        state = self.home / '.local/state/chthm/current.toml'
        state.parent.mkdir(parents=True)
        source = self.home / 'palette.toml'
        source.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        state.write_text(Theme.load(source).snapshot_toml())
        installer.install(SOURCE)
        source.unlink()  # No original theme or Alacritty configuration is needed.
        browser_config = Mock()
        c = SimpleNamespace(colors=SimpleNamespace(tabs=SimpleNamespace(even=SimpleNamespace())))
        runpy.run_path(str(config), init_globals={'config': browser_config, 'c': c})
        self.assertEqual(c.colors.tabs.even.bg, '#112233')
        self.assertEqual(c.colors.tabs.even.fg, '#ddeeff')
        browser_config.load_autoconfig.assert_called_once_with(False)
        browser_config.bind.assert_called_once_with('J', 'tab-prev')
        self.assertFalse((self.home / '.config/alacritty').exists())

    def test_absent_qutebrowser_config_is_not_created(self):
        installer.install(SOURCE)
        self.assertFalse((self.home / '.config/qutebrowser').exists())

    def test_uninstalled_applications_leave_stale_configs_untouched(self):
        files = {
            self.home / '.config/alacritty/theme.toml': 'invalid = true\n',
            self.home / '.config/qtile/config.py': 'if then\n',
            self.home / '.config/qutebrowser/config.py': 'if then\n',
        }
        for filename, content in files.items():
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text(content)
        with patch.object(installer.shutil, 'which', return_value=None):
            installer.install(SOURCE)
        for filename, content in files.items():
            self.assertEqual(filename.read_text(), content)

    def test_template_palettes_are_connected_and_restore_defaults_without_block(self):
        import runpy
        from chthm.theme import Theme
        state = self.home / '.local/state/chthm/current.toml'
        state.parent.mkdir(parents=True)
        source = self.home / 'selected.toml'
        source.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        state.write_text(Theme.load(source).snapshot_toml())
        original = ('"""Standalone config."""\nfrom __future__ import annotations\n'
                    'colors = {"primary": {"background": "#000000", "foreground": "#ffffff"}}\n'
                    'widget_defaults = dict(background=colors["primary"]["background"])\n'
                    'keys = ["keep"]\n')
        configs = []
        for app in ('qtile', 'qutebrowser'):
            filename = self.home / '.config' / app / 'config.py'
            filename.parent.mkdir(parents=True)
            filename.write_text(original)
            configs.append(filename)
        installer.install(SOURCE)
        for filename, label in zip(configs, ('Qtile', 'qutebrowser')):
            updated = filename.read_text()
            begin = f"# >>> chthm {label} palette >>>"
            end = f"# <<< chthm {label} palette <<<"
            start = updated.index(begin)
            stop = updated.index(end) + len(end) + 1
            self.assertLess(updated.index('colors = {'), start)
            self.assertIn('colors = chthm_colors', updated[start:stop])
            self.assertEqual(updated[:start] + updated[stop:], original)
            loaded = runpy.run_path(str(filename))
            self.assertEqual(loaded['widget_defaults']['background'], '#112233')
            self.assertEqual(loaded['keys'], ['keep'])
            restored = {}
            exec(updated[:start] + updated[stop:], restored)
            self.assertEqual(restored['widget_defaults']['background'], '#000000')
        before = [filename.read_bytes() for filename in configs]
        installer.install(SOURCE)
        self.assertEqual([filename.read_bytes() for filename in configs], before)

    def test_template_detection_does_not_execute_or_rebind_other_color_definitions(self):
        loader = SOURCE / 'src/chthm/qtile_palette.py'
        for original in ('colors = arbitrary_loader()\n',
                         'colors = {"primary": {"background": 1, "foreground": 2}}\n',
                         'colors = {"unrelated": "data"}\n'):
            updated = installer.qutebrowser_config(original, loader)
            self.assertNotIn('colors = chthm_colors', updated)
            self.assertTrue(updated.endswith(original))

    def test_existing_palette_block_moves_after_a_new_default_table(self):
        loader = SOURCE / 'src/chthm/qtile_palette.py'
        defaults = 'colors = {"primary": {"background": "#000000", "foreground": "#ffffff"}}\n'
        original = installer.qtile_config('', loader) + defaults + 'bg = colors["primary"]["background"]\n'
        updated = installer.qtile_config(original, loader)
        self.assertLess(updated.index(defaults), updated.index(installer.QTILE_BEGIN))
        self.assertEqual(updated.count(installer.QTILE_BEGIN), 1)
        self.assertEqual(installer.qtile_config(updated, loader), updated)

    def test_alacritty_install_adopts_standalone_palette_and_is_repeatable(self):
        directory = self.home / '.config/alacritty'
        directory.mkdir(parents=True)
        selector = directory / 'theme.toml'
        original = '[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n'
        selector.write_text(original)
        selector.chmod(0o640)
        main = directory / 'alacritty.toml'
        main.write_text('general.import=["theme.toml"]\n[window]\nopacity=0.9\n')
        main_before = main.read_bytes()
        installer.install(SOURCE)
        imported = tomllib.loads(selector.read_text())['general']['import']
        self.assertEqual(imported, [str(directory / 'chthm-colors.toml')])
        self.assertEqual(tomllib.loads(Path(imported[0]).read_text())['colors']['primary'],
                         tomllib.loads(original)['colors']['primary'])
        self.assertEqual(selector.stat().st_mode & 0o777, 0o640)
        self.assertEqual(main.read_bytes(), main_before)
        before = selector.read_bytes()
        installer.install(SOURCE)
        self.assertEqual(selector.read_bytes(), before)

    def test_alacritty_install_preserves_selector_symlink(self):
        directory = self.home / '.config/alacritty'
        directory.mkdir(parents=True)
        target = self.home / 'palette.toml'
        target.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        (directory / 'theme.toml').symlink_to(target)
        installer.install(SOURCE)
        self.assertTrue((directory / 'theme.toml').is_symlink())
        self.assertIn('chthm-colors.toml', target.read_text())

    def test_invalid_alacritty_selector_stops_before_installation_writes(self):
        directory = self.home / '.config/alacritty'
        directory.mkdir(parents=True)
        for original in ('not toml', 'general.import="wrong"\n',
                         '[window]\nopacity=0.9\n'):
            selector = directory / 'theme.toml'
            selector.write_text(original)
            with self.assertRaises(ValueError):
                installer.install(SOURCE)
            self.assertEqual(selector.read_text(), original)
            self.assertFalse((self.home / '.local/bin/chthm').exists())



    def test_installer_updates_existing_files_without_timestamped_backups(self):
        shell = self.home / '.zshrc'
        shell.write_text('# keep my shell settings\n')
        for app in ('qtile', 'qutebrowser'):
            config = self.home / '.config' / app / 'config.py'
            config.parent.mkdir(parents=True)
            config.write_text('keys = []\n')
        alacritty = self.home / '.config/alacritty/theme.toml'
        alacritty.parent.mkdir(parents=True)
        alacritty.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        installer.install(SOURCE)
        installer.install(SOURCE)
        self.assertFalse(any(self.home.rglob('*.chthm-back*')))
        self.assertTrue(shell.read_text().startswith('# keep my shell settings\n'))
        self.assertEqual(shell.read_text().count(installer.BEGIN), 1)

    def test_installer_sets_up_shared_qt_environment_and_removes_conflicting_overrides(self):
        from chthm.theme import Theme
        theme = self.home / 'current.toml'
        theme.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        snapshot = self.home / '.local/state/chthm/current.toml'
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text(Theme.load(theme).snapshot_toml())
        config = self.home / '.config'
        native = config / 'qt6ct/qt6ct.conf'
        native.parent.mkdir(parents=True)
        native.write_text('[Appearance]\nstyle=Fusion\nicon_theme=Adwaita\n[Fonts]\ngeneral="Cantarell,22"\n')
        clementine = config / 'Clementine/Clementine.conf'
        clementine.parent.mkdir()
        clementine.write_text('[Appearance]\nuse-custom-set=true\nbackground-color=keep\n')
        stylesheet = config / 'chthm/pcmanfm-qt.qss'
        stylesheet.parent.mkdir()
        stylesheet.write_text('/* Generated by chthm: PCManFM-Qt only. */\n')
        desktop = self.home / '.local/share/applications/pcmanfm-qt.desktop'
        desktop.parent.mkdir(parents=True)
        desktop.write_text('[Desktop Entry]\nName=Files\nExec="/usr/bin/pcmanfm-qt" "-stylesheet" "' + str(stylesheet) + '" %U\n')
        qtile = config / 'qtile/config.py'
        qtile.parent.mkdir()
        qtile.write_text('keys = []\n')
        real_which = installer.shutil.which
        with patch.object(installer.shutil, 'which', side_effect=lambda name, **kw:
                          '/usr/bin/qt6ct' if name == 'qt6ct' else real_which(name, **kw)):
            installer.install(SOURCE)
        self.assertIn('custom_palette=true', native.read_text())
        self.assertIn('general="Cantarell,22"', native.read_text())
        self.assertIn('#ff112233', (config / 'qt6ct/colors/chthm.conf').read_text())
        self.assertIn('use-custom-set=true', clementine.read_text())
        self.assertIn('background-color=keep', clementine.read_text())
        self.assertNotIn('-stylesheet', desktop.read_text())
        self.assertFalse(stylesheet.exists())
        self.assertEqual((config / 'environment.d/60-chthm-qt6ct.conf').read_text(), 'QT_QPA_PLATFORMTHEME=qt6ct\n')
        self.assertIn('QT_QPA_PLATFORMTHEME', qtile.read_text())
        self.assertFalse(any(self.home.rglob('*.chthm-back*')))

    def test_missing_qt6ct_skips_shared_theme_and_override_cleanup(self):
        clementine = self.home / '.config/Clementine/Clementine.conf'
        clementine.parent.mkdir(parents=True)
        original = '[Appearance]\nuse-custom-set=true\n'
        clementine.write_text(original)
        with patch.object(installer.shutil, 'which', return_value=None):
            self.assertEqual(installer.qt6ct_install_plan(SOURCE, self.home / '.config', self.home / '.local/share'), ([], []))
        self.assertEqual(clementine.read_text(), original)
        self.assertFalse((self.home / '.config/qt6ct').exists())

    def test_qt6ct_without_a_default_qt6_application_is_not_configured(self):
        with patch.object(installer.shutil, 'which',
                          side_effect=lambda name: '/usr/bin/qt6ct' if name == 'qt6ct' else None):
            self.assertEqual(
                installer.qt6ct_install_plan(
                    SOURCE, self.home / '.config', self.home / '.local/share'),
                ([], []))
        self.assertFalse((self.home / '.config/qt6ct').exists())

    def test_qt6ct_setup_rejects_overlapping_destinations(self):
        settings = self.home / '.config/chthm/config.toml'
        settings.parent.mkdir(parents=True)
        destination = self.home / 'same.conf'
        settings.write_text(f'qt6ct_config="{destination}"\nqt6ct_palette="{destination}"\n')
        with patch.object(installer.shutil, 'which', return_value='/usr/bin/qt6ct'):
            with self.assertRaisesRegex(ValueError, 'distinct'):
                installer.qt6ct_install_plan(SOURCE, self.home / '.config', self.home / '.local/share')
        self.assertFalse(destination.exists())

    def test_theme_collection_import_keeps_existing_files(self):
        collection = self.home / 'downloaded-themes'
        collection.mkdir()
        (collection / 'mine.toml').write_text('original downloaded theme')
        (collection / 'new.toml').write_text('new downloaded theme')
        destination = self.home / '.local/share/chthm/themes'
        destination.mkdir(parents=True)
        (destination / 'mine.toml').write_text('keep my changes')
        installer.install(SOURCE, theme_source=collection)
        self.assertEqual((destination / 'mine.toml').read_text(), 'keep my changes')
        self.assertEqual((destination / 'new.toml').read_text(), 'new downloaded theme')
        self.assertEqual((collection / 'mine.toml').read_text(), 'original downloaded theme')

    def test_legacy_selection_migrates_and_installs_palette_import(self):
        legacy = self.home / '.config/alacritty'
        themes = legacy / 'themes/themes'
        themes.mkdir(parents=True)
        selected = themes / 'selected.toml'
        selected.write_text('[colors.primary]\nbackground="#112233"\nforeground="#ddeeff"\n')
        selector = legacy / 'theme.toml'
        original = 'general.import=["themes/themes/selected.toml"]\n'
        selector.write_text(original)
        installer.install(SOURCE)
        from chthm.theme import Theme
        snapshot = self.home / '.local/state/chthm/current.toml'
        theme = Theme.from_snapshot(snapshot)
        self.assertEqual(theme.colors['primary']['background'], '#112233')
        self.assertEqual(theme.source, self.home / '.local/share/chthm/themes/selected.toml')
        imported = tomllib.loads(selector.read_text())["general"]["import"][0]
        self.assertEqual(Path(imported), legacy / 'chthm-colors.toml')
        self.assertEqual(tomllib.loads(Path(imported).read_text())['colors']['primary'],
                         {'background': '#112233', 'foreground': '#ddeeff'})
        self.assertTrue(selected.is_file())
        self.assertFalse((self.home / '.local/share/chthm/examples').exists())
        self.assertFalse((self.home / '.config/qtile').exists())

    def test_default_install_downloads_upstream_themes_and_license(self):
        installer.install(SOURCE)
        self.download.assert_called_once_with()
        collection = self.home / '.local/share/chthm/themes'
        self.assertTrue((collection / 'kimbie_dark.toml').is_file())
        self.assertEqual((collection / '.sources/alacritty-theme/LICENSE').read_text(), 'Test license text')
        self.assertIn(installer.THEME_REPOSITORY, (collection / '.sources/alacritty-theme/SOURCE.txt').read_text())

    def test_explicit_collection_never_downloads(self):
        collection = self.home / 'offline-themes'
        collection.mkdir()
        (collection / 'offline.toml').write_text('[colors.primary]\nbackground="#000000"\nforeground="#ffffff"\n')
        installer.install(SOURCE, theme_source=collection)
        self.download.assert_not_called()
        self.assertTrue((self.home / '.local/share/chthm/themes/offline.toml').is_file())

    def test_download_failure_uses_existing_local_themes_and_installs_commands(self):
        self.download.side_effect = OSError('offline')
        legacy = self.home / '.config/alacritty/themes/themes'
        legacy.mkdir(parents=True)
        (legacy / 'offline.toml').write_text('local original')
        with contextlib.redirect_stderr(io.StringIO()):
            installer.install(SOURCE)
        self.assertEqual((self.home / '.local/share/chthm/themes/offline.toml').read_text(), 'local original')
        self.assertTrue((self.home / '.local/share/chthm/themes/kimbie_dark.toml').is_file())
        self.assertTrue((self.home / '.local/bin/chthm').is_file())
        self.assertTrue((legacy / 'offline.toml').is_file())

    def test_download_failure_installs_working_bundled_default_on_fresh_system(self):
        self.download.side_effect = OSError('offline')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            installer.install(SOURCE)
        collection = self.home / '.local/share/chthm/themes'
        fallback = collection / 'kimbie_dark.toml'
        self.assertEqual(fallback.read_bytes(), (SOURCE / 'themes/kimbie_dark.toml').read_bytes())
        provenance = collection / '.sources/bundled-kimbie-dark'
        self.assertTrue((provenance / 'LICENSE').is_file())
        self.assertIn(installer.THEME_REPOSITORY, (provenance / 'SOURCE.txt').read_text())
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        result = subprocess.run(
            [str(self.home / '.local/bin/chthm'), '--dry-run', '--no-reload', '--targets', ''],
            env=environment, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(fallback), result.stderr)

    def test_bundled_fallback_never_replaces_an_existing_default(self):
        self.download.side_effect = OSError('offline')
        fallback = self.home / '.local/share/chthm/themes/kimbie_dark.toml'
        fallback.parent.mkdir(parents=True)
        fallback.write_text('my locally edited default\n')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            installer.install(SOURCE)
        self.assertEqual(fallback.read_text(), 'my locally edited default\n')
        self.assertFalse(
            (fallback.parent / '.sources/bundled-kimbie-dark').exists())

    def test_upstream_fetch_preserves_existing_user_edits(self):
        collection = self.home / 'collection'
        collection.mkdir()
        original = 'my local theme edits'
        (collection / 'kimbie_dark.toml').write_text(original)
        self.assertEqual(installer.fetch_upstream_themes(collection), 0)
        self.assertEqual((collection / 'kimbie_dark.toml').read_text(), original)

    def test_archive_never_extracts_scripts_or_traversal_paths(self):
        valid = '[colors.primary]\nbackground="#000000"\nforeground="#ffffff"\n'
        self.download.return_value = theme_archive({'themes/good.toml': valid,
            'themes/../../outside.toml': valid, 'script.py': 'do not execute',
            'images/picture.png': 'not palette data'})
        collection = self.home / 'collection'
        self.assertEqual(installer.fetch_upstream_themes(collection), 1)
        self.assertEqual({p.name for p in collection.iterdir()}, {'good.toml', '.sources'})
        self.assertFalse((self.home / 'outside.toml').exists())
        self.assertFalse((self.home / 'script.py').exists())

    def test_invalid_upstream_data_is_rejected_before_any_theme_write(self):
        self.download.return_value = theme_archive({'themes/good.toml': '[colors.primary]\nbackground="#000000"\nforeground="#ffffff"\n',
            'themes/bad.toml': 'colors=[]'})
        collection = self.home / 'collection'
        with self.assertRaises(ValueError):
            installer.fetch_upstream_themes(collection)
        self.assertFalse(collection.exists())

    def test_network_reader_has_timeout_and_size_limit(self):
        self.download_patch.stop()
        response = io.BytesIO(b'x' * 65)
        with patch.object(installer, 'MAX_ARCHIVE_BYTES', 64), \
             patch.object(installer, 'urlopen', return_value=response) as open_url:
            with self.assertRaises(ValueError):
                installer.download_theme_archive()
        self.assertEqual(open_url.call_args.kwargs, {'timeout': 20})
        self.assertEqual(open_url.call_args.args[0].full_url, installer.THEME_ARCHIVE)

    def test_root_install_is_refused(self):
        with patch.object(installer.os, 'geteuid', return_value=0), \
             patch.object(installer, 'install') as install, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(installer.main([]), 1)
            install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
