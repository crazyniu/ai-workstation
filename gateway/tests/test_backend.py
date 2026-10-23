"""Hermetic backend regressions: no Docker, production hosts, or live services."""
import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import legacy
import releases
import server
import state
import updates
import yaml

PNG_PIXEL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='


class DataTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name).resolve()
        self.dash = self.root / 'dashboard'
        self.config = self.root / 'mihomo/config.yaml'
        self.patches = [
            patch.object(state, 'ROOT', self.root), patch.object(state, 'DASH', self.dash),
            patch.object(state, 'CONFIG', self.config), patch.object(server, 'ROOT', self.root),
            patch.object(server, 'DASH', self.dash), patch.object(server, 'CONFIG', self.config),
            patch.object(updates, 'ROOT', self.root), patch.object(legacy, 'DATA', self.dash),
            patch.object(legacy, 'CARDS', self.dash / 'cards.json'),
            patch.object(legacy, 'MIHOMO_DIR', self.config.parent),
            patch.object(legacy, 'MIHOMO_CONFIG', self.config),
            patch.dict(os.environ, {'GATEWAY_LAN_ADDRESS': '192.0.2.251/24'}),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(self.scratch.cleanup)
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        state.write_config({'secret': 'local-controller-key', 'external-controller': '127.0.0.1:9090',
                            'redir-port': 7892, 'tproxy-port': 7893, 'ipv6': False,
                            'dns': {'fake-ip-filter': []}, 'proxies': [], 'rules': ['MATCH,DIRECT']})
        state.atomic(self.root / 'adguard/AdGuardHome.yaml', yaml.safe_dump({
            'http': {'address': '127.0.0.1:3000'}, 'dns': {'port': 5353},
            'filtering': {'rewrites': [{'domain': 'home.arpa', 'answer': '192.0.2.251'}]}}))
        state.save(self.dash / 'settings.json', state.settings())
        state.atomic(self.dash / 'session-key', 'a' * 64)
        self.original_config = self.config.read_bytes()

    def archive(self, entries):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name, body in entries.items():
                body = body.encode() if isinstance(body, str) else body
                member = tarfile.TarInfo(name)
                member.size = len(body)
                archive.addfile(member, io.BytesIO(body))
        return stream.getvalue()

    def restore_package(self, **overrides):
        settings = state.settings()
        settings['domain'] = 'gateway.home.arpa'
        entries = {'mihomo/config.yaml': yaml.safe_dump({'secret': 'foreign', 'dns': {'listen': ':9'},
                                                        'redir-port': 999, 'proxies': [], 'rules': ['MATCH,DIRECT']}),
                   'dashboard/settings.json': json.dumps(settings)}
        entries.update(overrides)
        return self.archive(entries)


class FilterSeedTests(DataTest):
    def setUp(self):
        super().setUp()
        self.seed=self.root/'seed';(self.seed/'filters').mkdir(parents=True)
        self.content=b'! official fixture\n||doubleclick.net^\n'
        self.url='https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt'
        (self.seed/'filters/adguard-dns.txt').write_bytes(self.content)
        state.save(self.seed/'filters/manifest.json',{'sha256':hashlib.sha256(self.content).hexdigest(),'update_url':self.url})
        self.settings={'filters':[{'id':1,'enabled':True,'url':self.url}]}
        self.target=self.root/'adguard/work/data/filters/1.txt'

    def test_default_filter_is_seeded_once_and_existing_cache_is_preserved(self):
        self.assertTrue(state.seed_adguard_filter(self.seed,self.settings))
        self.assertEqual(self.target.read_bytes(),self.content)
        self.target.write_bytes(b'newer user filter cache')
        self.assertFalse(state.seed_adguard_filter(self.seed,self.settings))
        self.assertEqual(self.target.read_bytes(),b'newer user filter cache')

    def test_disabled_or_custom_filter_is_not_replaced(self):
        for entry in ({'id':1,'enabled':False,'url':self.url},
                      {'id':1,'enabled':True,'url':'https://example.invalid/custom'},
                      {'id':2,'enabled':True,'url':self.url}):
            self.assertFalse(state.seed_adguard_filter(self.seed,{'filters':[entry]}))
            self.assertFalse(self.target.exists())

    def test_corrupt_snapshot_is_rejected_before_creating_cache(self):
        (self.seed/'filters/adguard-dns.txt').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):state.seed_adguard_filter(self.seed,self.settings)
        self.assertFalse(self.target.exists())


