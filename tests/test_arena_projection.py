from datetime import date
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from arena_source import URL, fetch_dataset
from arena_projection import from_snapshot, from_view
from input_snapshot import canonical
from shadow_store import PostgresInputView


def snapshot():
    rows = [{'model_name': 'model-' + str(i), 'organization': 'Arena fixture', 'license': 'fixture',
             'category': 'overall', 'rating': 1500 - i + .1234, 'rating_lower': 1499 - i,
             'rating_upper': 1501 - i, 'rank': i + 1, 'vote_count': 100,
             'leaderboard_publish_date': '2026-10-28'} for i in range(12)]
    text = fetch_dataset(URL, load=lambda: (rows, 'a' * 40, 'b' * 64), today=date(2026, 10, 31))
    return '<!-- fetched: 1793429378.067596 -->\n\n' + text


class ArenaProjectionTests(unittest.TestCase):
    def test_publication_date_coverage_score_and_attribution(self):
        board = from_snapshot(snapshot())
        self.assertEqual(board['snapshot_date'], '2026-10-28')
        self.assertTrue(board['collected_at'].startswith('2026-10-31'))
        self.assertFalse(board['manual']); self.assertEqual(board['row_count'], 12)
        self.assertEqual(len(board['top']), 10); self.assertEqual(board['top'][0]['model'], 'model-0')
        self.assertEqual(board['top'][0]['elo'], 1500.1)
        self.assertEqual(board['top'][0]['rating'], 1500.1234)
        self.assertEqual(board['source_url'], URL); self.assertIn('CC BY 4.0', board['citation'])
        self.assertIn('12 records', board['note_en'])
        actual = from_snapshot(snapshot().replace('1793429378.067596', '2026-10-31T14:49:38.067596+08:00'))
        self.assertEqual(actual['collected_at'], board['collected_at'])
        with self.assertRaises(ValueError):
            from_snapshot(snapshot().replace('1793429378.067596', '2026-10-31T14:49:38'))

    def test_legacy_kept_but_invalid_official_snapshot_blocks_publication(self):
        self.assertIsNone(from_snapshot('Historical manual website leaderboard'))
        self.assertIsNone(from_view(SimpleNamespace()))
        with self.assertRaises(ValueError):
            from_snapshot(snapshot().replace('"rating": 1500.1234', '"rating": null'))
        with self.assertRaises(ValueError):
            from_snapshot(snapshot().replace('<!-- fetched: 1793429378.067596 -->', ''))
        view = SimpleNamespace(iter_raw_snapshots=lambda pattern: iter([('new', snapshot()), ('old', 'legacy')]))
        self.assertEqual(from_view(view)['snapshot_date'], '2026-10-28')

    def test_raw_reader_uses_pinned_inventory_and_verified_blob_only(self):
        raw = snapshot().encode(); sha = hashlib.sha256(raw).hexdigest()
        name = 'data/snapshots/2026-10-31/LMArena__industry__2026-10-31.md'
        body = {'schemaVersion': 1, 'scope': 'raw-snapshots-local-drill', 'sourceCommit': 'a' * 40,
                'inputVersion': 'in_' + 'c' * 64, 'files': {name: {
                    'blobId': 'blob_' + sha, 'rawSha256': sha, 'bytes': len(raw)}}, 'snapshots': {}}
        manifest = {**body, 'migrationVersion': 'sm_' + hashlib.sha256(canonical(body).encode()).hexdigest()}
        view = PostgresInputView.__new__(PostgresInputView)
        view.version = body['inputVersion']; view.connection = MagicMock(); view.store = MagicMock()
        cursor = view.connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (manifest,); view.store.get.return_value = raw
        self.assertEqual(list(view.iter_raw_snapshots('data/snapshots/*/LMArena__industry__*.md')), [(name, raw.decode())])
        self.assertEqual(cursor.execute.call_args.args[1], [view.version])
        view.store.get.assert_called_once_with(sha, expected_bytes=len(raw))
        with self.assertRaises(ValueError): list(view.iter_raw_snapshots('data/snapshots/*/LMArena__industry__*.md', max_bytes=1))
        manifest['files'][name]['bytes'] += 1
        with self.assertRaises(ValueError): list(view.iter_raw_snapshots('data/snapshots/*/LMArena__industry__*.md'))

    def test_server_projection_overrides_manual_board_only(self):
        import page_projection
        name = 'data/derived/leaderboards/lmarena.json'
        view = SimpleNamespace(files={name: {}}, read_json=lambda n: {'manual': True},
                               iter_raw_snapshots=lambda pattern: iter([('committed', snapshot())]), iter_json=lambda *a: iter([]))
        with patch.object(page_projection, 'compose_daily', return_value={}), patch.object(page_projection, 'compose_weekly', return_value=[]):
            values = dict(page_projection.projections(Path('/unused'), view))
        self.assertFalse(values[name]['manual']); self.assertEqual(values[name]['row_count'], 12)


if __name__ == '__main__': unittest.main()
