"""Automatic LAN routing and Tailscale connection lifecycle regressions."""
import json
import os
import subprocess
import time
from unittest.mock import Mock, patch

from test_backend import DataTest
import server
import state


def result(value=None, code=0):
    return Mock(returncode=code, stdout=json.dumps(value or {}))


class LanDiscoveryTests(DataTest):
    def test_configured_lan_uses_real_prefix_without_querying_control_bridge(self):
        with patch.dict(os.environ, {'GATEWAY_LAN_ADDRESS': '192.168.51.250/23'}), patch.object(state, 'command') as command:
            self.assertEqual(state.lan_networks(), ['192.168.50.0/23'])
            command.assert_not_called()

    def test_fallback_detects_all_global_subnets_only_on_lan_interface(self):
        addresses=[{'ifname':'eth1','addr_info':[
            {'family':'inet','local':'192.168.8.250','prefixlen':24,'scope':'global'},
            {'family':'inet','local':'10.20.0.5','prefixlen':16,'scope':'global'},
            {'family':'inet','local':'169.254.1.5','prefixlen':16,'scope':'link'},
            {'family':'inet','local':'100.80.0.5','prefixlen':24,'scope':'global'}]}]
        with patch.dict(os.environ, {}, clear=True), patch.object(state, 'command', side_effect=[result([{'dev':'eth1'}]),result(addresses)]) as command:
            self.assertEqual(state.lan_networks(), ['10.20.0.0/16','192.168.8.0/24'])
            self.assertEqual(command.call_args.args[0], ['ip','-j','-4','addr','show','dev','eth1'])

    def test_explicit_runtime_interface_wins_over_default_control_route(self):
        with patch.dict(os.environ, {'GATEWAY_RUNTIME_INTERFACE':'eth1'}, clear=True), patch.object(state, 'command', return_value=result([{'addr_info':[{'family':'inet','local':'192.168.9.1','prefixlen':24,'scope':'global'}]}])) as command:
            self.assertEqual(state.lan_networks(), ['192.168.9.0/24'])
            command.assert_called_once_with(['ip','-j','-4','addr','show','dev','eth1'])

    def test_never_advertises_vpn_control_bridge_default_or_host_routes(self):
        for iface in ('lo','docker0','br-control','vethabc','tailscale0','tun0','Mihomo'):
            with self.subTest(iface=iface), patch.dict(os.environ, {'GATEWAY_RUNTIME_INTERFACE':iface}, clear=True):
                with self.assertRaises(ValueError):state.lan_networks()
        for address in ('100.80.0.1/24','127.0.0.1/8','169.254.1.1/16','0.0.0.0/0','192.168.1.1/32','::1/128'):
            with self.subTest(address=address), patch.dict(os.environ, {'GATEWAY_LAN_ADDRESS':address}):
                with self.assertRaises(ValueError):state.lan_networks()