class AuthTests(DataTest):
    def setUp(self):
        super().setUp()
        server.FAILURES.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.url = 'http://127.0.0.1:' + str(self.http.server_port)
        self.addCleanup(self.close)

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()

    def request(self, path, data=None, cookie=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if cookie:
            headers['Cookie'] = cookie
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as response:
            return response

    def test_setup_login_and_private_configuration(self):
        with self.request('/api/proxy/config') as response:
            self.assertEqual(response.status, 401)
        with self.request('/api/auth/setup', {'password': 'strong-password-123'}) as response:
            self.assertEqual(response.status, 200)
            cookie = response.headers['Set-Cookie'].split(';')[0]
            self.assertIn('HttpOnly', response.headers['Set-Cookie'])
            self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        with self.request('/api/proxy/config', cookie=cookie) as response:
            self.assertEqual(response.status, 200)
            self.assertIn('revision', json.load(response))
        with self.request('/api/auth/setup', {'password': 'another-password-123'}) as response:
            self.assertEqual(response.status, 400)
        with self.request('/api/auth/login', {'password': 'wrong'}) as response:
            self.assertEqual(response.status, 401)
        with self.request('/api/auth/login', {'password': 'strong-password-123'}) as response:
            self.assertEqual(response.status, 200)

    def test_cross_origin_setup_is_rejected_without_mutation(self):
        with self.request('/api/auth/setup', {'password': 'strong-password-123'}, origin='https://elsewhere.invalid') as response:
            self.assertEqual(response.status, 403)
        self.assertFalse((self.dash / 'admin.json').exists())

    def test_favicon_requires_login_and_returns_only_safe_image_headers(self):
        url='/api/favicon?url=http%3A%2F%2F192.168.1.249%3A9999%2F'
        png=base64.b64decode(PNG_PIXEL.split(',')[1])
        with patch.object(server.favicon,'get_icon',return_value=(png,'image/png')) as fetch:
            with self.request(url) as response:self.assertEqual(response.status,401)
            fetch.assert_not_called()
            with self.request('/api/auth/setup',{'password':'a'}) as response:
                cookie=response.headers['Set-Cookie'].split(';')[0]
            with self.request(url,cookie=cookie) as response:
                self.assertEqual(response.status,200)
                self.assertEqual(response.headers['Content-Type'],'image/png')
                self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
                self.assertIn('sandbox',response.headers['Content-Security-Policy'])
                self.assertEqual(response.read(),png)
            fetch.assert_called_once_with('http://192.168.1.249:9999/')
        with patch.object(server.favicon,'get_icon',return_value=None):
            with self.request(url,cookie=cookie) as response:self.assertEqual(response.status,404)

    def test_auto_icon_saves_without_fetching_and_preserves_existing_manual_card(self):
        with self.request('/api/auth/setup',{'password':'a'}) as response:
            cookie=response.headers['Set-Cookie'].split(';')[0]
        with patch.object(server.favicon,'get_icon') as fetch:
            for name,icon in [('Existing','server'),('NAS','auto')]:
                with self.request('/api/cards',{'name':name,'url':'http://192.168.1.249:9999/','icon':icon},cookie=cookie) as response:
                    self.assertEqual(response.status,201)
            fetch.assert_not_called()
        with self.request('/api/cards',cookie=cookie) as response:
            cards=json.load(response)['cards']
        saved={card['name']:card for card in cards}
        self.assertEqual(saved['Existing']['icon'],'server')
        self.assertEqual(saved['NAS']['icon'],'auto')

    def test_default_admin_login_and_password_change_preserves_new_session(self):
        with patch.dict(os.environ, {}, clear=True):state.initialize_admin()
        with self.request('/api/auth/login', {'password': 'admin'}) as response:
            self.assertEqual(response.status, 200)
            old_cookie = response.headers['Set-Cookie'].split(';')[0]
        before = (self.dash / 'admin.json').read_bytes()
        for data, cookie, origin, status in (
            ({'current_password': 'admin', 'password': 'x'}, None, None, 401),
            ({'current_password': 'admin', 'password': 'x'}, old_cookie, 'https://elsewhere.invalid', 403),
            ({'current_password': 'wrong', 'password': 'x'}, old_cookie, None, 400),
            ({'current_password': 'admin', 'password': ''}, old_cookie, None, 400),
            ({'current_password': 'admin', 'password': 'x' * 257}, old_cookie, None, 400)):
            with self.request('/api/password', data, cookie=cookie, origin=origin) as response:
                self.assertEqual(response.status, status)
            self.assertEqual((self.dash / 'admin.json').read_bytes(), before)
        with self.request('/api/password', {'current_password': 'admin', 'password': 'x'}, cookie=old_cookie) as response:
            self.assertEqual(response.status, 200)
            new_cookie = response.headers['Set-Cookie'].split(';')[0]
        with self.request('/api/settings', cookie=old_cookie) as response:self.assertEqual(response.status, 401)
        with self.request('/api/settings', cookie=new_cookie) as response:self.assertEqual(response.status, 200)
        with self.request('/api/auth/login', {'password': 'admin'}) as response:self.assertEqual(response.status, 401)
        with self.request('/api/auth/login', {'password': 'x'}) as response:self.assertEqual(response.status, 200)
        with patch.dict(os.environ, {'GATEWAY_ADMIN_PASSWORD': 'replacement'}):state.initialize_admin()
        self.assertTrue(state.password_valid('x', state.read(self.dash / 'admin.json')['password']))

    def test_old_appearance_read_is_normalized_without_rewriting_file(self):
        with self.request('/api/auth/setup', {'password': 'a'}) as response:
            cookie = response.headers['Set-Cookie'].split(';')[0]
        old = {'fit': 'contain', 'image': ''}
        state.save(self.dash / 'appearance.json', old)
        with self.request('/api/appearance', cookie=cookie) as response:
            self.assertEqual(json.load(response), dict(old, theme='auto', wallpaper='coast'))
        self.assertEqual(state.read(self.dash / 'appearance.json'), old)

    def test_invalid_and_expired_sessions_rejected(self):
        for cookie in ('gateway_session=broken', 'gateway_session=1.invalid'):
            with self.request('/api/settings', cookie=cookie) as response:
                self.assertEqual(response.status, 401)

    def test_cards_are_persistent_and_order_requires_complete_set(self):
        with self.request('/api/auth/setup', {'password': 'strong-password-123'}) as response:
            cookie = response.headers['Set-Cookie'].split(';')[0]
        for name in ('NAS', 'Router'):
            with self.request('/api/cards', {'name': name, 'url': 'http://192.0.2.249:9999', 'icon': 'server'}, cookie=cookie) as response:
                self.assertEqual(response.status, 201)
        cards = legacy.read_cards()
        with self.request('/api/cards/order', {'ids': [cards[1]['id'], cards[0]['id']]}, cookie=cookie) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(legacy.read_cards()[0]['name'], 'Router')
        with self.request('/api/cards/order', {'ids': []}, cookie=cookie) as response:
            self.assertEqual(response.status, 400)

    def test_appearance_requires_login_for_read_and_write(self):
        for data in (None, {'fit': 'cover', 'image': PNG_PIXEL}):
            with self.request('/api/appearance', data) as response:
                self.assertEqual(response.status, 401)
        self.assertFalse((self.dash / 'appearance.json').exists())

    def test_appearance_persists_and_is_in_backup(self):
        with self.request('/api/auth/setup', {'password': 'strong-password-123'}) as response:
            cookie = response.headers['Set-Cookie'].split(';')[0]
        with self.request('/api/appearance', cookie=cookie) as response:
            self.assertEqual(json.load(response), {'fit': 'cover', 'image': '', 'theme': 'auto', 'wallpaper': 'coast'})
        value = {'fit': 'contain', 'image': PNG_PIXEL, 'theme': 'dark', 'wallpaper': 'forest'}
        with self.request('/api/appearance', value, cookie=cookie) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), value)
        self.assertEqual(state.read(self.dash / 'appearance.json'), value)
        with self.request('/api/appearance', cookie=cookie) as response:
            self.assertEqual(json.load(response), value)
        with self.request('/api/backup', cookie=cookie) as response:
            backup = base64.b64decode(json.load(response)['data'])
        with tarfile.open(fileobj=io.BytesIO(backup), mode='r:gz') as archive:
            self.assertEqual(json.load(archive.extractfile('dashboard/appearance.json')), value)

    def test_appearance_rejects_svg_and_preserves_saved_wallpaper(self):
        with self.request('/api/auth/setup', {'password': 'strong-password-123'}) as response:
            cookie = response.headers['Set-Cookie'].split(';')[0]
        original = {'fit': 'cover', 'image': PNG_PIXEL}
        state.save(self.dash / 'appearance.json', original)
        svg = base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>').decode()
        for mime in ('svg+xml', 'png'):
            with self.subTest(mime=mime):
                with self.request('/api/appearance', {'image': 'data:image/' + mime + ';base64,' + svg}, cookie=cookie) as response:
                    self.assertEqual(response.status, 400)
                self.assertEqual(state.read(self.dash / 'appearance.json'), original)
        with self.request('/api/appearance', {'fit': 'tile', 'image': ''}, cookie=cookie,
                          origin='https://elsewhere.invalid') as response:
            self.assertEqual(response.status, 403)
        self.assertEqual(state.read(self.dash / 'appearance.json'), original)

    @patch.object(legacy.subprocess, 'run', return_value=Mock(returncode=0))
    @patch.object(legacy, 'controller_request', return_value=b'{}')
    @patch.object(server, 'fetch_subscription', return_value='proxies: []\nrules: [MATCH,DIRECT]\n')
    def test_subscription_import_and_refresh_use_authenticated_transaction(self, fetch, controller, run):
        with self.request('/api/auth/setup', {'password': 'strong-password-123'}) as response:
            cookie = response.headers['Set-Cookie'].split(';')[0]
        with self.request('/api/subscription', {'url': 'https://example.invalid/sub', 'interval_hours': 6}, cookie=cookie) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(json.load(response)['ok'])
        self.assertEqual(state.settings()['subscription']['interval_hours'], 6)
        self.assertTrue(state.read(self.dash / 'proxy-state.json')['configured'])
        with self.request('/api/subscription/refresh', {}, cookie=cookie) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(json.load(response)['ok'])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(state.config()['secret'], 'local-controller-key')

    @patch.object(legacy.subprocess, 'run', return_value=Mock(returncode=1))
    @patch.object(server, 'fetch_subscription', return_value='proxies: []\n')
    def test_rejected_subscription_keeps_previous_subscription_settings(self, fetch, run):
        with self.request('/api/auth/setup', {'password': 'strong-password-123'}) as response:
            cookie = response.headers['Set-Cookie'].split(';')[0]
        with self.request('/api/subscription', {'url': 'https://example.invalid/sub', 'interval_hours': 6}, cookie=cookie) as response:
            self.assertEqual(response.status, 400)
        self.assertEqual(self.config.read_bytes(), self.original_config)
        self.assertEqual(state.settings()['subscription']['url'], '')
        self.assertFalse((self.dash / 'proxy-state.json').exists())


