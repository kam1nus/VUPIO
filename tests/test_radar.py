import json
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mimic.autofetch import pcm_hash
from mimic.library import Library
from mimic.studio import Studio
from mimic.web_agent import web_row
from mimic.radar import InstantLinks, Radar, aggregate, apple_tracks, apply_model_order, relevance_order, social_candidates


class RadarTest(unittest.TestCase):
    def test_instants_uses_chart_links_in_order_and_deduplicates_locale(self):
        parser = InstantLinks()
        parser.feed("""
            <a href="/instant/other/">Outside chart</a>
            <a class="instant-link" href="//example.com/instant/wrong/">Wrong host</a>
            <a href="/en/instant/first/" class="instant-link link-secondary">First &amp; <b>loud</b></a>
            <a class="instant-link" href="/ru/instant/first/">Repeat</a>
            <a class="instant-link" href="/en/instant/second/">Second</a>
        """)
        self.assertEqual([r['title'] for r in parser.rows.values()], ['First & loud', 'Second'])

    def test_apple_tracks_keeps_only_the_selected_storefront(self):
        def track(id, region):
            return {'id': id, 'url': f'https://music.apple.com/{region}/album/track', 'name': id}
        data = {'feed': {'results': [track('1', 'gb'), track('2', 'us'), track('3', 'us'), track('2', 'us')]}}
        self.assertEqual([r['key'] for r in apple_tracks(data, 'us')], ['2', '3'])

    def test_aggregate_uses_each_daily_rank_and_discloses_older_only_entries(self):
        a, b, c = ({'key': key} for key in ('a', 'b', 'c'))
        rows = aggregate([[b, a], [a, c, b], [a]])
        self.assertEqual([(r['key'], r['days'], r['source_rank']) for r in rows],
                         [('a', 3, 2), ('b', 2, 1), ('c', 1, None)])

    def test_social_requires_real_video_paths_and_canonicalizes_duplicates(self):
        urls = ['https://www.youtube.com/shorts/abcdefghijk?feature=share',
                'https://youtube.com/shorts/abcdefghijk', 'https://www.youtube.com/watch?v=abcdefghijk',
                'https://www.youtube.com.evil.test/shorts/abcdefghijk',
                'https://user@www.youtube.com/shorts/abcdefghijk']
        rows = [{'title': 'A sound', 'page_url': url} for url in urls]
        self.assertEqual([r['url'] for r in social_candidates(rows, 'shorts')],
                         ['https://www.youtube.com/shorts/abcdefghijk'])
        self.assertEqual(apply_model_order(['a', 'b', 'c'], {'order': [2, 2, True, 99]}), ['c'])
        self.assertEqual(apply_model_order(['a'], {'order': []}), [])
        self.assertEqual(apply_model_order(['a'], {'order': [5]}), ['a'])

    def test_relevance_promotes_named_audio_over_generic_posts(self):
        rows = [
            {'title': 'How to download audio', 'excerpt': 'Tutorial', 'web_score': 1},
            {'title': 'Band — Song', 'excerpt': 'Remix', 'web_score': .4},
        ]
        models = Mock()
        models.embed.return_value = [[1, 0], [0, 1], [1, 0]]
        self.assertEqual(relevance_order(rows, 'tracks', models), rows[::-1])
        models.embed.side_effect = ValueError('no local model')
        self.assertEqual(relevance_order(rows, 'tracks', models), rows[::-1])

    def test_refresh_reuses_cache_when_chart_provider_fails(self):
        with tempfile.TemporaryDirectory() as root:
            web = Mock()
            studio = SimpleNamespace(library=Library(root), finder=SimpleNamespace(web=web))
            radar = Radar(studio)
            body = {'region': 'us', 'category': 'tracks'}
            feed = json.dumps({'feed': {'results': [
                {'id': '1', 'name': 'Test song', 'url': 'https://music.apple.com/us/album/track'},
            ]}}).encode()
            with patch('mimic.radar.read_feed', side_effect=[feed, OSError('offline'), OSError('offline')]) as read:
                first = radar.refresh(body, Mock())
                self.assertEqual(first['days'], 1)
                self.assertEqual(radar.refresh(body, Mock()), first)
                stale = radar.refresh({**body, 'force': True}, Mock())
                self.assertTrue(stale['stale'])
                self.assertIn('Apple Music', stale['warning'])
                self.assertEqual(stale['rows'], first['rows'])
                self.assertEqual(read.call_count, 3)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg not installed')
    def test_radar_prepares_once_and_commits_the_same_audio(self):
        with tempfile.TemporaryDirectory() as root:
            library = Library(root)
            studio = Studio(library, '/unused')
            try:
                row = web_row('https://www.myinstants.com/en/instant/fixture/', 'Radar fixture', 'Myinstants')
                source = dict(row, download_url='https://www.myinstants.com/media/sounds/fixture.wav')
                studio.finder.web.save_results([row])
                job = Mock()

                def download(url, path, job, maximum):
                    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                    'sine=frequency=430:duration=0.25', '-f', 'wav', str(path)], check=True)

                with patch.object(studio.finder, 'resolve', return_value=source), \
                     patch('mimic.public_audio.download_public', side_effect=download) as network, \
                     patch.object(studio, 'classify', side_effect=AssertionError('Radar should skip AI')):
                    prepared = studio.radar.prepare_clip(row['source_id'], job)
                    self.assertEqual(library.items(), [])
                    self.assertEqual(studio.radar.prepare_clip(row['source_id'], job), prepared)
                    self.assertEqual(network.call_count, 1)

                id = prepared['asset_id']
                _, preview = studio.asset(id)
                self.assertEqual(preview, studio.original(id))
                self.assertEqual(prepared['plan']['end'], .25)
                added = studio.autofetch.commit(id, job)['item']
                self.assertEqual(pcm_hash(preview), pcm_hash(library.path(added['id'])))
                duplicate = studio.autofetch.commit(id, job)
                self.assertTrue(duplicate['duplicate'])
                self.assertEqual(studio.radar.prepare_clip(row['source_id'], job)['item']['id'], added['id'])
                self.assertEqual(len(library.items()), 1)
                library.delete(added['id'])
                self.assertEqual(studio.radar.prepare_clip(row['source_id'], job), prepared)
            finally:
                studio.close()

    def test_radar_rejects_a_player_page_before_preloading(self):
        with tempfile.TemporaryDirectory() as root:
            studio = Studio(Library(root), '/unused')
            try:
                row = web_row('https://www.youtube.com/shorts/abcdefghijk', 'Video', 'Shorts')
                studio.finder.web.save_results([row])
                with self.assertRaisesRegex(ValueError, 'отдельный аудиофайл'):
                    studio.radar.prepare_clip(row['source_id'], Mock())
            finally:
                studio.close()
