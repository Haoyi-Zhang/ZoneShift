# Source and reference audit

## Audit summary

- Audit date: **2026-10-04**.
- Scientific bibliography: **69 entries; 69 unique cited keys; 87 recorded citation contexts**.
- Identifier classes: **0 DOI-backed records and 69 official/versioned URL records**.
- Every entry has author, title, year, identifier, source class, read scope, verification basis, and at least one manuscript citation context in `docs/reference-verification.json`.
- `docs/reference-live-audit.json` is the frozen publisher/official-record metadata check. The offline checker compares BibTeX, citation keys, the verification ledger, and this frozen audit; it does not claim to re-resolve every network identifier on each run.
- IANA 2026a, 2026b, 2026c, 2026d, and 2026e are executable study inputs, not recency-only citations. The release series uses exact tagged Python `tzdata` bytes through 2026e.

## Bibliography inventory

| Key | Year | Source class | Title | Identifier |
|---|---:|---|---|---|
| `apsdoc` | 2025 | `versioned_software_or_documentation` | apscheduler.triggers.cron | https://github.com/agronholm/apscheduler/blob/3.11.1/docs/modules/triggers/cron.rst |
| `issue529` | 2021 | `public_practice_case` | DST transitions cause APScheduler to incorrectly calculate next trigger times | https://github.com/agronholm/apscheduler/issues/529 |
| `issue606` | 2022 | `public_practice_case` | APScheduler With CronTrigger Skipped A Day Due To Daylight Savings | https://github.com/agronholm/apscheduler/issues/606 |
| `issue1021` | 2025 | `public_practice_case` | CronTrigger runs into infinite loop at daylight savings time boundary | https://github.com/agronholm/apscheduler/issues/1021 |
| `sentryissue` | 2024 | `public_practice_case` | Crons: croniter library does not correctly compute DST transition for some schedules | https://github.com/getsentry/sentry/issues/66868 |
| `pep495` | 2015 | `standard_or_rule_data` | Local Time Disambiguation | https://peps.python.org/pep-0495/ |
| `pep615` | 2020 | `standard_or_rule_data` | Support for the IANA Time Zone Database in the Standard Library | https://peps.python.org/pep-0615/ |
| `tza` | 2025 | `standard_or_rule_data` | News for the tz database | https://github.com/eggert/tz/blob/2025a/NEWS |
| `tzlicense` | 2025 | `standard_or_rule_data` | LICENSE | https://github.com/eggert/tz/blob/2025b/LICENSE |
| `apshistory` | 2025 | `versioned_software_or_documentation` | Version history | https://github.com/agronholm/apscheduler/blob/3.11.2/docs/versionhistory.rst |
| `aps0` | 2024 | `versioned_software_or_documentation` | CronTrigger implementation | https://github.com/agronholm/apscheduler/blob/3.11.0/src/apscheduler/triggers/cron/__init__.py |
| `aps1` | 2025 | `versioned_software_or_documentation` | CronTrigger implementation | https://github.com/agronholm/apscheduler/blob/3.11.1/src/apscheduler/triggers/cron/__init__.py |
| `aps2` | 2025 | `versioned_software_or_documentation` | CronTrigger implementation | https://github.com/agronholm/apscheduler/blob/3.11.2/src/apscheduler/triggers/cron/__init__.py |
| `tests0` | 2024 | `versioned_software_or_documentation` | Cron trigger tests | https://github.com/agronholm/apscheduler/blob/3.11.0/tests/triggers/test_cron.py |
| `tests2` | 2025 | `versioned_software_or_documentation` | Cron trigger tests | https://github.com/agronholm/apscheduler/blob/3.11.2/tests/triggers/test_cron.py |
| `cronreadme` | 2023 | `versioned_software_or_documentation` | croniter README | https://github.com/pallets-eco/croniter/blob/2.0.1/README.rst |
| `cron1310` | 2023 | `versioned_software_or_documentation` | croniter implementation | https://github.com/pallets-eco/croniter/blob/1.3.10/src/croniter/croniter.py |
| `cron201` | 2023 | `versioned_software_or_documentation` | croniter implementation | https://github.com/pallets-eco/croniter/blob/2.0.1/src/croniter/croniter.py |
| `sentryschedule` | 2024 | `versioned_software_or_documentation` | Monitor schedule calculation | https://github.com/getsentry/sentry/blob/24.3.0/src/sentry/monitors/schedule.py |
| `sentrypin` | 2024 | `versioned_software_or_documentation` | Frozen requirements | https://github.com/getsentry/sentry/blob/24.3.0/requirements-frozen.txt |
| `hypothesis` | 2019 | `test_generation_research` | Hypothesis: A New Approach to Property-Based Testing | https://doi.org/10.21105/joss.01891 |
| `tang` | 2024 | `bug_report_and_empirical_methodology` | App Review Driven Collaborative Bug Finding | https://doi.org/10.1007/s10664-024-10489-x |
| `genmorph` | 2024 | `differential_or_metamorphic_research` | GenMorph: Automatically Generating Metamorphic Relations via Genetic Programming | https://doi.org/10.1109/TSE.2024.3407840 |
| `mckeeman` | 1998 | `differential_or_metamorphic_research` | Differential Testing for Software | https://bitsavers.org/pdf/dec/dtj/dtj_v10-01_1998.pdf |
| `rfc6557` | 2012 | `standard_or_rule_data` | Procedures for Maintaining the Time Zone Database | https://doi.org/10.17487/RFC6557 |
| `rfc8536` | 2019 | `standard_or_rule_data` | The Time Zone Information Format (TZif) | https://doi.org/10.17487/RFC8536 |
| `rfc9636` | 2024 | `standard_or_rule_data` | The Time Zone Information Format (TZif) | https://doi.org/10.17487/RFC9636 |
| `rfc5545` | 2009 | `standard_or_rule_data` | Internet Calendaring and Scheduling Core Object Specification (iCalendar) | https://doi.org/10.17487/RFC5545 |
| `rfc7808` | 2016 | `standard_or_rule_data` | Time Zone Data Distribution Service | https://doi.org/10.17487/RFC7808 |
| `weyuker1982` | 1982 | `test_oracle_research` | On Testing Non-Testable Programs | https://doi.org/10.1093/comjnl/25.4.465 |
| `barr2015` | 2015 | `test_oracle_research` | The Oracle Problem in Software Testing: A Survey | https://doi.org/10.1109/TSE.2014.2372785 |
| `quickcheck` | 2000 | `test_generation_research` | QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs | https://doi.org/10.1145/351240.351266 |
| `dart` | 2005 | `test_generation_research` | DART: Directed Automated Random Testing | https://doi.org/10.1145/1065010.1065036 |
| `klee` | 2008 | `test_generation_research` | KLEE: Unassisted and Automatic Generation of High-Coverage Tests for Complex Systems Programs | https://www.usenix.org/conference/osdi-08 |
| `randoop` | 2007 | `test_generation_research` | Feedback-Directed Random Test Generation | https://doi.org/10.1109/ICSE.2007.37 |
| `evosuite` | 2011 | `test_generation_research` | EvoSuite: Automatic Test Suite Generation for Object-Oriented Software | https://doi.org/10.1145/2025113.2025179 |
| `csmith` | 2011 | `test_generation_research` | Finding and Understanding Bugs in C Compilers | https://doi.org/10.1145/1993498.1993532 |
| `deltadebug` | 2002 | `testing_evidence_and_benchmarks` | Simplifying and Isolating Failure-Inducing Input | https://doi.org/10.1109/32.988498 |
| `creduce` | 2012 | `testing_evidence_and_benchmarks` | Test-Case Reduction for C Compiler Bugs | https://doi.org/10.1145/2254064.2254104 |
| `mtsurvey` | 2016 | `differential_or_metamorphic_research` | A Survey on Metamorphic Testing | https://doi.org/10.1109/TSE.2016.2532875 |
| `mtreview` | 2018 | `differential_or_metamorphic_research` | Metamorphic Testing: A Review of Challenges and Opportunities | https://doi.org/10.1145/3143561 |
| `mrscout` | 2024 | `differential_or_metamorphic_research` | MR-Scout: Automated Synthesis of Metamorphic Relations from Existing Test Cases | https://doi.org/10.1145/3656340 |
| `safeRTS` | 1997 | `regression_testing_research` | A Safe, Efficient Regression Test Selection Technique | https://doi.org/10.1145/248233.248262 |
| `prioritize2001` | 2001 | `regression_testing_research` | Prioritizing Test Cases for Regression Testing | https://doi.org/10.1109/32.962562 |
| `elbaum2002` | 2002 | `regression_testing_research` | Test Case Prioritization: A Family of Empirical Studies | https://doi.org/10.1109/32.988497 |
| `yoo2012` | 2012 | `regression_testing_research` | Regression Testing Minimization, Selection and Prioritization: A Survey | https://doi.org/10.1002/stv.430 |
| `ekstazi` | 2015 | `regression_testing_research` | Ekstazi: Lightweight Test Selection | https://doi.org/10.1109/ICSE.2015.230 |
| `flaky` | 2014 | `testing_evidence_and_benchmarks` | An Empirical Analysis of Flaky Tests | https://doi.org/10.1145/2635868.2635920 |
| `deflaker` | 2018 | `testing_evidence_and_benchmarks` | DeFlaker: Automatically Detecting Flaky Tests | https://doi.org/10.1145/3180155.3180164 |
| `defects4j` | 2014 | `testing_evidence_and_benchmarks` | Defects4J: A Database of Existing Faults to Enable Controlled Testing Studies for Java Programs | https://doi.org/10.1145/2610384.2628055 |
| `mutantsreal` | 2014 | `testing_evidence_and_benchmarks` | Are Mutants a Valid Substitute for Real Faults in Software Testing? | https://doi.org/10.1145/2635868.2635929 |
| `manybugs` | 2015 | `testing_evidence_and_benchmarks` | The ManyBugs and IntroClass Benchmarks for Automated Repair of C Programs | https://doi.org/10.1109/TSE.2015.2454513 |
| `yin2011` | 2011 | `configuration_and_dependency_evolution` | An Empirical Study on Configuration Errors in Commercial and Open Source Systems | https://doi.org/10.1145/2043556.2043572 |
| `rabkin2011` | 2011 | `configuration_and_dependency_evolution` | Static Extraction of Program Configuration Options | https://doi.org/10.1145/1985793.1985812 |
| `kula2018` | 2018 | `configuration_and_dependency_evolution` | Do Developers Update Their Library Dependencies? An Empirical Study on the Impact of Security Advisories on Library Migration | https://doi.org/10.1007/s10664-017-9521-5 |
| `bettenburg2008` | 2008 | `bug_report_and_empirical_methodology` | What Makes a Good Bug Report? | https://doi.org/10.1145/1453101.1453146 |
| `zimmermann2010` | 2010 | `bug_report_and_empirical_methodology` | What Makes a Good Bug Report? | https://doi.org/10.1109/TSE.2010.63 |
| `herzig2013` | 2013 | `bug_report_and_empirical_methodology` | It's Not a Bug, It's a Feature: How Misclassification Impacts Bug Prediction | https://doi.org/10.1109/ICSE.2013.6606585 |
| `bird2009` | 2009 | `bug_report_and_empirical_methodology` | Fair and Balanced? Bias in Bug-Fix Datasets | https://doi.org/10.1145/1595696.1595716 |
| `collberg2016` | 2016 | `reproducibility_and_empirical_design` | Repeatability in Computer Systems Research | https://doi.org/10.1145/2812803 |
| `wohlin2012` | 2012 | `reproducibility_and_empirical_design` | Experimentation in Software Engineering | https://doi.org/10.1007/978-3-642-29044-2 |
| `nas2019` | 2019 | `reproducibility_and_empirical_design` | Reproducibility and Replicability in Science | https://doi.org/10.17226/25303 |
| `aps3` | 2026 | `versioned_software_or_documentation` | CronTrigger implementation | https://github.com/agronholm/apscheduler/blob/3.11.3/src/apscheduler/triggers/cron/__init__.py |
| `cron624` | 2026 | `versioned_software_or_documentation` | croniter implementation | https://github.com/pallets-eco/croniter/blob/6.2.4/src/croniter/croniter.py |
| `tz2026a` | 2026 | `standard_or_rule_data` | Time Zone Database Release 2026a | https://www.iana.org/time-zones/releases/2026a |
| `tz2026b` | 2026 | `standard_or_rule_data` | Time Zone Database Release 2026b | https://www.iana.org/time-zones/releases/2026b |
| `tz2026e` | 2026 | `standard_or_rule_data` | Time Zone Database Release 2026e | https://www.iana.org/time-zones/releases/2026e |
| `tz2026c` | 2026 | `standard_or_rule_data` | Time Zone Database Release 2026c | https://www.iana.org/time-zones/releases/2026c |
| `tz2026d` | 2026 | `standard_or_rule_data` | Time Zone Database Release 2026d | https://www.iana.org/time-zones/releases/2026d |