class AppearanceTests(DataTest):
    def test_allowed_fits_and_default_wallpaper(self):
        for fit in ('cover', 'contain', 'stretch', 'center', 'tile'):
            with self.subTest(fit=fit):
                self.assertEqual(server.validate_appearance({'fit': fit, 'image': PNG_PIXEL, 'theme': 'auto', 'wallpaper': 'coast'}),
                                 {'fit': fit, 'image': PNG_PIXEL, 'theme': 'auto', 'wallpaper': 'coast'})
        self.assertEqual(server.validate_appearance({}), {'fit': 'cover', 'image': '', 'theme': 'auto', 'wallpaper': 'coast'})

    def test_theme_wallpaper_selections_and_injection(self):
        for theme in ('light', 'dark', 'auto'):
            for wallpaper in ('coast', 'mountain', 'dusk', 'forest'):
                self.assertEqual(server.validate_appearance({'theme': theme, 'wallpaper': wallpaper}),
                                 {'fit': 'cover', 'image': '', 'theme': theme, 'wallpaper': wallpaper})
        for value in ({'theme': 'system'}, {'wallpaper': '../secret'}, {'wallpaper': 'url(javascript:alert(1))'},
                      {'theme': None}, {'wallpaper': ['coast']}):
            with self.subTest(value=value), self.assertRaises(ValueError):server.validate_appearance(value)

    def test_icon_catalog_allows_only_bundled_svg_ids(self):
        icons = self.root / 'web/icons'
        icons.mkdir(parents=True)
        (icons / 'docker.svg').write_text('<svg/>')
        state.save(icons / 'catalog.json', [{'id': 'docker'}, {'id': 'missing'}, {'id': '../secret'}])
        fake_source = self.root / 'app/server.py'
        with patch.object(server, '__file__', str(fake_source)), patch.object(server.Path, 'is_dir', return_value=False):
            self.assertTrue(server.valid_card_icon('docker'))
            for icon in ('missing', '../secret', '/tmp/icon', 'docker.svg', 'Docker', 'unknown'):
                self.assertFalse(server.valid_card_icon(icon), icon)

    def test_bad_image_formats_and_sizes_are_rejected(self):
        bad_images = [None, 7, 'https://example.invalid/wallpaper.png',
                      'data:image/png;base64,not-base64!', 'data:image/png;base64,a',
                      'data:image/jpeg;base64,' + PNG_PIXEL.split(',', 1)[1],
                      'data:image/gif;base64,R0lGODlh',
                      'data:image/png;base64,' + 'A' * (4 * 1024 * 1024)]
        for image in bad_images:
            with self.subTest(image_type=type(image).__name__, prefix=str(image)[:40]):
                with self.assertRaises(ValueError):
                    server.validate_appearance({'image': image})
        with self.assertRaises(ValueError):
            server.validate_appearance({'fit': 'url(javascript:alert(1))'})

    def test_restore_rejects_malicious_wallpaper_before_mutating_services(self):
        malicious = {'fit': 'cover', 'image': 'data:image/svg+xml;base64,PHN2Zy8+'}
        package = self.restore_package(**{'dashboard/appearance.json': json.dumps(malicious)})
        with patch.object(updates, 'control') as control:
            with self.assertRaises(ValueError):
                server.restore(package)
            control.assert_not_called()
        self.assertEqual(self.config.read_bytes(), self.original_config)
        self.assertFalse((self.dash / 'appearance.json').exists())