class AutomaticRoutingTests(DataTest):
    def setUp(self):
        super().setUp()
        self.routes=['192.0.2.0/24']
        self.current={'AdvertiseRoutes':self.routes,'RouteAll':True,'CorpDNS':False,'NoSNAT':False}
        self.running={'BackendState':'Running','HaveNodeKey':True,'TailscaleIPs':['100.64.0.4'],
                      'Self':{'Online':True,'HostName':'gateway'},'Peer':{'a':{'Online':True},'b':{'Online':False}}}
        self.addCleanup(server.JOBS.clear)
        server.JOBS.clear()

    def test_old_manual_preferences_migrate_and_preserve_other_settings(self):
        value=state.settings();value['tailscale']={'routes':'10.99.0.0/24','accept_routes':False}
        state.save(self.dash/'settings.json',value)
        with patch.object(server,'ts',side_effect=[result({'RouteAll':False,'CorpDNS':True}),result()]) as ts:
            prefs=server.configure_tailscale_routes()
        self.assertEqual(ts.call_args.args[0],['set','--accept-dns=false','--accept-routes=true','--snat-subnet-routes=true','--advertise-routes=192.0.2.0/24'])
        self.assertEqual(prefs,{'routes':'192.0.2.0/24','accept_routes':True,'auto_routes':True})
        self.assertEqual(state.settings()['subscription'],value['subscription'])
        self.assertEqual(state.settings()['domain'],value['domain'])

    def test_no_redundant_daemon_writes_when_preferences_match(self):
        with patch.object(server,'ts',return_value=result(self.current)) as ts:
            server.configure_tailscale_routes()
            before=(self.dash/'settings.json').stat().st_mtime_ns
            server.configure_tailscale_routes()
        self.assertEqual([call.args[0] for call in ts.call_args_list],[['debug','prefs'],['debug','prefs']])
        self.assertEqual((self.dash/'settings.json').stat().st_mtime_ns,before)

    def test_restart_checks_actual_preferences_even_when_saved_settings_match(self):
        with patch.object(server,'ts',return_value=result(self.current)):server.configure_tailscale_routes()
        with patch.object(server,'ts',side_effect=[result({'AdvertiseRoutes':[]}),result()]) as ts:
            server.configure_tailscale_routes()
            self.assertEqual(ts.call_args.args[0][0],'set')

    def test_failed_configuration_does_not_persist_false_success_and_retries(self):
        before=(self.dash/'settings.json').read_bytes()
        with patch.object(server,'tailscale_raw_status',return_value=self.running), patch.object(server,'ts',side_effect=[result(),result(code=1)]):
            server.maintain_tailscale_routes()
        self.assertEqual((self.dash/'settings.json').read_bytes(),before)
        self.assertIn('失败',state.read(self.dash/'tailscale-error.json')['error'])
        with patch.object(server,'tailscale_raw_status',return_value=self.running), patch.object(server,'ts',return_value=result(self.current)):
            server.maintain_tailscale_routes()
        self.assertFalse((self.dash/'tailscale-error.json').exists())
        self.assertTrue(state.settings()['tailscale']['auto_routes'])

    def test_no_reconnect_or_route_changes_after_disconnect_or_logout(self):
        for backend in ('Stopped','NeedsLogin','NeedsMachineAuth','Starting'):
            with self.subTest(backend=backend), patch.object(server,'tailscale_raw_status',return_value={'BackendState':backend}), patch.object(server,'configure_tailscale_routes') as configure:
                server.maintain_tailscale_routes();configure.assert_not_called()

    def test_background_does_not_interfere_with_running_upgrade_or_restore(self):
        server.JOBS['upgrade']={'status':'running'}
        with patch.object(server,'tailscale_raw_status') as status:
            server.maintain_tailscale_routes();status.assert_not_called()

    def test_login_with_authorization_url_preserves_full_profile(self):
        pending={'state':'NeedsLogin','login_url':'https://login.tailscale.com/a/example'}
        profile=dict(self.current,ControlURL='https://custom-control.example',Hostname='my-gateway',RunSSH=True,AdvertiseTags=['tag:gateway'])
        with patch.object(server,'tailscale_raw_status',return_value={'BackendState':'NeedsLogin','HaveNodeKey':True}), patch.object(server,'configure_tailscale_routes') as configure, patch.object(server,'ts',return_value=result(profile)), patch.object(server,'tailscale_local_api') as local_api, patch.object(server,'tailscale_status',return_value=pending):
            self.assertEqual(server.connect_tailscale(),pending)
            configure.assert_called_once()
            sent=local_api.call_args_list[0].args
            self.assertEqual(sent[0],'start');self.assertEqual(sent[1]['UpdatePrefs'],dict(profile,WantRunning=True,LoggedOut=False))
            self.assertEqual(local_api.call_args_list[1].args,('login-interactive',{}))

    def test_existing_exit_node_advertisement_does_not_trigger_repeated_writes(self):
        self.current['AdvertiseRoutes']+=['0.0.0.0/0','::/0']
        with patch.object(server,'ts',return_value=result(self.current)) as ts:
            server.configure_tailscale_routes()
            ts.assert_called_once_with(['debug','prefs'])

    def test_login_failure_without_authorization_url_is_reported(self):
        with patch.object(server,'tailscale_raw_status',return_value={'BackendState':'NeedsLogin'}), patch.object(server,'configure_tailscale_routes'), patch.object(server,'ts',return_value=result(self.current)), patch.object(server,'tailscale_local_api'), patch.object(server,'tailscale_status',return_value={'state':'NeedsLogin','login_url':''}), patch.object(server.time,'monotonic',side_effect=[0,9]):
            with self.assertRaisesRegex(ValueError,'无法连接'):server.connect_tailscale()

    def test_bad_preferences_never_start_or_reset_profile(self):
        with patch.object(server,'tailscale_raw_status',return_value=self.running), patch.object(server,'configure_tailscale_routes'), patch.object(server,'ts',return_value=result(code=1)), patch.object(server,'tailscale_local_api') as local_api:
            with self.assertRaisesRegex(ValueError,'无法读取'):server.connect_tailscale()
            local_api.assert_not_called()

    def test_connect_recovers_a_stopped_daemon(self):
        with patch.object(server,'tailscale_raw_status',side_effect=[{},self.running]), patch.object(server,'configure_tailscale_routes'), patch.object(server,'ts',return_value=result(self.current)), patch.object(server,'tailscale_local_api') as local_api, patch.object(server,'tailscale_status',return_value={'state':'Running','login_url':''}), patch.object(server.updates,'control') as control, patch.object(server.updates,'wait_health') as health:
            server.connect_tailscale();control.assert_called_once_with('start','tailscale');health.assert_called_once_with('tailscale')
            self.assertEqual(local_api.call_count,1)

    def test_status_distinguishes_published_route_from_active_route(self):
        with patch.object(server,'ts',return_value=result(self.current)):server.configure_tailscale_routes()
        with patch.object(server,'tailscale_raw_status',return_value=self.running):
            status=server.tailscale_status()
            self.assertEqual(status['route_state'],'pending');self.assertEqual(status['peers'],1)
        self.running['Self']['PrimaryRoutes']=self.routes
        with patch.object(server,'tailscale_raw_status',return_value=self.running):
            self.assertEqual(server.tailscale_status()['route_state'],'active')
        self.running['Self']['Online']=False
        with patch.object(server,'tailscale_raw_status',return_value=self.running):
            self.assertEqual(server.tailscale_status()['route_state'],'waiting')

    def test_daemon_failure_is_unavailable_instead_of_a_false_stopped_state(self):
        for response in (result(code=1),Mock(stdout='unparseable'),subprocess.TimeoutExpired('tailscale',15),FileNotFoundError()):
            kwargs={'side_effect':response} if isinstance(response,Exception) else {'return_value':response}
            with self.subTest(response=response), patch.object(server,'ts',**kwargs):
                self.assertEqual(server.tailscale_status()['state'],'Unavailable')

    def call_action(self,action):
        handler=object.__new__(server.Handler);handler.path='/api/tailscale/action'
        handler.same_origin=lambda:True;handler.authorized=lambda:True
        handler.body=lambda:{'action':action};handler.reply=Mock()
        handler.post();return handler.reply.call_args.args

    def test_disconnect_keeps_daemon_alive_and_identity_intact(self):
        for action in ('disconnect','stop'):
            with self.subTest(action=action), patch.object(server,'ts',return_value=result()) as ts, patch.object(server.updates,'control') as control, patch.object(server,'submit',side_effect=lambda kind,work:work()):
                self.assertEqual(self.call_action(action),(202,{'ok':True}))
                ts.assert_called_once_with(['down']);control.assert_not_called()

    def test_logout_is_separate_from_disconnect(self):
        with patch.object(server,'ts',return_value=result()) as ts, patch.object(server,'submit',side_effect=lambda kind,work:work()):
            self.assertEqual(self.call_action('logout'),(202,{'ok':True}))
            ts.assert_called_once_with(['logout'])

    def test_disconnect_and_logout_do_not_race_an_in_progress_connection(self):
        server.JOBS['connecting']={'status':'running'}
        for action in ('disconnect','logout'):
            with self.subTest(action=action), patch.object(server,'ts') as ts:
                with self.assertRaisesRegex(ValueError,'任务正在执行'):self.call_action(action)
                ts.assert_not_called()

    def test_service_restart_preserves_disconnected_state(self):
        with patch.object(server,'submit',side_effect=lambda kind,work:work()), patch.object(server.updates,'control'), patch.object(server.updates,'wait_health'), patch.object(server,'tailscale_raw_status',return_value={'BackendState':'Stopped'}), patch.object(server,'tailscale_status',return_value={'state':'Stopped'}), patch.object(server,'connect_tailscale') as connect:
            self.assertEqual(self.call_action('restart'),(202,{'state':'Stopped'}))
            connect.assert_not_called()

    def test_manual_route_payload_is_replaced_by_detected_lan(self):
        handler=object.__new__(server.Handler);handler.path='/api/tailscale/settings'
        handler.same_origin=lambda:True;handler.authorized=lambda:True
        handler.body=lambda:{'routes':'0.0.0.0/0','accept_routes':False};handler.reply=Mock()
        with patch.object(server,'ts',side_effect=[result(),result()]) as ts:
            handler.post()
            self.assertIn('--advertise-routes=192.0.2.0/24',ts.call_args.args[0])
        self.assertTrue(state.settings()['tailscale']['accept_routes'])

