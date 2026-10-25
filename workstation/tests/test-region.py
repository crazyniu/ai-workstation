"""Region selection, safe initialization and deployment contracts."""
import importlib.util
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('region', ROOT / 'workstation/runtime/region.py')
REGION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REGION)


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for path in ('etc/workstation', 'etc/default', 'etc/profile.d',
                     'usr/share/i18n/locales', 'usr/share/zoneinfo/Asia',
                     'usr/share/zoneinfo/America'):
            (self.root / path).mkdir(parents=True)
        for name in ('en_SG', 'zh_TW', 'en_US'):
            (self.root / 'usr/share/i18n/locales' / name).touch()
        for name in ('Asia/Singapore', 'Asia/Taipei', 'America/New_York', 'America/Los_Angeles'):
            (self.root / 'usr/share/zoneinfo' / name).write_bytes(b'TZif-fixture')
        (self.root / 'usr/share/zoneinfo/zone.tab').write_text('not a compiled timezone')
        self.run = Mock(return_value=subprocess.CompletedProcess([], 0, 'C\nen_SG.utf8\n'))

    def tearDown(self):
        self.temp.cleanup()

    def test_default_singapore_english_reaches_login_config(self):
        (self.root / 'etc/environment').write_text('KEEP=existing\nLANG=old\nTZ=old\n')
        selected = REGION.configure_region(self.root, {}, self.run)
        self.assertEqual(selected, {'LANG': 'en_SG.UTF-8', 'LC_ALL': 'en_SG.UTF-8',
                                    'LANGUAGE': 'en_SG:en', 'TZ': 'Asia/Singapore',
                                    'WORKSTATION_COUNTRY': 'SG', 'WORKSTATION_LANGUAGE': 'en',
                                    'WORKSTATION_TIMEZONE': 'Asia/Singapore'})
        self.run.assert_called_once()
        self.assertIn('KEEP=existing\n', (self.root / 'etc/environment').read_text())
        self.assertNotIn('=old', (self.root / 'etc/environment').read_text())
        self.assertIn('LANGUAGE=en_SG:en', (self.root / 'etc/default/locale').read_text())
        self.assertIn('export LANG=en_SG.UTF-8',
                      (self.root / 'etc/profile.d/workstation-region.sh').read_text())
        self.assertEqual((self.root / 'etc/localtime').readlink(),
                         Path('/usr/share/zoneinfo/Asia/Singapore'))

    def test_custom_locale_is_generated_without_inheriting_invalid_locale(self):
        selected = REGION.configure_region(self.root, {'WORKSTATION_COUNTRY': 'TW',
            'WORKSTATION_LANGUAGE': 'zh', 'WORKSTATION_TIMEZONE': 'Asia/Taipei',
            'LC_ALL': 'invalid'}, self.run)
        self.assertEqual(selected['LANG'], 'zh_TW.UTF-8')
        command, = self.run.call_args.args
        self.assertEqual(command, ['localedef', '-i', 'zh_TW', '-f', 'UTF-8', 'zh_TW.UTF-8'])
        self.assertEqual(self.run.call_args.kwargs['env']['LC_ALL'], 'C.UTF-8')
        self.assertEqual((self.root / 'etc/timezone').read_text(), 'Asia/Taipei\n')

    def test_singapore_uses_utc_plus_eight_all_year(self):
        zone = ZoneInfo(REGION.DEFAULTS['timezone'])
        self.assertEqual(datetime(2026, 1, 15, tzinfo=zone).utcoffset(), timedelta(hours=8))
        self.assertEqual(datetime(2026, 7, 15, tzinfo=zone).utcoffset(), timedelta(hours=8))

    def test_taiwan_english_uses_real_locales_and_resets_when_changed_back(self):
        config = self.root / 'etc/workstation/region.json'
        config.write_text(json.dumps({'country': 'TW', 'language': 'en', 'timezone': 'Asia/Taipei'}))
        selected = REGION.configure_region(self.root, {}, self.run)
        self.assertEqual(selected['LANG'], 'en_US.UTF-8')
        self.assertEqual(selected['LANGUAGE'], 'en_US:en')
        self.assertEqual(selected['LC_MESSAGES'], 'en_US.UTF-8')
        self.assertEqual(selected['LC_ALL'], '')
        self.assertEqual(selected['LC_MONETARY'], 'zh_TW.UTF-8')
        self.assertEqual(selected['LC_ADDRESS'], 'zh_TW.UTF-8')
        self.assertEqual(selected['TZ'], 'Asia/Taipei')
        self.assertEqual(selected['WORKSTATION_COUNTRY'], 'TW')
        self.assertNotIn('WORKSTATION_', (self.root / 'etc/default/locale').read_text())
        self.assertIn('WORKSTATION_COUNTRY=TW', (self.root / 'etc/environment').read_text())
        generated = [call.args[0] for call in self.run.call_args_list[1:]]
        self.assertEqual(generated, [
            ['localedef', '-i', 'en_US', '-f', 'UTF-8', 'en_US.UTF-8'],
            ['localedef', '-i', 'zh_TW', '-f', 'UTF-8', 'zh_TW.UTF-8']])
        config.write_text('{}')
        REGION.configure_region(self.root, {}, self.run)
        self.assertNotIn('zh_TW', (self.root / 'etc/environment').read_text())
        self.assertNotIn('LC_MONETARY=', (self.root / 'etc/default/locale').read_text())
        self.assertIn('unset LC_NUMERIC',
                      (self.root / 'etc/profile.d/workstation-region.sh').read_text())

    def test_internal_file_overrides_environment_and_survives_repeated_init(self):
        config = self.root / 'etc/workstation/region.json'
        config.write_text(json.dumps({'country': 'US', 'language': 'en', 'timezone': 'America/New_York'}))
        environment = {'WORKSTATION_COUNTRY': 'SG', 'WORKSTATION_LANGUAGE': 'en'}
        first = REGION.configure_region(self.root, environment, self.run)
        self.assertEqual(first['LANG'], 'en_US.UTF-8')
        second = REGION.configure_region(self.root, environment, self.run)
        self.assertEqual(first, second)
        self.assertEqual((self.root / 'etc/environment').read_text().count('LANG='), 1)
        self.assertTrue(config.exists())

    def test_invalid_settings_fail_before_writes_or_commands(self):
        for overrides in ({'country': 'sg'}, {'country': 'SG;id'}, {'language': 'en_US'},
                          {'language': 'xx'}, {'timezone': '../etc/passwd'},
                          {'timezone': '/etc/passwd'}, {'timezone': 'Asia/Nowhere'},
                          {'timezone': 'zone.tab'},
                          {'timezone': 'Asia/Singapore\nLANG=bad'}, {'timezone': 123},
                          {'typo': 'SG'}, []):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                REGION.select_region({}, overrides, self.root)
        self.assertFalse((self.root / 'etc/timezone').exists())
        self.run.assert_not_called()

    def test_timezone_symlink_cannot_escape_zoneinfo(self):
        (self.root / 'usr/share/zoneinfo/escape').symlink_to(self.root / 'etc')
        (self.root / 'etc/outside').touch()
        with self.assertRaises(ValueError):
            REGION.select_region({}, {'timezone': 'escape/outside'}, self.root)

    def test_bad_override_file_fails_before_system_changes(self):
        config = self.root / 'etc/workstation/region.json'
        for text in ('{', '[]', '{"country": "sg"}', ' ' * 4097):
            config.write_text(text)
            with self.assertRaises(ValueError):
                REGION.configure_region(self.root, {}, self.run)
        config.unlink()
        config.symlink_to(self.root / 'etc/environment')
        with self.assertRaises(ValueError):
            REGION.configure_region(self.root, {}, self.run)
        self.run.assert_not_called()
        self.assertFalse((self.root / 'etc/timezone').exists())

    def test_generation_failure_does_not_change_login_config(self):
        self.run.side_effect = [subprocess.CompletedProcess([], 0, 'C\n'),
                                subprocess.CalledProcessError(1, 'localedef')]
        with self.assertRaises(subprocess.CalledProcessError):
            REGION.configure_region(self.root, {}, self.run)
        self.assertFalse((self.root / 'etc/default/locale').exists())


if __name__ == '__main__':
    unittest.main()
