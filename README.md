# ZoneShift

Policy-aware qualification for civil-time scheduler updates. Scheduler code
and time-zone data are evaluated as separate coordinates. A policy-completion
frontier represents unspecified gap/fold behavior; a promotion certificate
reports the minimal passing coordinate changes in an executed upgrade square.

## Install and test

Run from this `artifact/` directory with Python 3.11 or newer:

```sh
python -m pip install -e '.[test]'
python -m pytest -q
python scripts/verify_inputs.py
```

The retained study's test logs are preserved separately from the current suite,
which includes nested semantic-comparator and current-size regressions. Pinned TZif files and licensed scheduler
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

The reference rejects non-finite or out-of-range starting UTC instants. Its
supported UTC range remains 1970--2036, with at most 64 candidate civil dates.
Recurring footer rules include prior-year December spillovers into January 1970;
their initial seasonal state comes from the first applicable UTC transition.
The focused `test_reference_boundary_regressions.py` tests use only mathematical
and in-memory fixtures, without binary TZif files or scheduler execution.

The focused offline regressions need only Python's standard library:

```sh
python -B -m unittest discover -s tests -p test_reproduction_semantics.py -v
```

They check that variable startup durations do not change the semantic digest,
while scheduled timestamps, verdicts, and source/data hashes still do, and that
the current derived size includes the complete core package. They do not rerun
the retained scheduler campaigns or replace their timing measurements.

## Native-policy comparison

Install the optional, fixed comparator with `pip install '.[comparison]'`.
`python scripts/run_native_comparison.py --output results/native-comparison-new`
requalifies the retained 616 frontier,
33,600 benchmark, and 10,400 matrix traces, recomputes the 2,080 certificates, and executes
a separate cronsim 2.6 comparison. It requires the retained results as inputs;
it does not rerun or replace the historical Linux campaign or its timings.
Historical inputs are read from `results/`, independently of the output directory;
`--input-results PATH` selects another retained input set for every comparison
reader. No historical result files are copied into the new directory as new runs.
Choose a directory that does not exist. Omitting `--output` selects
`results/native-comparison-new`; an existing output directory is rejected before
dependency checks or writes. Neither user outputs nor retained records are overwritten.
For a four-trace
native smoke, use `--output results/native-comparison-smoke-new --limit 4`.
This still makes actual optional-comparator calls and is not an offline unit
test. Table generation
uses `python scripts/make_paper_tables.py --paper-dir ../paper`.
`--requalify-only` rechecks retained traces and attribution without new scheduler
calls, writing only recomputed frontier, certificate, and verification files to
a new output directory. It does not copy or update an old native-comparison result.
For example, `python scripts/run_native_comparison.py --output results/requalification-new --requalify-only`
does not require the optional cronsim dependency. The small offline routing tests
in `tests/test_native_output_routing.py` use real bounded qualification fixtures
and stop at the first native-call boundary; they do not run the native campaign.

The comparator records literal cron expressions. Fixed-time cronsim expressions
use immediate gap catch-up (`clamp_forward`) and the first fold branch;
wildcard-hour expressions use skip/both. Expanding `*` into a list can change
native cronsim DST mode even when the sets of hours agree. The bounded model
coalesces several clamped labels to one next-occurrence instant, not job counts.
`policy_scope="open"` preserves `UNDERSPECIFIED` for policy domains outside the
enumerated menu; unsupported option names still fail configuration validation.

`results/native-cronsim-comparison.json` records 1,368 new traces and 10,944 API
calls with no timeout: 96 traces pass native policy but violate skip/both, while
eight Lord Howe hourly-at-30 traces still omit valid occurrences under the
native contract. Both stateful cronsim and reconstruction of Sentry's later
CronSim branch pass the same 80 five-o'clock windows. Sentry migrated in November
2024 (issue 80208); the 24.3.0 croniter replay is historical. The comparison pin
does not assert an exact current Sentry distribution, production outcome, or a
performance advantage. Changes of at least three hours remain outside the
documented small-change native attribution. The historical seven-module totals
and the separate native comparison must not be conflated.

## Render retained signature yields

The code--data workflow is a direct Matplotlib vector with embedded fonts.
`paper/build.py` regenerates it in the full bundle. From this artifact root:

```sh
python plots/draw_workflow.py --output-dir ../paper/figures
```

Install the optional `figures` extra, then run
`python scripts/render_signature_budget.py --source plot_inputs/signature-budget.dat --output-dir figures --font-root /path/to/texmf-dist/fonts`.
This embedded-font vector plot preserves seven budgets and both retained mean
series. Each point is an equal-weight mean over five modules' retained
resampling means, not a defect count or a new sampling experiment. Five input
and routing tests run in the ordinary suite.
