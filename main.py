"""Deterministic, dependency-free rank-distribution forecast."""
import json
import math
import os
from datetime import datetime
from pathlib import Path


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() / 3600


def read_history(path):
    snapshots = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get('ok') is False:
            continue
        ranks = {}
        for row in item.get('up_and_coming') or []:
            if not isinstance(row, dict):
                continue
            uid, rank = row.get('universe_id'), row.get('rank')
            if type(uid) is int and type(rank) is int and uid > 0 and rank > 0:
                ranks.setdefault(uid, rank)
        if ranks:
            snapshots.append((timestamp(item['at']), ranks))
    snapshots.sort(key=lambda s: s[0])
    if not snapshots:
        raise ValueError('history contains no valid ranked observations')
    return snapshots


def forecast(task, snapshots):
    start = timestamp(task['window']['from'])
    horizon = timestamp(task['window']['until']) - start
    if horizon <= 0:
        raise ValueError('forecast window must have positive duration')
    latest_time, latest = snapshots[-1]
    ids = sorted({uid for _, ranks in snapshots for uid in ranks})
    if len(ids) < 10:
        raise ValueError('need at least ten observed universe ids')
    # Time quadrature prevents denser recording from multiplying its influence.
    weights = []
    for i, (at, _) in enumerate(snapshots):
        previous = snapshots[i - 1][0] if i else at - 6
        following = snapshots[i + 1][0] if i + 1 < len(snapshots) else start
        duration = max(0.1, min(12, (following - previous) / 2))
        weights.append(duration * math.exp(-max(0, start - at) / 30))
    total_weight = sum(weights)
    scores = {uid: [0.0] * 10 for uid in ids}
    for uid in ids:
        observations = [(at, ranks[uid]) for at, ranks in snapshots if uid in ranks]
        last_at, last_rank = observations[-1]
        recent = [(at, rank) for at, rank in observations if at >= last_at - 24]
        old_at, old_rank = recent[0]
        slope = (last_rank - old_rank) / max(8, last_at - old_at)
        slope = max(-0.4, min(0.4, slope))
        survival = math.exp(-max(0, start - last_at) / 36)
        for place in range(1, 11):
            frequency = sum(w for w, (_, ranks) in zip(weights, snapshots)
                            if ranks.get(uid) == place) / total_weight
            kernel = 0.0
            for step in range(12):
                ahead = max(0, start - last_at) + horizon * (step + 0.5) / 12
                center = max(1, last_rank + slope * 18 * (1 - math.exp(-ahead / 18)))
                width = 1.5 + 0.075 * ahead + 0.10 * min(last_rank, 30)
                # Discrete normalization accounts for the rank-one boundary.
                normalizer = sum(math.exp(-0.5 * ((rank - center) / width) ** 2)
                                 for rank in range(1, max(120, int(center + 8 * width)) + 1))
                kernel += math.exp(-0.5 * ((place - center) / width) ** 2) / normalizer / 12
            broad = sum(w * math.exp(-abs(ranks.get(uid, 200) - place) / 12)
                        for w, (_, ranks) in zip(weights, snapshots)) / total_weight / 24
            scores[uid][place - 1] = 0.25 * frequency + 0.60 * survival * kernel + 0.15 * broad
    # Name fewer than the whole current chart, retaining a useful newcomer share.
    candidates = sorted(ids, key=lambda uid: (-sum(scores[uid]), uid))[:60]
    rows = []
    for place in range(1, 11):
        denominator = sum(scores[uid][place - 1] for uid in candidates)
        for uid in sorted(candidates):
            probability = 0.78 * scores[uid][place - 1] / denominator
            rows.append({'universe_id': uid, 'place': place, 'p': round(probability, 12)})
    remaining = set(candidates)
    top10 = []
    for place in range(10):
        uid = min(remaining, key=lambda u: (-scores[u][place], u))
        top10.append(uid)
        remaining.remove(uid)
    return {'probabilities': rows, 'top10': top10}


def main():
    input_dir = Path(os.environ.get('MAKEFUN_INPUT_DIR', '/input'))
    output_dir = Path(os.environ.get('MAKEFUN_OUTPUT_DIR', '/output'))
    task = json.loads((input_dir / 'task.json').read_text())
    result = forecast(task, read_history(input_dir / 'history.ndjson'))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'forecast.json').write_text(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
