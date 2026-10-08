# ZoneShift

Policy-aware qualification for civil-time scheduler updates. Scheduler code
and time-zone data are evaluated as separate coordinates. A policy-completion
frontier represents unspecified gap/fold behavior; a promotion certificate
reports the minimal passing coordinate changes in an executed upgrade square.

## Install and test

```sh
python -m pip install -e '.[test]'
python -m pytest -q
python scripts/verify_inputs.py
```

The suite contains 127 tests. Pinned TZif files and licensed scheduler
sources are included in `data/` and `vendor/`; the checker does not fall back to
the host's current time-zone database. Windows evaluation uses a bounded worker
process, while POSIX supports the recorded signal-based boundary.

The retained Linux study comprises 53,400 traces and 422,592 next-occurrence
calls. These are recorded measurements, not a fresh run on the CI host. For a
new experiment, choose a new output directory with the documented study runner.
`configs/` defines contracts and bounded horizons, `results/` holds measurements,
and `docs/` describes the supported recurrence fragment. Monthly recurrence,
distributed delivery, and live deployment are not claimed by the core checker.
Original code is MIT-licensed; vendored sources retain their own notices.
