import io
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from mimic.account import AccountService, AccountHTTPError, NoRedirect, WEBSITE
from mimic.account_credentials import CredentialStore


class Vault:
    def __init__(self, token=''): self.token = token
    def read(self): return self.token
    def write(self, token): self.token = token
    def delete(self): self.token = ''


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.vault = Vault('a'*64)
        self.calls = []
        def request(action, data=None, token=None):
            self.calls.append((action, data, token))
            if action == 'me': return {'account':{'id':'alice','email':'alice@example.test'},'membership':{'plan':'pro','source':'tester','expires_at':9999999999999},'device_id':'b'*32,'access_token':'DO NOT EXPOSE'}
            if action == 'devices': return {'devices':[{'id':'b'*32,'name':'Mac','platform':'macos','token':'DO NOT EXPOSE'}]}
            if action == 'begin': return {'verification_uri':WEBSITE+'/connect?code=1234ABCD','user_code':'1234ABCD','device_code':'c'*64,'expires_in':600}
            return {}
        self.service = AccountService('/tmp/vupio-account-test', vault=self.vault, request=request)

    def wait(self):
        for _ in range(200):
            info = self.service.info()
            if not info.get('busy'): return info
            time.sleep(.01)
        self.fail('Account operation did not complete')

    def test_status_uses_server_and_never_exposes_tokens(self):
        self.service.refresh()
        info = self.wait()
        self.assertEqual(info['state'], 'signed_in')
        self.assertEqual(info['membership']['plan'], 'pro')
        self.assertNotIn('DO NOT EXPOSE', json.dumps(info))
        self.assertNotIn('a'*64, json.dumps(info))
        self.assertFalse(info['membership']['billing_enabled'])

    def test_expired_session_is_removed_and_local_features_remain_independent(self):
        def expired(*args, **kwargs): raise AccountHTTPError('Session expired.', 401)
        self.service.request = expired
        self.service.refresh()
        info = self.wait()
        self.assertEqual(info['state'],'signed_out')
        self.assertEqual(self.vault.token,'')
        self.assertEqual(info['membership']['plan'],'free')

    def test_offline_logout_clears_local_session(self):
        def offline(*args, **kwargs): raise ValueError('Offline')
        self.service.request = offline
        self.service.logout()
        info = self.wait()
        self.assertEqual(self.vault.token,'')
        self.assertEqual(info['state'],'signed_out')
        self.assertIn('locally',info['message'])

    def test_revoking_this_device_signs_out(self):
        self.service.refresh(); self.wait()
        self.service.revoke('b'*32)
        self.assertEqual(self.wait()['state'],'signed_out')
        self.assertEqual(self.vault.token,'')

    def test_browser_url_cannot_be_replaced_by_server(self):
        self.service.request=lambda *a,**k: {'verification_uri':'https://evil.example/connect?code=1234ABCD'}
        with patch('mimic.account.platform.system',return_value='Darwin'):
            self.service.begin(); info=self.wait()
        self.assertTrue(info['error'])
        self.assertNotIn('verification_uri',info)

    def test_account_http_never_redirects_token(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',None,'https://evil.example/'))

    def test_secure_mac_helper_passes_secret_on_stdin(self):
        with tempfile.TemporaryDirectory() as folder:
            store=CredentialStore(folder,'/Applications/VUPIO.app/Contents/MacOS/MIMIC')
            with patch('mimic.account_credentials.sys.platform','darwin'),patch('mimic.account_credentials.subprocess.run') as run:
                run.return_value.returncode=0; run.return_value.stdout='{}'
                store.write('a'*64)
                self.assertNotIn('a'*64,str(run.call_args.args))
                self.assertIn('a'*64,run.call_args.kwargs['input'])

    @unittest.skipUnless(__import__('sys').platform=='win32','Windows current-user DPAPI')
    def test_real_dpapi_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            store=CredentialStore(folder)
            store.write('a'*64)
            self.assertNotIn(b'a'*64,store.file.read_bytes())
            self.assertEqual(store.read(),'a'*64)
            store.delete(); self.assertEqual(store.read(),'')

    def test_pro_access_checks_server_caches_briefly_and_expires(self):
        self.service.require_pro();self.assertEqual(self.calls[0][0],'me')
        count=len(self.calls);self.service.require_pro();self.assertEqual(len(self.calls),count)
        self.service.pro_checked=0
        self.service.request=lambda *a,**k:{'membership':{'plan':'free'}}
        with self.assertRaises(ValueError):self.service.require_pro()
        self.service.pro_checked=0
        self.service.request=lambda *a,**k:{'membership':{'plan':'pro','expires_at':1}}
        with self.assertRaises(ValueError):self.service.require_pro()
        self.service.pro_checked=0
        self.service.request=lambda *a,**k:{'membership':{'plan':'pro','expires_at':None}}
        self.service.require_pro()
        self.service.logout();self.wait()
        with self.assertRaises(ValueError):self.service.require_pro()

    def test_pro_cannot_be_unlocked_when_server_rejects_session(self):
        self.service.request=lambda *a,**k:(_ for _ in ()).throw(AccountHTTPError('Expired',401))
        with self.assertRaises(AccountHTTPError):self.service.require_pro()
