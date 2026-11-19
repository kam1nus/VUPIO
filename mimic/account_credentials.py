"""Device tokens stay in the OS credential store, never in the library or UI."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


class CredentialStore:
    def __init__(self, root, executable=None):
        self.root = Path(root)
        self.executable = executable or os.environ.get('MIMIC_AUDIO_EXECUTABLE')
        self.scope = hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:24]
        self.file = self.root / 'account-session.dpapi'

    def _mac(self, action, token=''):
        if not self.executable:
            raise ValueError('Open the installed VUPIO app to sign in securely.')
        result = subprocess.run([str(self.executable), '--account-helper'],
            input=json.dumps({'action':action, 'scope':self.scope, 'token':token}),
            text=True, capture_output=True, timeout=20)
        try:
            reply = json.loads(result.stdout)
        except ValueError:
            raise ValueError('Could not open the macOS credential store. Try signing in again.') from None
        if result.returncode or reply.get('error'):
            raise ValueError('Could not access the macOS credential store. Allow VUPIO access and try again.')
        return reply.get('token', '')

    @staticmethod
    def _protect(data, decrypt=False):
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_char))]
        buffer = ctypes.create_string_buffer(data)
        source, destination = Blob(len(data), buffer), Blob()
        crypt = ctypes.windll.crypt32
        function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        # CRYPTPROTECT_UI_FORBIDDEN. Current-user DPAPI; no machine-wide flag.
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
            raise ValueError('Could not access the Windows credential store. Sign in again.')
        try:
            return ctypes.string_at(destination.data, destination.size)
        finally:
            ctypes.windll.kernel32.LocalFree(destination.data)

    def read(self):
        if sys.platform == 'darwin': return self._mac('read')
        if sys.platform == 'win32':
            if not self.file.exists(): return ''
            return self._protect(self.file.read_bytes(), decrypt=True).decode('ascii')
        raise ValueError('Secure account storage is available in the Mac and Windows app.')

    def write(self, token):
        if sys.platform == 'darwin': self._mac('write', token); return
        if sys.platform == 'win32':
            temporary = self.file.with_suffix('.tmp')
            try:
                with open(temporary, 'wb') as stream:
                    os.chmod(temporary, 0o600)
                    stream.write(self._protect(token.encode('ascii')))
                os.replace(temporary, self.file)
            finally:
                temporary.unlink(missing_ok=True)
            return
        raise ValueError('Secure account storage is unavailable on this platform.')

    def delete(self):
        if sys.platform == 'darwin': self._mac('delete')
        elif sys.platform == 'win32': self.file.unlink(missing_ok=True)
