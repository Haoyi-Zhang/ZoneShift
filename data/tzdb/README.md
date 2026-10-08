# Retained TZif data

This directory contains byte-pinned TZif files used by the executable study. `manifest.json` is the authoritative path/SHA-256/provenance list; `NOTICE.txt` retains the upstream data notice.

The corpus contains **47 zone files**:

- historical snapshots used by the main benchmark and factorial study: IANA 2024a and 2025b;
- the earlier current-data holdout: tagged Python `tzdata` 2025.2 / 2026.1 / 2026.2 inputs corresponding to IANA 2025b / 2026a / 2026b;
- the consecutive release series: exact files from tagged Python `tzdata` 2026.1 through 2026.5, corresponding to IANA 2026a through 2026e.

The source-named release pairs are:

| Old → new | Retained zone | Source change under study |
|---|---|---|
| 2025b → 2026a | `Europe/Chisinau` | Moldova transition-history/rule correction |
| 2026a → 2026b | `America/Vancouver` | British Columbia permanent UTC-07 |
| 2026b → 2026c | `America/Edmonton` | Alberta permanent UTC-06 |
| 2026b → 2026c | `Africa/Casablanca` | Morocco permanent UTC+00 |
| 2026c → 2026d | `America/Inuvik` | Northwest Territories permanent UTC-06 |
| 2026d → 2026e | `America/Winnipeg` | Manitoba permanent UTC-05 |

Each tagged distribution directory has a `VERSION.json` recording the Python package tag, IANA release label, and source commit. These files are scientific inputs, not claims that every zone or every rule change in a release was evaluated. `scripts/verify_inputs.py` checks all retained hashes before execution.
