"""Website-confirmed device sign-in and server-owned membership status.

This foundation never gates existing soundboard features. No payments are taken.
"""
import base64
import hashlib
import json
import platform
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from .account_credentials import CredentialStore

WEBSITE = 'https://vupio-soundboard.denserat4.chatgpt.site'


class AccountHTTPError(ValueError):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward device tokens to redirected hosts.


class AccountService:
    def __init__(self, root, executable=None, vault=None, request=None):
        self.vault = vault or CredentialStore(root, executable)
        self.request = request or self._request
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.state = {'state':'signed_out', 'membership':{'plan':'free', 'billing_enabled':False},
                      'website':WEBSITE, 'message':'', 'devices':[]}
        self.epoch = 0
        self.token = None
        self.loaded = False
        self.pro_checked=0.0
        self.pro_token=None

    @staticmethod
    def _request(action, data=None, token=None):
        if action not in {'begin','poll','me','devices','redeem','revoke'}:
            raise ValueError('Unknown account action.')
        headers = {'Accept':'application/json', 'User-Agent':'VUPIO-Account/1'}
        if token: headers['Authorization'] = 'Bearer ' + token
        if data is not None: headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(WEBSITE + '/api/account/' + action,
            data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
                raw = response.read(65537)
                if len(raw) > 65536: raise ValueError('Account service returned an invalid response.')
                result = json.loads(raw)
                if not isinstance(result, dict): raise ValueError('Account service returned an invalid response.')
                return result
        except urllib.error.HTTPError as error:
            messages = {401:'Your account session expired or was disconnected. Sign in again.',
                        400:'This code expired or was used. Try again with a new code.',
                        403:'Account access was refused. Open the VUPIO website and try again.',
                        429:'Too many account requests. Wait a minute and try again.'}
            raise AccountHTTPError(messages.get(error.code, 'The account service is unavailable. Try again later.'), error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError('Cannot reach the account service. Check your connection and try again.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('The account service returned an invalid response. Try again later.') from None

    def info(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def _change(self, **values):
        with self.lock: self.state.update(values)

    def _load_token(self):
        if not self.loaded:
            value = self.vault.read()
            if value and not re.fullmatch('[a-f0-9]{64}', value):
                raise ValueError('Your saved account session is invalid. Sign out and try again.')
            self.token, self.loaded = value, True
        return self.token

    def _update_status(self, token):
        result = self.request('me', token=token)
        devices = self.request('devices', token=token).get('devices', [])
        if not isinstance(result.get('account'), dict) or not isinstance(result.get('membership'), dict):
            raise ValueError('The account service returned an invalid response.')
        # Allow only expected display fields, never relay arbitrary response fields.
        account = {key:result['account'].get(key) for key in ('id','email','display_name')}
        membership = result['membership']
        member = {'plan':'pro' if membership.get('plan') == 'pro' else 'free',
                  'source':membership.get('source'), 'expires_at':membership.get('expires_at'), 'billing_enabled':False, 'features':membership.get('features',[])}
        safe_devices = [{key:d.get(key) for key in ('id','name','platform','created','expires')}
                        for d in devices[:50] if isinstance(d, dict)]
        self.pro_checked=time.monotonic();self.pro_token=token
        self._change(state='signed_in', account=account, membership=member, devices=safe_devices,
                     device_id=result.get('device_id'), message='', user_code=None, verification_uri=None)

    def require_pro(self):
        if not self.operation.acquire(timeout=20):raise ValueError('Account is busy. Wait a moment and try again.')
        try:
            token=self._load_token()
            if not token:raise ValueError('Sign in and activate a Pro invitation in Account to use this feature.')
            if self.pro_token!=token or time.monotonic()-self.pro_checked>60:
                result=self.request('me',token=token)
                member=result.get('membership',{})
                self._change(membership={'plan':member.get('plan','free'),'source':member.get('source'),
                                         'expires_at':member.get('expires_at'),'features':member.get('features',[]),'billing_enabled':False})
                self.pro_checked=time.monotonic();self.pro_token=token
            member=self.info()['membership'];expires=member.get('expires_at')
            if member.get('plan')!='pro' or (expires is not None and expires<=time.time()*1000):
                raise ValueError('This feature needs Pro. Activate a promo or invitation code in Account.')
        finally:self.operation.release()

    def refresh(self):
        return self._background(self._refresh)

    def _refresh(self):
        token = self._load_token()
        if token: self._update_status(token)
        else: self._change(state='signed_out', message='Sign in to connect this computer to your account.')

    def _background(self, action):
        if not self.operation.acquire(blocking=False): return self.info()
        self._change(busy=True, message='')
        def run():
            try: action()
            except Exception as error:
                if isinstance(error, AccountHTTPError) and error.status == 401:
                    self.token = ''
                    try: self.vault.delete()
                    except Exception: pass
                    self._change(state='signed_out', account=None, devices=[], membership={'plan':'free','billing_enabled':False})
                self._change(message=str(error) if isinstance(error, ValueError) else 'Account operation failed. Try again.', error=True)
            finally:
                self._change(busy=False)
                self.operation.release()
        self._change(error=False)
        threading.Thread(target=run, daemon=True, name='vupio-account').start()
        return self.info()

    def begin(self):
        return self._background(self._begin)

    def _begin(self):
        self.epoch += 1
        epoch = self.epoch
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        system = platform.system()
        if system not in {'Darwin','Windows'}: raise ValueError('Open the Mac or Windows app to sign in.')
        grant = self.request('begin', {'challenge':challenge, 'name':platform.node()[:80] or 'VUPIO',
                                       'platform':'macos' if system=='Darwin' else 'windows'})
        uri = grant.get('verification_uri','')
        if not uri.startswith(WEBSITE + '/connect?code=') or urlsplit(uri).netloc != urlsplit(WEBSITE).netloc:
            raise ValueError('The account service returned an invalid sign-in address.')
        if not re.fullmatch('[A-F0-9]{8}', str(grant.get('user_code',''))) or not re.fullmatch('[a-f0-9]{64}',str(grant.get('device_code',''))):
            raise ValueError('The account service returned an invalid sign-in code.')
        self._change(state='pending', user_code=grant['user_code'], verification_uri=uri, message='Confirm this code on the website. Only approve a computer you recognize.')
        until = time.monotonic() + min(600, max(1, int(grant.get('expires_in',600))))
        def poll():
            while time.monotonic() < until and epoch == self.epoch:
                time.sleep(5)
                if epoch != self.epoch: return
                with self.operation:
                    if epoch != self.epoch: return
                    try:
                        result = self.request('poll', {'device_code':grant['device_code'], 'verifier':verifier})
                        if result.get('status') == 'authorization_pending': continue
                        token = result.get('access_token','')
                        if result.get('status') != 'approved' or not re.fullmatch('[a-f0-9]{64}',str(token)):
                            raise ValueError('The account service returned an invalid session.')
                        self.vault.write(token)
                        self.token, self.loaded = token, True
                        try:
                            self._update_status(token)
                        except ValueError as error:
                            self._change(state='offline', user_code=None, verification_uri=None, message=str(error), error=True)
                        return
                    except Exception as error:
                        self._change(message=str(error) if isinstance(error, ValueError) else 'Sign-in failed. Try again.', error=True)
                        if isinstance(error, AccountHTTPError) and error.status in {400,401,409}:
                            self._change(state='signed_out', user_code=None, verification_uri=None)
                            return
            if epoch == self.epoch:
                self._change(state='signed_out', user_code=None, verification_uri=None, message='Sign-in expired. Start again.', error=True)
        threading.Thread(target=poll, daemon=True, name='vupio-sign-in').start()

    def redeem(self, code):
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9 -]{7,63}', str(code).strip()):
            raise ValueError('Enter the promo or invitation code you received.')
        def action():
            token = self._load_token()
            if not token: raise ValueError('Sign in before redeeming a code.')
            self.request('redeem', {'code':str(code).strip()}, token)
            self._update_status(token)
        return self._background(action)

    def revoke(self, device_id):
        if not re.fullmatch('[a-f0-9]{32}',str(device_id)): raise ValueError('Choose a connected device.')
        def action():
            token = self._load_token()
            if not token: raise ValueError('Sign in first.')
            self.request('revoke', {'device_id':device_id}, token)
            if device_id == self.state.get('device_id'):
                self._clear()
            else: self._update_status(token)
        return self._background(action)

    def _clear(self):
        self.vault.delete()
        self.token, self.loaded = '', True
        self._change(state='signed_out', account=None, devices=[], membership={'plan':'free','billing_enabled':False},
                     user_code=None, verification_uri=None, device_id=None)

    def logout(self):
        self.epoch += 1
        def action():
            token = self._load_token()
            failed = False
            try:
                if token: self.request('revoke', {}, token)
            except ValueError: failed = True
            self._clear()
            self._change(message='Signed out locally. The website can disconnect this device if it is still listed.' if failed else 'Signed out.')
        return self._background(action)
