import json
import math
from pathlib import Path
import tempfile
import unittest

from main import forecast, read_history, timestamp, validate_forecast


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

    def test_future_observations_excluded_sorted_and_unsorted(self):
        start = timestamp(self.task['window']['from'])
        future = [(start, {900 + i: i + 1 for i in range(20)}),
                  (start + 12, {1000 + i: i + 1 for i in range(20)})]
        expected = forecast(self.task, self.history)
        for records in (self.history + future, list(reversed(self.history + future))):
            self.assertEqual(forecast(self.task, records), expected)

    def test_earliest_cutoff_and_exclusive_boundary(self):
        start = timestamp(self.task['window']['from'])
        cutoff = start - 12
        task = dict(self.task, history_until='2026-01-01T12:00:00Z')
        expected = forecast(self.task, [(at, ranks) for at, ranks in self.history
                                        if at < cutoff])
        self.assertEqual(forecast(task, list(reversed(self.history))), expected)
        # A history_until later than the window must not admit window data.
        later = dict(self.task, history_until='2026-01-03T00:00:00Z')
        future = (start, {2000 + i: i + 1 for i in range(20)})
        self.assertEqual(forecast(later, self.history + [future]),
                         forecast(self.task, self.history))

    def test_empty_post_cutoff_history_fails_explicitly(self):
        start = timestamp(self.task['window']['from'])
        for records in ([], [(start, self.history[0][1])],
                        [(start + 1, self.history[0][1])]):
            with self.assertRaisesRegex(ValueError, 'before the task cutoff'):
                forecast(self.task, records)

    def test_insufficient_history_fails_explicitly(self):
        with self.assertRaises(ValueError):
            forecast(self.task, [(490896, {1: 1})])

    def test_output_validation_preserves_serialization(self):
        result = forecast(self.task, self.history)
        expected = (json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        self.assertEqual(validate_forecast(result), expected)

    def test_output_validation_rejects_invalid_contracts(self):
        valid = {'probabilities': [], 'top10': list(range(1, 11))}
        row = {'universe_id': 1, 'place': 1, 'p': 0.6}
        invalid = [
            dict(valid, extra=True),
            dict(valid, top10=[1] * 10),
            dict(valid, top10=[True] + list(range(2, 11))),
            dict(valid, top10=[0] + list(range(2, 11))),
            dict(valid, probabilities=[dict(row, p=float('nan'))]),
            dict(valid, probabilities=[dict(row, p=float('inf'))]),
            dict(valid, probabilities=[dict(row, p=-0.1)]),
            dict(valid, probabilities=[dict(row, p=1.1)]),
            dict(valid, probabilities=[dict(row, p=True)]),
            dict(valid, probabilities=[row, row.copy()]),
            dict(valid, probabilities=[row, dict(row, universe_id=2)]),
            dict(valid, probabilities=[dict(row, extra=1)]),
            dict(valid, probabilities=[dict(row, place=11)]),
            dict(valid, probabilities=[dict(row, universe_id=0)]),
            dict(valid, probabilities=[dict(row, universe_id=i, p=0.001)
                                       for i in range(1, 102)]),
            dict(valid, probabilities={}),
        ]
        for result in invalid:
            with self.subTest(result=result):
                with self.assertRaises(ValueError):
                    validate_forecast(result)

    def test_output_validation_checks_encoded_size(self):
        # Legal integer ids can still make the encoded document too large.
        huge_id = 10 ** 2000
        result = {'top10': list(range(1, 11)), 'probabilities': [
            {'universe_id': huge_id + i, 'place': place, 'p': 0.001}
            for place in range(1, 11) for i in range(100)]}
        with self.assertRaisesRegex(ValueError, 'one MiB'):
            validate_forecast(result)


if __name__ == '__main__':
    unittest.main()
