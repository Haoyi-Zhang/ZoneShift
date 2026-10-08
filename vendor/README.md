# Dependency-isolated upstream execution

The three `cron/__init__.py` modules and the complete croniter 2.0.1 and 1.3.10 modules are byte-for-byte released upstream source, identified by Git blob hashes in MANIFEST.json. Verify with `python scripts/verify_inputs.py`.

APScheduler parser (`fields.py`, `expressions.py`) and base-trigger modules in **all three** execution directories are shared from tag 3.11.1. This is a controlled calculation-module comparison, not three complete installed distributions. `zoneshift/vendor_support.py` supplies the used upstream datetime arithmetic and restricted adapters for explicit ZoneInfo and aware-datetime inputs. Unsupported constructor coercions are rejected. The ambient tzlocal lookup raises if reached. No cron recurrence algorithm has been replaced. Pickling, job stores, daemon wake-up, executor/concurrency behavior, and arbitrary datetime coercions are outside scope.

The helpers for 3.11.2 preserve its UTC-based `datetime_ceil`/`datetime_utc_add`; 3.11.0 and 3.11.1 preserve their wall-arithmetic ceiling. The shared parsers admit exactly the numeric fields used in the study. The main paper discloses this isolation; it must not be relabelled as a full installed-package or full-project test-suite evaluation.

The Sentry adapter is a minimal local reconstruction of the crontab branch in Sentry 24.3.0 `src/sentry/monitors/schedule.py` (Git blob d7bdb37da6a20fda41b2413db3bd48c40d034bad). The frozen main comparison calls croniter 2.0.1. The separate `sentry-24.3.0` adapter calls the exact 1.3.10 pin in that release's requirements-frozen.txt (Git blob 26ebdd608de45ee99e09be1bae960df6fbb470b6). The complete hosted incident configuration is not established by this release pin. The adapter is not Sentry itself and the local intervention is not an upstream patch.

Included APScheduler/croniter code and adapted helpers retain the corresponding MIT notices. No full third-party research papers or Sentry repository are redistributed.
