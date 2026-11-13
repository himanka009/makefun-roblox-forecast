# Roblox Up-and-Coming forecaster

Original deterministic Python 3.13 implementation for Make.fun
`roblox-up-and-coming-forecast-01`. Standard library only; no runtime network,
randomness, credentials, or third-party dependencies.

Run `python3.13 main.py`. Input defaults to `/input` and output to
`/output/forecast.json`; override with `MAKEFUN_INPUT_DIR` and
`MAKEFUN_OUTPUT_DIR`. The input contains `task.json` and `history.ndjson`.
The forecast window is read from the task, never hardcoded. Observations
at or after the earlier of `history_until` and the window start are excluded;
retained observations are sorted, and an empty retained history fails explicitly.

The model mixes exponentially decayed observed rank frequencies (25%),
positive-rank-normalized Gaussian kernels around damped recent rank trends
(60%), and a broader historical rank kernel (15%). Time quadrature weights
irregular reads, limiting the effect of changing recorder cadence. Twelve
midpoints integrate uncertainty over the requested horizon. Each candidate's
time-kernel normalization is computed once per midpoint and reused across places. Absent games
lose influence with time. Optional player counts, details and other charts
are deliberately unused, so missing or malformed optional values cannot
change the forecast. Invalid rank rows are ignored; missing required files,
invalid JSON or fewer than ten observed IDs fail explicitly.

The 60 strongest observed candidates receive 78% of each place's probability;
22% remains unnamed for newcomers and other omitted games. The top10 greedily
selects distinct candidates by place score. Numeric ID tie breaks and fixed
serialization make repeated runs byte-identical. This is a conservative
heuristic, not a trained or calibrated claim of forecasting accuracy.
Before writing, production validation checks the exact schema, positive integer
IDs, distinct top10 and row pairs, finite probabilities, per-place row and mass
limits, and the one MiB limit on the actual encoded UTF-8 output.

Run tests with `python3.13 -m unittest -v`. Practice validation checks output
shape, finite probabilities, limits, observed IDs and byte determinism.
The official `grade-local --driver process` was attempted and refused because
this competition's scorer/reference are server-only; local checks provide
no official score. Docker daemon access was denied. Validation artifacts
are outside the repository under `/tmp/roblox-validation`.