class ImportTests(DataTest):
    def handler(self, content, revision=None):
        h = server.Handler.__new__(server.Handler)
        h.headers = {}
        h.body = lambda *args: {'content': content, 'filename': 'import.yaml',
                                'revision': revision or legacy.revision(self.config.read_bytes())}
        h.reply = Mock()
        return h

    @patch.object(legacy.subprocess, 'run', return_value=Mock(returncode=0))
    @patch.object(legacy, 'controller_request', return_value=b'{}')
    def test_import_preserves_gateway_identity_and_listeners(self, controller, run):
        h = self.handler('proxies: []\nrules: [MATCH,DIRECT]\nsecret: foreign\nredir-port: 99\ndns: {listen: ":9"}\nproxy-providers: null\n')
        legacy.Handler.apply_config(h)
        self.assertEqual(h.reply.call_args.args[0], 200)
        result = state.config()
        self.assertEqual(result['secret'], 'local-controller-key')
        self.assertEqual(result['redir-port'], 7892)
        self.assertEqual(result['dns']['fake-ip-filter'], [])
        self.assertEqual(result['proxy-providers'], {})
        self.assertEqual(result['hosts']['home.arpa'],'192.0.2.251')
        self.assertEqual(run.call_args.kwargs['env']['SAFE_PATHS'],str(self.root))

    @patch.object(legacy.subprocess, 'run', return_value=Mock(returncode=0))
    @patch.object(legacy, 'controller_request', return_value=b'{}')
    def test_import_keeps_custom_hosts_and_restores_configured_local_domain(self, controller, run):
        settings=state.settings();settings['domain']='gateway.home.arpa'
        state.save(self.dash/'settings.json',settings)
        h=self.handler('proxies: []\nhosts:\n  gateway.home.arpa: 203.0.113.1\n  nas.home.arpa: 192.0.2.249\n')
        legacy.Handler.apply_config(h)
        self.assertEqual(h.reply.call_args.args[0],200)
        self.assertEqual(state.config()['hosts'],{'gateway.home.arpa':'192.0.2.251','nas.home.arpa':'192.0.2.249'})

    @patch.object(legacy.subprocess, 'run', return_value=Mock(returncode=0))
    @patch.object(legacy, 'controller_request')
    def test_failed_provider_refresh_restores_config_and_cache(self, controller, run):
        cache = self.config.parent / 'providers/nodes.yaml'
        state.atomic(cache, 'old node cache')
        controller.side_effect = [b'{}', ValueError('download failed'), b'{}']
        h = self.handler('proxies: []\nproxy-providers:\n  Nodes:\n    type: http\n    path: providers/nodes.yaml\n    url: https://example.invalid/nodes\n')
        legacy.Handler.apply_config(h)
        self.assertEqual(h.reply.call_args.args[0], 400)
        self.assertEqual(self.config.read_bytes(), self.original_config)
        self.assertEqual(cache.read_text(), 'old node cache')
        self.assertEqual(controller.call_count, 3)

    def test_stale_revision_cannot_apply(self):
        h = self.handler('proxies: []', 'stale')
        legacy.Handler.apply_config(h)
        self.assertEqual(h.reply.call_args.args[0], 409)
        self.assertEqual(self.config.read_bytes(), self.original_config)

    def test_provider_paths_cannot_escape_or_overwrite_config(self):
        outside = self.root / 'private'
        outside.mkdir()
        (self.config.parent / 'escape').symlink_to(outside)
        for path in ('../private/secret', '/etc/passwd', 'config.yaml', 'escape/secret'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                legacy.validate_providers({'rule-providers': {'a': {'path': path}}})


class RestoreTests(DataTest):
    @patch.object(updates, 'wait_health')
    @patch.object(updates, 'control')
    @patch.object(server, 'command')
    def test_restore_keeps_local_network_identity_and_rewrites_domain(self, command, control, health):
        server.restore(self.restore_package())
        result = state.config()
        self.assertEqual(result['secret'], 'local-controller-key')
        self.assertEqual(result['redir-port'], 7892)
        self.assertEqual(result['tproxy-port'], 7893)
        self.assertFalse(result['ipv6'])
        self.assertEqual(result['hosts']['gateway.home.arpa'], '192.0.2.251')
        agh = yaml.safe_load((self.root / 'adguard/AdGuardHome.yaml').read_text())
        self.assertEqual(agh['filtering']['rewrites'], [{'domain': 'gateway.home.arpa', 'answer': '192.0.2.251'}])

    @patch.object(updates, 'wait_health', side_effect=[ValueError('new failed'), None, None, None])
    @patch.object(updates, 'control')
    @patch.object(server, 'command')
    def test_health_failure_restores_adguard_even_if_missing_from_archive(self, command, control, health):
        before = {p: p.read_bytes() for p in (self.config, self.dash / 'settings.json', self.root / 'adguard/AdGuardHome.yaml')}
        with self.assertRaisesRegex(ValueError, '已回退'):
            server.restore(self.restore_package())
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)

    @patch.object(updates, 'control')
    def test_rejects_archive_traversal_and_invalid_settings_before_stopping(self, control):
        for payload in (self.archive({'../bad': 'x'}), self.restore_package(**{'dashboard/settings.json': '{}'})):
            with self.assertRaises(ValueError):
                server.restore(payload)
        control.assert_not_called()

    @patch.object(updates, 'wait_health')
    @patch.object(updates, 'control')
    @patch.object(server, 'command')
    def test_snapshot_copy_failure_preserves_live_files(self, command, control, health):
        before = self.config.read_bytes()
        with patch.object(server.shutil, 'copy2', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(ValueError, '已回退'):
                server.restore(self.restore_package())
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(state.settings()['domain'], 'home.arpa')

    @patch.object(updates, 'control')
    @patch.object(server, 'command')
    def test_restore_failure_recovers_provider_cache_modified_during_start(self, command, control):
        cache=self.root/'mihomo/providers/nodes.yaml'
        state.atomic(cache,'old nodes')
        def fail_new_health(component):
            if cache.read_text()=='old nodes' and state.settings()['domain']=='gateway.home.arpa':
                state.atomic(cache,'corrupt new cache')
                raise ValueError('failed new configuration')
        with patch.object(updates,'wait_health',side_effect=fail_new_health):
            with self.assertRaisesRegex(ValueError,'已回退'):
                server.restore(self.restore_package())
        self.assertEqual(cache.read_text(),'old nodes')


class UpgradeTests(DataTest):
    def setUp(self):
        super().setUp()
        self.prior = self.root / 'components/versions/panel/old'
        self.prior.mkdir(parents=True)
        (self.prior / 'index.html').write_text('old')
        self.link = self.root / 'components/current/panel'
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(self.prior)
        self.manifest = {'component': 'panel', 'version': 'v2'}

    def install(self, manifest, dest):
        dest.mkdir(parents=True)
        (dest / 'index.html').write_text('new')

    @patch.object(updates, 'control')
    def test_download_failure_does_not_stop_service(self, control):
        with patch.object(updates, 'install_asset', side_effect=ValueError('bad digest')):
            with self.assertRaises(ValueError):
                updates.upgrade('panel', self.manifest)
        control.assert_not_called()
        self.assertEqual(self.link.resolve(), self.prior)

    @patch.object(updates, 'command')
    @patch.object(updates, 'control')
    @patch.object(updates, 'wait_health')
    def test_partial_snapshot_never_overwrites_working_data(self, health, control, command):
        before = self.config.read_bytes()
        def incomplete(source, dest, **kwargs):
            dest.mkdir(parents=True)
            (dest / 'partial').write_text('incomplete')
            raise OSError('disk full')
        with patch.object(updates, 'install_asset', side_effect=self.install), patch.object(updates.shutil, 'copytree', side_effect=incomplete):
            with self.assertRaisesRegex(ValueError, '已恢复'):
                updates.upgrade('panel', self.manifest)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.link.resolve(), self.prior)

    @patch.object(updates, 'command')
    @patch.object(updates, 'control')
    @patch.object(updates, 'wait_health', side_effect=[ValueError('failed'), None])
    def test_health_failure_restores_old_binary_and_data(self, health, control, command):
        before = self.config.read_bytes()
        with patch.object(updates, 'install_asset', side_effect=self.install):
            with self.assertRaisesRegex(ValueError, '已恢复'):
                updates.upgrade('panel', self.manifest)
        self.assertEqual(self.link.resolve(), self.prior)
        self.assertEqual(self.config.read_bytes(), before)

    @patch.object(updates, 'command')
    @patch.object(updates, 'control')
    @patch.object(updates, 'wait_health', side_effect=ValueError('still broken'))
    def test_failed_rollback_is_reported_accurately(self, health, control, command):
        with patch.object(updates, 'install_asset', side_effect=self.install):
            with self.assertRaisesRegex(ValueError, '自动恢复未通过'):
                updates.upgrade('panel', self.manifest)

    @patch.object(updates, 'control')
    @patch.object(updates, 'wait_health')
    def test_successful_upgrade_persists_new_target_and_backup(self, health, control):
        with patch.object(updates, 'install_asset', side_effect=self.install):
            result = updates.upgrade('panel', self.manifest)
        self.assertNotEqual(self.link.resolve(), self.prior)
        self.assertTrue((self.root / 'backups' / result['backup'] / 'mihomo/config.yaml').is_file())

    @patch.object(updates, 'tailscale_identity', return_value={'BackendState': 'Running', 'Self': {'ID': 'different'}, 'TailscaleIPs': ['100.64.0.2']})
    def test_tailscale_identity_change_fails_acceptance(self, status):
        with self.assertRaisesRegex(ValueError, '身份'):
            updates.verify_tailscale_identity({'BackendState': 'Running', 'Self': {'ID': 'original'}, 'TailscaleIPs': ['100.64.0.1']})

    @patch.object(updates.time,'sleep')
    @patch.object(updates,'health')
    def test_tailscale_restart_waits_until_original_identity_reconnects(self, health, sleep):
        baseline={'BackendState':'Running','Self':{'ID':'original'},'TailscaleIPs':['100.64.0.1']}
        with patch.object(updates,'tailscale_identity',side_effect=[{'BackendState':'Starting'},baseline]):
            updates.wait_health('tailscale',baseline)
        self.assertEqual(health.call_count,2)
        sleep.assert_called_once_with(1)


