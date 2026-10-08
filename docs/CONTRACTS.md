# Contract and integration details

## Declared recurrence contract

A wall-clock contract contains sorted, distinct `hours`, `minutes`, and Monday-zero `weekdays`; seconds are fixed to zero. Gap policy is `skip`, `shift_forward`, `shift_backward`, or `unspecified`. Fold policy is `first`, `second`, `both`, or `unspecified`. The executable configuration also fixes the zone identity, exact TZif snapshot, local starting label and fold, implementation identifier, requested prefix length, timeout, and reference horizon. A nonexistent starting label is rejected. Elapsed recurrence is a separate helper and is never treated as an alias for local daily recurrence.

For a declared contract and bounded observed sequence, the checker evaluates:

- strict progress in physical time;
- membership in the requested civil recurrence;
- presence of required unique occurrences;
- exclusion of forbidden fold branches;
- required fold cardinality when specified; and
- explicit gap behavior when the tested implementation normalizes a missing label.

`PASS` applies only to the observed finite prefix. `VIOLATION` identifies a contradicted declared requirement. `UNDERSPECIFIED` preserves a materially missing gap/fold decision. An exception, timeout, unsupported reference capability, or unknown intent is never converted into a maintainer-confirmed bug.

## Independent limited enumerator

The reference path parses retained TZif transition arrays and fixed and common recurring POSIX TZ footers, enumerates candidate civil labels in the supported recurrence subset, and resolves each label against applicable offsets. Zero resolutions form a gap, one an ordinary occurrence, and two a fold. Policy chooses permitted/required branches. The enumerator does not import or call APScheduler or croniter.

The real adapters and a separately implemented intervention use Python `ZoneInfo`, while the reference path uses the local TZif parser. Both consume the same retained rule bytes. The retained all-input validator records 14,780 comparisons over 1,345 transition records across 47 TZif files: 200 sampled instants per file plus four checks per transition. The separate consecutive-release validator records 777 comparisons over 259 records. Their recorded zero mismatches test independent conversion algorithms over shared rule truth; they do not establish independent legal authority over time-zone rules or validate arbitrary recurrence syntax.

## Main and two-axis matrices

The main benchmark uses complete application profiles with `gap=skip` and `fold=both`, so every trace receives a decisive bounded verdict. A separate policy-frontier study deliberately removes one policy coordinate at a time, enumerates all admissible completions, and reports either the exact passing completions or a robust violation that fails every completion. Both studies require unique valid matching labels and strict UTC progress. The historical benchmark executes APScheduler 3.11.0/1/2 and croniter 1.3.10/2.0.1 with pinned 2024a data.

The two-axis matrix evaluates coordinates `(C,D)`, where `C` is scheduler-code version and `D` is TZif snapshot. For fixed code, a data update is classified as:

1. identical bytes and identical behavior;
2. changed bytes with no observed behavior change;
3. accepted data effect: output changes, both sides pass, and retained release evidence explains the affected zone/interval; or
4. changed output containing a violation or unresolved policy.

For fixed data, code-version effects are analyzed separately. A code-data interaction is recorded when the existence or qualification of a code-version difference changes with `D`. The update gate never approves a change merely because tzdb bytes differ or because a release note describes an intended rule change.

## Real application integration point

Sentry 24.3.0's monitored-cron path initializes croniter from the reference timestamp, obtains the next datetime, and clears seconds/microseconds. `sentry_next()` reconstructs only that branch. `sentry-24.3.0` selects the released croniter 1.3.10 pin; `sentry-adapter` selects the later 2.0.1 comparison without pretending it was Sentry's frozen dependency. Stateful croniter iteration is a distinct adapter and is not silently conflated with reconstruction on every call.

`wall_next(previous, contract)` is the bounded local intervention. It supports only the declared expression subset, round-trips both fold candidates through pinned `ZoneInfo`, implements skip, forward-projection, and backward-projection gap policies, and returns the next policy-permitted instant. It does not call the independent oracle. A production integration would still require a syntax-domain gate, persistence/concurrency tests, alerting tests, rollout controls, and accountable maintainer review; none is claimed here.

## Time-separated qualification sets

The historical main and factorial matrices remain frozen. Later sets are labeled separately:

- **Current-module holdout:** APScheduler 3.11.2/3.11.3 and croniter 2.0.1/6.2.4, 2025b data, 12 non-discovery zones, years 2022--2025, four profiles. It measures release preservation/repair without rewriting the historical Sentry pin.
- **Initial current-rule-data holdout:** APScheduler 3.11.3 and croniter 6.2.4, 2025b/2026b data, America/Vancouver and Europe/Chisinau selected from IANA 2026a/2026b notes before outcome inspection, years 2022/2026/2027, four profiles.
- **Consecutive rule-release series:** the same current modules with exact tagged Python `tzdata` bytes for every source-named pair from IANA 2026a through 2026e. The six retained zones are Chisinau, Vancouver, Edmonton, Casablanca, Inuvik, and Winnipeg. A difference is accepted only when both endpoint traces pass and the retained source covers the affected zone/period.

`results/decision-records.jsonl` stores 5,280 historical/current-holdout records. `results/release-series-decisions.jsonl` adds 1,752 paired old-data/new-data records with both TZif hashes and traces. `results/minimized-witnesses.json` retains 43 executed prefixes that preserve and exactly replay representative blocked and accepted decisions. Prefix reduction packages reviewable evidence; it does not minimize semantic inputs, isolate root causes, or provide independent confirmation.

## De-correlated failure signatures

Generated windows can share a mechanism. For a violating observation, `behaviour_signature()` retains exactly `profile`, sorted `reasons`, and the first mismatch's `mismatch`, `value`, and zero-based `ordinal`. The mismatch is an error category, a signed UTC timestamp delta, a missing required occurrence within the emitted coverage, or a verdict-only reason. Zone, year, absolute UTC time, case identity, and sampler metadata (anchor class, anchor offset, and transition shape) are excluded. Analysis pools are grouped separately by implementation, strategy, and seed; implementation identity is not a signature field. Seven budgets are evaluated with 200 deterministic resamples per strategy and module. At budget 16, the retained detection rates span 60--100% for boundary selection and 5--22% for uniform selection. Signature yield is a stricter diversity measure than raw trace count, but signatures can still share a root cause and must not be reported as independent defects.

## Recorded costs and current artifact size

`results/released-sentry.json` retains 80 before/after windows with eight occurrences on each side. Its local Linux timing medians are 643.7135 microseconds before and 293.1995 microseconds after, per eight-occurrence trace, not per individual next-occurrence call. The before timer includes adapter setup and iteration; the after timer covers the eight-step intervention loop. These timings describe different implementations and work boundaries and are not a general performance claim. The five boundary rows in `results/benchmark-summary.json` retain median bounded-trace times of 302.979--345.311 microseconds. No original duration records are replaced by these summaries.

The current size metric counts all ten Python files directly in `zoneshift/`, including `vendor_support.py`, and excludes study scripts, tests, and retained vendor source. It counts nonblank lines that do not begin with `#` after leading whitespace; docstring lines remain counted under this convention. The derived `integration-metrics.json` and the `integration` branch of `extended-analysis.json` report 1,092 lines, 23 top-level protocol fields, and 47 pinned TZif files. This current-tree size is not a new scheduler experiment or an estimate of engineer effort.

Semantic reproduction comparison excludes `startup_ns` alongside the existing duration fields at every nested level. It does not modify the source records and retains runner identity, scheduled instants, verdicts, trace order, and source/data hashes in the comparison.
