import unittest,socket,tempfile,json
from pathlib import Path
from unittest.mock import patch
from mimic.public_audio import AudioPage,public_target,resolve_public_audio,PublicAudioError,public_dns

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
   with patch('mimic.public_audio.socket.getaddrinfo',return_value=records),patch('mimic.public_audio.public_dns',side_effect=PublicAudioError('private','private_address')):
    with self.assertRaises(ValueError):public_target('https://example.org/a')
 def test_https_and_credentials_and_port(self):
  for url in ['http://example.org/a','file:///tmp/a','https://u:p@example.org/a','https://example.org:8000/a']:
   with self.assertRaises(ValueError):public_target(url)
 def test_public_target_usable_for_ip_pinning(self):
  with patch('mimic.public_audio.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]):
   host,ips,path=public_target('https://example.org/a%20b.mp3?x=1&y=2')
  self.assertEqual((host,ips,path),('example.org',['8.8.8.8'],'/a%20b.mp3?x=1&y=2'))
 def test_vpn_fake_ip_is_replaced_with_verified_public_dns(self):
  records=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('198.18.0.4',443))]
  with patch('mimic.public_audio.socket.getaddrinfo',return_value=records),patch('mimic.public_audio.public_dns',return_value=['93.184.216.34']) as dns:
   self.assertEqual(public_target('https://example.org/audio.mp3?private-token=abc'),('example.org',['93.184.216.34'],'/audio.mp3?private-token=abc'))
  dns.assert_called_once_with('example.org')
 def test_local_urls_never_use_public_dns(self):
  with patch('mimic.public_audio.public_dns') as dns,patch('mimic.public_audio.socket.getaddrinfo') as local:
   for url in ['https://127.0.0.1/x','https://169.254.169.254/latest','https://[::1]/x','https://printer.local/x','https://localhost/x','https://224.0.0.1/x','https://[ff02::1]/x']:
    with self.subTest(url=url),self.assertRaises(ValueError):public_target(url)
  dns.assert_not_called();local.assert_not_called()
 def test_resolver_results_are_rechecked_before_pinning(self):
  with patch('mimic.public_audio.socket.getaddrinfo',side_effect=socket.gaierror(socket.EAI_AGAIN,'temporary DNS failure')),patch('mimic.public_audio.public_dns',return_value=['10.0.0.1']):
   with self.assertRaises(PublicAudioError):public_target('https://example.org/x')
 def test_sinkhole_and_negative_dns_are_not_overridden(self):
  with patch('mimic.public_audio.public_dns') as dns:
   for value in ['0.0.0.0','127.0.0.1','192.168.1.2']:
    with patch('mimic.public_audio.socket.getaddrinfo',return_value=[(2,1,6,'',(value,443))]),self.assertRaises(PublicAudioError):public_target('https://example.org/x')
   with patch('mimic.public_audio.socket.getaddrinfo',side_effect=socket.gaierror(socket.EAI_NONAME,'not found')),self.assertRaises(PublicAudioError):public_target('https://example.org/x')
  dns.assert_not_called()
 def test_public_dns_uses_fixed_tls_resolver_and_bounded_cache(self):
  from unittest.mock import MagicMock
  response=MagicMock(status=200);response.read.return_value=json.dumps({'Status':0,'Answer':[{'type':1,'data':'93.184.216.34','TTL':30}]}).encode()
  connection=MagicMock();connection.getresponse.return_value=response
  with patch.dict('mimic.public_audio._dns_cache',{},clear=True),patch('mimic.public_audio.PinnedHTTPS',return_value=connection) as create:
   self.assertEqual(public_dns('example.org'),['93.184.216.34'])
   self.assertEqual(public_dns('example.org'),['93.184.216.34'])
   create.assert_called_once_with('cloudflare-dns.com','1.1.1.1',timeout=4)
   self.assertEqual(connection.request.call_args.args[1],'/dns-query?name=example.org&type=A')
  connection.close.assert_called_once();response.close.assert_called_once()
 def test_public_dns_private_answers_and_redirects_fail_closed(self):
  from unittest.mock import MagicMock
  for status,body in [(200,{'Status':0,'Answer':[{'type':1,'data':'192.168.1.1','TTL':30}]}),(302,{})]:
   response=MagicMock(status=status);response.read.return_value=json.dumps(body).encode()
   connection=MagicMock();connection.getresponse.return_value=response
   with patch.dict('mimic.public_audio._dns_cache',{},clear=True),patch('mimic.public_audio.PinnedHTTPS',return_value=connection):
    with self.assertRaises(PublicAudioError):public_dns('example.org')
 def test_catalog_redirect_to_unlisted_host_is_not_requested(self):
  from mimic.net import catalog_download
  from unittest.mock import MagicMock
  connection=MagicMock();response=connection.getresponse.return_value;response.status=302;response.getheader.return_value='https://other-public.org/audio.mp3'
  with tempfile.TemporaryDirectory() as d,patch('mimic.public_audio.public_target',return_value=('archive.org',['8.8.8.8'],'/audio')) as target,patch('mimic.public_audio.PinnedHTTPS',return_value=connection) as create:
   with self.assertRaises(ValueError):catalog_download('https://archive.org/audio',Path(d)/'file')
  self.assertEqual(create.call_count,1);self.assertEqual(target.call_count,1)
 def test_network_failure_code_survives_background_queue(self):
  import time
  from mimic.library import Library
  from mimic.jobs import Jobs
  with tempfile.TemporaryDirectory() as root:
   jobs=Jobs(Library(root))
   try:
    def fail(job):raise PublicAudioError('VPN DNS unavailable','network_dns')
    id=jobs.submit('radar_clip',fail)['job_id']
    deadline=time.monotonic()+3
    while jobs.get(id)['status'] not in ['failed','done'] and time.monotonic()<deadline:time.sleep(.01)
    result=jobs.get(id)
    self.assertEqual(result['status'],'failed');self.assertEqual(result['result']['error_code'],'network_dns')
   finally:jobs.close()
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