class StateTests(DataTest):
    def test_initial_admin_env_default_and_existing_password_preservation(self):
        with patch.dict(os.environ, {'GATEWAY_ADMIN_PASSWORD': 'a'}):state.initialize_admin()
        original = (self.dash / 'admin.json').read_bytes()
        self.assertTrue(state.password_valid('a', state.read(self.dash / 'admin.json')['password']))
        with patch.dict(os.environ, {'GATEWAY_ADMIN_PASSWORD': 'another'}):state.initialize_admin()
        self.assertEqual((self.dash / 'admin.json').read_bytes(), original)
        (self.dash / 'admin.json').unlink()
        with patch.dict(os.environ, {}, clear=True):state.initialize_admin()
        self.assertTrue(state.password_valid('admin', state.read(self.dash / 'admin.json')['password']))
        (self.dash / 'admin.json').unlink()
        with patch.dict(os.environ, {'GATEWAY_ADMIN_PASSWORD': ''}), self.assertRaises(ValueError):state.initialize_admin()
        self.assertFalse((self.dash / 'admin.json').exists())

    def test_password_scrypt_rejects_wrong_password(self):
        stored = state.password_hash('a secure password')
        self.assertTrue(state.password_valid('a secure password', stored))
        self.assertFalse(state.password_valid('different password', stored))

    def test_domain_rewrite_is_idempotent_and_avoids_fake_ip(self):
        state.domain_config('HOME.ARPA.')
        state.domain_config('home.arpa')
        c = state.config()
        self.assertEqual(c['hosts']['home.arpa'], '192.0.2.251')
        self.assertEqual(c['dns']['fake-ip-filter'].count('home.arpa'), 1)
        self.assertTrue(c['dns']['use-hosts'])

    def test_https_only_tlds_and_invalid_domains_rejected(self):
        for domain in ('home.dev', 'no spaces.arpa', '-bad.arpa', 'single'):
            with self.assertRaises(ValueError):
                state.local_domain(domain)

    @patch.object(updates, 'wait_health')
    @patch.object(updates, 'control')
    @patch.object(legacy, 'controller_request')
    def test_domain_change_stops_adguard_before_editing_and_validates(self, controller, control, health):
        server.update_domain('gateway.home.arpa')
        self.assertEqual(control.call_args_list[0].args, ('stop', 'adguard'))
        self.assertEqual(control.call_args_list[-1].args, ('start', 'adguard'))
        self.assertEqual(state.settings()['domain'], 'gateway.home.arpa')
        health.assert_called_once_with('adguard')

    @patch.object(server, 'command')
    @patch.object(updates, 'wait_health', side_effect=[ValueError('failed DNS'), None])
    @patch.object(updates, 'control')
    @patch.object(legacy, 'controller_request')
    def test_domain_health_failure_restores_both_yaml_and_settings(self, controller, control, health, command):
        paths=(self.config,self.root/'adguard/AdGuardHome.yaml',self.dash/'settings.json')
        before={p:p.read_bytes() for p in paths}
        with self.assertRaisesRegex(ValueError, '已恢复'):
            server.update_domain('gateway.home.arpa')
        for p,body in before.items():
            self.assertEqual(p.read_bytes(),body)