## Primary practical-source provenance

- APScheduler 3.11.0/1/2/3 calculation modules, selected tests, documentation, issues, and version history are retained by exact tag/path or recorded upstream identity. The study executes the calculation boundary only, not complete historical distributions or full upstream CI.
- croniter 1.3.10 and 2.0.1 retain released modules and licenses. Sentry 24.3.0 selects 1.3.10. croniter 6.2.4 is tied to its official tagged upstream source identity and is used only in labeled current holdouts.
- The Sentry experiment reconstructs only `src/sentry/monitors/schedule.py`'s crontab calculation branch. Full services, customer data, hosted incidents, persistence, worker execution, and alert delivery are not redistributed or executed.
- The TZif corpus contains **47 files covering 21 selected zones and seven IANA releases**. Exact provenance and SHA-256 hashes are in `data/tzdb/manifest.json`; the upstream notice is retained.
- The consecutive release series executes source-named pairs from IANA 2026a through 2026e. It does not infer outcomes for zones or release changes that were not retained and run.

## Venue-policy checks (not scientific bibliography entries)

- ICSE 2027 SEIP: 10 main-text pages plus no more than 2 reference-only pages; IEEEtran `10pt,conference`; non-anonymous track.
- ICSE 2027 open-science policy: `Data Availability` immediately follows the Conclusion; no uncreated DOI or unuploaded public URL is claimed.
- The manuscript discloses substantive generative-AI assistance and does not claim human-only analysis or independent review.

Official policy pages checked for manuscript compliance:

- https://conf.researchr.org/track/icse-2027/icse-2027-seip
- https://conf.researchr.org/track/icse-2027/icse-2027-icse-2027-open-science-policies

## Interpretation limits

This ledger is a traceability record, not a systematic literature review or a bibliometric completeness claim. Some methodology papers are used through publisher/DOI metadata and their cited conceptual contribution rather than redistributed full text; each row records its read scope. Source availability, citation count, and venue prestige are not empirical evidence for ZoneShift.
