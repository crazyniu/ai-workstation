"""Hermetic icon HTTP discovery, request isolation, bounds, and address policy."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import favicon

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')


class FixtureHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.requests.append((self.path, dict(self.headers)))
        headers = {}
        status = 200
        if self.path == '/entry':
            status, body = 302, b''
            headers = {'Location': '/nested/page', 'Set-Cookie': 'remote_identity=never-forward'}
        elif self.path == '/nested/page':
            body = b'<html><link rel="shortcut icon" href="../assets/icon.png"></html>'
        elif self.path == '/svg':
            body = b'<link rel="icon" href="/unsafe.svg">'
        elif self.path == '/unsafe.svg':
            body = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
            headers['Content-Type'] = 'image/svg+xml'
        elif self.path == '/big':
            body = b'x' * (favicon.MAX_IMAGE + 1)
        elif self.path == '/loop':
            status, body = 302, b''
            headers['Location'] = '/loop'
        elif self.path == '/metadata':
            status, body = 302, b''
            headers['Location'] = 'http://169.254.169.254/latest/meta-data/'
        elif self.path in ('/assets/icon.png', '/favicon.ico'):
            body = PNG
            headers['Content-Type'] = 'image/png'
        else:
            status, body = 404, b'not found'
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if 'Content-Type' not in headers:
            self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class FaviconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.worker = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.worker.join()

    def setUp(self):
        FixtureHandler.requests.clear()
        favicon._cache.clear()

    def fixture_access(self):
        # Only this local test server bypasses the production loopback prohibition.
        original = favicon.allowed_address
        return patch.object(favicon, 'allowed_address', side_effect=lambda address: address == '127.0.0.1' or original(address))

    def test_relative_icon_after_redirect_without_cookie_or_business_headers(self):
        with self.fixture_access():
            self.assertEqual(favicon.get_icon(self.base + '/entry'), (PNG, 'image/png'))
        self.assertEqual([url for url, _ in FixtureHandler.requests], ['/entry', '/nested/page', '/assets/icon.png'])
        for _, headers in FixtureHandler.requests:
            self.assertNotIn('Cookie', headers)
            self.assertNotIn('Authorization', headers)
            self.assertNotIn('Referer', headers)
            self.assertEqual(headers['Accept-Encoding'], 'identity')

    def test_svg_is_rejected_and_origin_favicon_is_used(self):
        with self.fixture_access():
            self.assertEqual(favicon.get_icon(self.base + '/svg'), (PNG, 'image/png'))
        self.assertEqual([url for url, _ in FixtureHandler.requests], ['/svg', '/unsafe.svg', '/favicon.ico'])
        self.assertIsNone(favicon.image_type(b'<svg><script>alert(1)</script></svg>'))
        self.assertIsNone(favicon.image_type(b'<html><img src=x></html>'))

    def test_byte_limit_and_redirect_limit(self):
        with self.fixture_access():
            for path in ('/big', '/loop'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    favicon.fetch(self.base + path, favicon.MAX_IMAGE, time.monotonic() + 5)
        self.assertEqual(sum(path == '/loop' for path, _ in FixtureHandler.requests), favicon.MAX_REDIRECTS + 1)

    def test_metadata_redirect_is_checked_before_any_connection(self):
        with self.fixture_access(), self.assertRaises(ValueError):
            favicon.fetch(self.base + '/metadata', favicon.MAX_HTML, time.monotonic() + 5)
        self.assertEqual(len(FixtureHandler.requests), 1)

    def test_lan_and_public_are_allowed_but_local_control_and_metadata_are_not(self):
        for address in ('192.168.1.249', '10.0.0.5', '172.16.4.5', '8.8.8.8', 'fd12::1234', '100.70.1.2'):
            self.assertTrue(favicon.allowed_address(address), address)
        for address in ('127.0.0.1', '0.0.0.0', '169.254.169.254', '100.100.100.200', '168.63.129.16',
                        '224.0.0.1', '::1', 'fe80::1', 'fd00:ec2::254', '::ffff:169.254.169.254'):
            self.assertFalse(favicon.allowed_address(address), address)
        self.assertEqual(favicon.normalize_url('http://192.168.1.249:9999/'), 'http://192.168.1.249:9999/')

    def test_invalid_urls_and_mixed_dns_answers_are_rejected(self):
        for url in ('file:///etc/passwd', 'ftp://site.test/icon', 'http://user:pass@site.test/',
                    'http://site.test\\@127.0.0.1/', 'http://metadata.google.internal/',
                    'http://localhost/', 'http://[fe80::1%eth0]/', 'http://site.test:99999/', 'http://site.test/\nHost:x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                favicon.normalize_url(url)
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80)) for ip in ('8.8.8.8', '127.0.0.1')]
        with patch.object(socket, 'getaddrinfo', return_value=answers), self.assertRaises(ValueError):
            favicon.resolve('site.test', 80, time.monotonic() + 3)

    def test_cache_is_bounded_and_caches_missing_icons(self):
        with patch.object(favicon, 'discover', return_value=(PNG, 'image/png')) as discover:
            for _ in range(2):
                self.assertEqual(favicon.get_icon('https://site.test/'), (PNG, 'image/png'))
            self.assertEqual(discover.call_count, 1)
            for index in range(favicon.MAX_CACHE + 4):
                favicon.get_icon('https://site.test/' + str(index))
            self.assertEqual(len(favicon._cache), favicon.MAX_CACHE)
        with patch.object(favicon, 'discover', return_value=None) as discover:
            self.assertIsNone(favicon.get_icon('https://missing.test/'))
            self.assertIsNone(favicon.get_icon('https://missing.test/'))
            self.assertEqual(discover.call_count, 1)


if __name__ == '__main__':
    unittest.main()
