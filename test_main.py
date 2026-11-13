import json
import math
from pathlib import Path
import tempfile
import unittest

from main import forecast, read_history


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.task = {'window': {'from': '2026-01-02T00:00:00Z',
                                'until': '2026-01-05T00:00:00Z'}}
        self.history = [(490896.0 + j * 6, {100 + i: 1 + (i + j) % 20
                                          for i in range(20)}) for j in range(4)]

    def test_normalization_and_determinism(self):
        result = forecast(self.task, self.history)
        self.assertEqual(result, forecast(self.task, self.history))
        self.assertEqual(set(result), {'probabilities', 'top10'})
        self.assertEqual(len(set(result['top10'])), 10)
        self.assertTrue(set(result['top10']) <= set(self.history[0][1]))
        keys = set()
        for row in result['probabilities']:
            self.assertEqual(set(row), {'universe_id', 'place', 'p'})
            self.assertTrue(math.isfinite(row['p']) and 0 <= row['p'] <= 1)
            key = row['universe_id'], row['place']
            self.assertNotIn(key, keys)
            keys.add(key)
        for place in range(1, 11):
            rows = [r for r in result['probabilities'] if r['place'] == place]
            self.assertLessEqual(len(rows), 100)
            self.assertAlmostEqual(sum(r['p'] for r in rows), 0.78, places=9)

    def test_null_and_malformed_optional_fields(self):
        record = {'at': '2026-01-01T00:00:00Z', 'ok': True,
                  'details': None, 'top_trending': 'malformed',
                  'top_playing_now': {'unexpected': []},
                  'up_and_coming': [None, {}, {'universe_id': True, 'rank': 1},
                                     {'universe_id': 1, 'rank': None},
                                     {'universe_id': 42, 'rank': 2, 'playing': None}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.ndjson'
            path.write_text(json.dumps(record) + '\n')
            parsed = read_history(path)
            self.assertEqual(parsed[0][1], {42: 2})
            record['details'] = {'42': {'created': [], 'playing': 'bad'}}
            path.write_text(json.dumps(record) + '\n')
            self.assertEqual(read_history(path), parsed)

    def test_rank_changes_affect_forecast(self):
        before = forecast(self.task, self.history)
        changed = [(t, {uid: 21 - rank for uid, rank in ranks.items()})
                   for t, ranks in self.history]
        self.assertNotEqual(before, forecast(self.task, changed))

    def test_insufficient_history_fails_explicitly(self):
        with self.assertRaises(ValueError):
            forecast(self.task, [(490896, {1: 1})])


if __name__ == '__main__':
    unittest.main()
