import unittest,socket,tempfile,json
from pathlib import Path
from unittest.mock import patch
from mimic.public_audio import AudioPage,public_target,resolve_public_audio

class PublicAudioTests(unittest.TestCase):
 def test_primary_audio_not_related_sounds(self):
  p=AudioPage();p.feed('<meta property="og:audio" content="/media/main.mp3"><a href="/related.mp3">other</a>')
  self.assertEqual(p.candidate('https://example.org/page'),'https://example.org/media/main.mp3')
 def test_audio_source_relative(self):
  p=AudioPage();p.feed('<audio><source src="./sound.ogg" type="audio/ogg"></audio>')
  self.assertEqual(p.candidate('https://example.org/x/page'),'https://example.org/x/sound.ogg')
 def test_scripts_never_executed_or_selected(self):
  p=AudioPage();p.feed('<script>fetch("https://evil.org/a.mp3")</script>')
  with self.assertRaises(ValueError):p.candidate('https://example.org/')
 def test_ambiguous_list_rejected(self):
  p=AudioPage();p.feed('<a href="a.mp3">a</a><a href="b.mp3">b</a>')
  with self.assertRaisesRegex(ValueError,'multiple audio files'):p.candidate('https://example.org/')
 def test_private_or_mixed_dns_rejected(self):
  for addresses in [['127.0.0.1'],['169.254.169.254'],['::1'],['8.8.8.8','10.0.0.1']]:
   records=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in addresses]
   with patch('mimic.public_audio.socket.getaddrinfo',return_value=records):
    with self.assertRaises(ValueError):public_target('https://example.org/a')
 def test_https_and_credentials_and_port(self):
  for url in ['http://example.org/a','file:///tmp/a','https://u:p@example.org/a','https://example.org:8000/a']:
   with self.assertRaises(ValueError):public_target(url)
 def test_public_target_usable_for_ip_pinning(self):
  with patch('mimic.public_audio.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]):
   host,ips,path=public_target('https://example.org/a%20b.mp3?x=1&y=2')
  self.assertEqual((host,ips,path),('example.org',['8.8.8.8'],'/a%20b.mp3?x=1&y=2'))
 def test_unknown_license_does_not_block_public_audio(self):
  from email.message import Message
  class Response:
   def __init__(self):self.headers=Message();self.headers['Content-Type']='text/html';self.url='https://example.org/page'
   def read(self,n):return b'<meta property="og:audio" content="https://example.org/sound.mp3">'
   def __enter__(self):return self
   def __exit__(self,*a):pass
  source={'source_id':'tavily:x','page_url':'https://example.org/page','license':''}
  with patch('mimic.public_audio.open_public',return_value=Response()),patch('mimic.public_audio.public_target'):
   r=resolve_public_audio(source)
  self.assertTrue(r['can_import']);self.assertFalse(r['rights_checked']);self.assertEqual(r['download_url'],'https://example.org/sound.mp3')
 def test_connection_uses_pinned_ip_and_original_tls_host(self):
  from mimic.public_audio import PinnedHTTPS
  connection=PinnedHTTPS('example.org','8.8.8.8')
  with patch('mimic.public_audio.socket.create_connection') as create,patch.object(connection._context,'wrap_socket') as wrap:
   connection.connect()
  self.assertEqual(create.call_args.args[0],('8.8.8.8',443));self.assertEqual(wrap.call_args.kwargs['server_hostname'],'example.org')
 def test_redirect_to_local_network_is_rejected_before_connect(self):
  from mimic.public_audio import open_public
  from unittest.mock import MagicMock
  connection=MagicMock();response=connection.getresponse.return_value;response.status=302;response.getheader.return_value='https://127.0.0.1/private'
  def target(url):
   if '127.0.0.1' in url:raise ValueError('\u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0439 \u0441\u0435\u0442\u0438')
   return 'example.org',['8.8.8.8'],'/'
  with patch('mimic.public_audio.public_target',side_effect=target),patch('mimic.public_audio.PinnedHTTPS',return_value=connection) as create:
   with self.assertRaises(ValueError):open_public('https://example.org/')
  self.assertEqual(create.call_count,1);response.close.assert_called_once();connection.close.assert_called_once()
 def test_large_download_is_removed(self):
  from mimic.public_audio import download_public
  from unittest.mock import MagicMock
  response=MagicMock();response.__enter__.return_value=response;response.headers.get.return_value='101'
  with tempfile.TemporaryDirectory() as d,patch('mimic.public_audio.open_public',return_value=response):
   path=Path(d)/'partial'
   with self.assertRaises(ValueError):download_public('https://example.org/a.mp3',path,maximum=100)
   self.assertFalse(path.exists())
 def test_cancelled_download_is_removed(self):
  from mimic.public_audio import download_public
  from unittest.mock import MagicMock
  response=MagicMock();response.__enter__.return_value=response;response.headers.get.return_value='0'
  job=MagicMock();job.check.side_effect=RuntimeError('cancel')
  with tempfile.TemporaryDirectory() as d,patch('mimic.public_audio.open_public',return_value=response):
   path=Path(d)/'partial'
   with self.assertRaises(RuntimeError):download_public('https://example.org/a.mp3',path,job)
   self.assertFalse(path.exists())