class AssetTests(DataTest):
    def test_wrong_digest_never_creates_component_directory(self):
        destination=self.root/'new-version'
        with patch.object(releases,'download',return_value=b'corrupt'):
            with self.assertRaisesRegex(ValueError,'SHA256'):
                releases.install_asset({'component':'panel','url':'https://example.invalid','sha256':'0'*64},destination)
        self.assertFalse(destination.exists())

    def test_unsafe_archive_paths_are_rejected(self):
        body=self.archive({'../secret':'malicious'})
        with patch.object(releases,'download',return_value=body):
            with self.assertRaisesRegex(ValueError,'不安全'):
                releases.install_asset({'component':'panel','url':'https://example.invalid','sha256':hashlib.sha256(body).hexdigest()},self.root/'new-version')
        self.assertFalse((self.root/'secret').exists())

    def test_valid_official_digest_extracts_panel_with_version_manifest(self):
        body=self.archive({'dist/index.html':'<html>dashboard</html>'})
        destination=self.root/'new-version'
        manifest={'component':'panel','version':'v2','url':'https://example.invalid','sha256':hashlib.sha256(body).hexdigest()}
        with patch.object(releases,'download',return_value=body):
            releases.install_asset(manifest,destination)
        self.assertEqual((destination/'index.html').read_text(),'<html>dashboard</html>')
        self.assertEqual(json.loads((destination/'version.json').read_text()),manifest)


if __name__ == '__main__':
    unittest.main()
