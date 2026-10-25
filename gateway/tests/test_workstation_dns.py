"""Fixed-source policy and transactional per-client updates without live services."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import state
import workstation_dns as dns


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.source = '192.0.2.51'
        self.proxy = 'fixed-exit'
        self.config = {'mode': 'rule', 'tun': {'enable': True}, 'secret': 'never-print-fixture',
                       'proxies': [{'name': self.proxy, 'type': 'socks5', 'password': 'private-fixture'}],
                       'proxy-groups': [{'name': 'AUTO', 'type': 'select', 'proxies': ['DIRECT', self.proxy]}],
                       'dns': {'nameserver': ['223.5.5.5']},
                       'rules': ['DOMAIN-SUFFIX,example.cn,DIRECT', 'MATCH,AUTO']}

    def test_fixed_source_precedes_country_rules_without_changing_other_clients(self):
        original = copy.deepcopy(self.config)
        result = dns.pinned_config(self.config, self.source, self.proxy)
        self.assertEqual(self.config, original)
        self.assertEqual(result['rules'][2:], original['rules'])
        self.assertEqual(result['dns'], original['dns'])
        self.assertEqual(result['proxy-groups'], original['proxy-groups'])
        dns.validate_pinned(result, self.source, self.proxy)
        self.assertEqual(dns.pinned_config(result, self.source, self.proxy), result)

    def test_endpoint_cannot_be_direct_or_an_automatic_group(self):
        for name in ['AUTO', 'DIRECT', 'missing']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                dns.pinned_config(self.config, self.source, name)
        self.config['proxies'] = [{'name': self.proxy, 'type': 'direct'}]
        with self.assertRaises(ValueError):
            dns.pinned_config(self.config, self.source, self.proxy)

    def test_no_dns_switch_when_rules_can_intercept_or_fall_back(self):
        pinned = dns.pinned_config(self.config, self.source, self.proxy)
        for earlier in ['MATCH,DIRECT', 'DOMAIN-SUFFIX,cn,DIRECT',
                        f'AND,((SRC-IP-CIDR,{self.source}/32),(NETWORK,UDP)),DIRECT']:
            modified = copy.deepcopy(pinned)
            modified['rules'].insert(0, earlier)
            with self.subTest(earlier=earlier), self.assertRaises(ValueError):
                dns.validate_pinned(modified, self.source, self.proxy)
        pinned['rules'].pop(1)
        with self.assertRaises(ValueError):
            dns.validate_pinned(pinned, self.source, self.proxy)

    def test_existing_other_source_dns_rules_are_compatible(self):
        config = dns.pinned_config(self.config, self.source, self.proxy)
        config['rules'].insert(0, 'AND,((SRC-IP-CIDR,198.18.0.1/32),(DOMAIN,dns.google)),fixed-exit')
        dns.validate_pinned(config, self.source, self.proxy)

    def test_private_dns_and_filter_settings_survive_without_public_dns_overrides(self):
        old = {'name': 'Keep name', 'ids': [self.source], 'uid': 'fixture-id',
               'use_global_settings': False, 'filtering_enabled': True,
               'upstreams': ['https://dns.alidns.com/dns-query',
                             '[/home.arpa/lan/local/]127.0.0.1:53',
                             '[/fixture.ts.net/]100.100.100.100',
                             '[/example.cn/]223.5.5.5']}
        result = dns.dns_client(old, self.source, 5354)
        self.assertEqual(result['upstreams'], ['tcp://192.0.2.51:5354',
                         '[/home.arpa/lan/local/]127.0.0.1:53', '[/fixture.ts.net/]100.100.100.100'])
        for key in old.keys() - {'upstreams'}:
            self.assertEqual(result[key], old[key])
        self.assertEqual(old['upstreams'][0], 'https://dns.alidns.com/dns-query')

    def test_shared_client_identifier_cannot_change_other_devices(self):
        with self.assertRaises(ValueError):
            dns.dns_client({'ids': [self.source, '192.0.2.52']}, self.source, 5354)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        PolicyTests.setUp(self)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'mihomo').mkdir()
        (self.root / 'backups').mkdir()
        self.patches = [patch.object(state, 'ROOT', self.root),
                        patch.object(state, 'CONFIG', self.root / 'mihomo/config.yaml'),
                        patch.object(dns, 'probe_resolver'), patch.object(dns, 'validate_mihomo'),
                        patch.object(dns, 'reload_mihomo')]
        for p in self.patches:
            p.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        state.write_config(dns.pinned_config(self.config, self.source, self.proxy))
        self.clients = [{'name': 'Target', 'ids': [self.source], 'upstreams': ['https://dns.example/dns-query'],
                         'use_global_settings': True},
                        {'name': 'Other', 'ids': ['192.0.2.52'], 'upstreams': ['223.5.5.5']}]
        self.calls = []
        api_patch = patch.object(dns, 'request', self.api)
        api_patch.start()
        self.addCleanup(api_patch.stop)

    def api(self, path, data=None, **kwargs):
        self.calls.append(path)
        if path == '/configs':
            return {'mode': 'rule', 'tun': {'enable': True}}
        if path == '/clients':
            return {'clients': copy.deepcopy(self.clients)}
        if path == '/clients/update':
            index = next(i for i, c in enumerate(self.clients) if c['name'] == data['name'])
            self.clients[index] = copy.deepcopy(data['data'])
        elif path == '/clients/add':
            self.clients.append(copy.deepcopy(data))
        elif path == '/clients/delete':
            self.clients = [c for c in self.clients if c['name'] != data['name']]
        return {}

    def test_client_apply_and_rollback_preserve_other_devices_and_proxy_bytes(self):
        before, config = copy.deepcopy(self.clients), state.CONFIG.read_bytes()
        result = dns.configure('dns', self.source, self.proxy, 5354, True)
        self.assertEqual(self.clients[1], before[1])
        self.assertEqual(state.CONFIG.read_bytes(), config)
        self.assertEqual(self.clients[0]['upstreams'], ['tcp://192.0.2.51:5354'])
        self.assertEqual(Path(result['backup']).stat().st_mode & 0o777, 0o700)
        dns.rollback(result['backup'], True)
        self.assertEqual(self.clients, before)

    def test_a_new_client_can_be_removed_by_rollback(self):
        self.clients.pop(0)
        before = copy.deepcopy(self.clients)
        result = dns.configure('dns', self.source, self.proxy, 5354, True)
        dns.rollback(result['backup'], True)
        self.assertEqual(self.clients, before)

    def test_failed_probe_makes_no_changes(self):
        before = copy.deepcopy(self.clients)
        dns.probe_resolver.side_effect = OSError('unreachable')
        with self.assertRaises(OSError):
            dns.configure('dns', self.source, self.proxy, 5354, True)
        self.assertEqual(self.clients, before)
        self.assertNotIn('/clients/update', self.calls)
        self.assertEqual(list((self.root / 'backups').iterdir()), [])

    def test_rollback_refuses_to_overwrite_later_client_edits(self):
        result = dns.configure('dns', self.source, self.proxy, 5354, True)
        self.clients[0]['name'] = 'User edit after deployment'
        with self.assertRaisesRegex(ValueError, 'changed since apply'):
            dns.rollback(result['backup'], True)
        self.assertEqual(self.clients[0]['name'], 'User edit after deployment')

    def test_failed_route_reload_restores_exact_original_bytes(self):
        state.write_config(self.config)
        before = state.CONFIG.read_bytes()
        dns.reload_mihomo.side_effect = [OSError('reload failed'), None]
        with self.assertRaises(OSError):
            dns.configure('route', self.source, self.proxy, 5354, True)
        self.assertEqual(state.CONFIG.read_bytes(), before)

    def test_probe_cannot_overwrite_a_concurrent_client_edit(self):
        def edit(*args):
            self.clients[0]['name'] = 'Edited while resolver was being checked'
        dns.probe_resolver.side_effect = edit
        with self.assertRaisesRegex(ValueError, 'changed during validation'):
            dns.configure('dns', self.source, self.proxy, 5354, True)
        self.assertNotIn('/clients/update', self.calls)

    def test_failed_update_restores_a_partially_applied_client_change(self):
        before = copy.deepcopy(self.clients)
        attempts = 0
        def fail_after_commit(path, data=None, **kwargs):
            nonlocal attempts
            result = self.api(path, data, **kwargs)
            if path == '/clients/update':
                attempts += 1
                if attempts == 1:
                    raise OSError('Connection lost after the API committed the update')
            return result
        with patch.object(dns, 'request', fail_after_commit), self.assertRaises(OSError):
            dns.configure('dns', self.source, self.proxy, 5354, True)
        self.assertEqual(self.clients, before)

    def test_dry_run_never_probes_or_modifies_config_or_exposes_credentials(self):
        before = state.CONFIG.read_bytes()
        result = dns.configure('dns', self.source, self.proxy, 5354)
        self.assertNotIn('private-fixture', json.dumps(result))
        dns.probe_resolver.assert_not_called()
        self.assertEqual(state.CONFIG.read_bytes(), before)
        self.assertEqual(list((self.root / 'backups').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