class LocalAPITests(DataTest):
    def test_private_unix_socket_transports_start_and_login_without_argv(self):
        import http.server
        import socketserver
        import tempfile
        import threading
        import socket
        with tempfile.TemporaryDirectory(prefix='ts-qa-',dir='/tmp') as scratch:
            path=scratch+'/daemon.sock';requests=[]
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_POST(self):
                    requests.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                    self.send_response(204 if self.path.endswith('start') else 500);self.end_headers()
                def log_message(self,*args):pass
            daemon=socketserver.UnixStreamServer(path,Handler)
            worker=threading.Thread(target=daemon.serve_forever,daemon=True);worker.start()
            real_socket=socket.socket
            def redirected(*args,**kwargs):
                sock=real_socket(*args,**kwargs)
                class Socket:
                    def connect(self,target):
                        self_outer.assertEqual(target,'/run/tailscale/tailscaled.sock');sock.connect(path)
                    def __getattr__(self,key):return getattr(sock,key)
                return Socket()
            self_outer=self
            try:
                with patch.object(server.socket,'socket',side_effect=redirected), patch.object(server,'command') as command:
                    server.tailscale_local_api('start',{'UpdatePrefs':{'WantRunning':True,'private':'fixture'}})
                    with self.assertRaisesRegex(ValueError,'连接请求失败'):server.tailscale_local_api('login-interactive',{})
                    command.assert_not_called()
                self.assertEqual(requests,[('/localapi/v0/start',{'UpdatePrefs':{'WantRunning':True,'private':'fixture'}}),('/localapi/v0/login-interactive',{})])
            finally:daemon.shutdown();daemon.server_close();worker.join()
