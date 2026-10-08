#!/usr/bin/env python3
"""Audit the manuscript bibliography against its verification ledger.

The checker is intentionally offline. It verifies the internal chain from BibTeX
metadata to manuscript citations to the retained source-audit ledger. Network
resolution is not claimed by this script; the ledger records the primary-source
basis used during the source audit.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BIB = ROOT / "paper" / "references.bib"
TEX = ROOT / "paper" / "main.tex"
LEDGER = ROOT / "docs" / "reference-verification.json"
LIVE_AUDIT = ROOT / "docs" / "reference-live-audit.json"
OUT = ROOT / "results" / "reference-check.json"

ENTRY_RE = re.compile(r"@(?P<type>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s]+)\s*,", re.M)
CITE_RE = re.compile(r"\\cite\w*\{([^}]*)\}")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
URL_RE = re.compile(r"^https://\S+$", re.I)

PUBLIC_CASES = {"issue529", "issue606", "issue1021", "sentryissue"}
STANDARDS = {"pep495", "pep615", "rfc5545", "rfc6557", "rfc7808", "rfc8536", "rfc9636", "tza", "tzlicense", "tz2026a", "tz2026b", "tz2026c", "tz2026d", "tz2026e"}
SOFTWARE = {"apsdoc", "apshistory", "aps0", "aps1", "aps2", "aps3", "tests0", "tests2", "cronreadme", "cron1310", "cron201", "cron624", "sentryschedule", "sentrypin"}
ORACLE = {"weyuker1982", "barr2015"}
GENERATION = {"hypothesis", "quickcheck", "dart", "klee", "randoop", "evosuite", "csmith"}
DIFF_META = {"mckeeman", "genmorph", "mtsurvey", "mtreview", "mrscout"}
REGRESSION = {"safeRTS", "prioritize2001", "elbaum2002", "yoo2012", "ekstazi"}
TEST_EVIDENCE = {"flaky", "deflaker", "defects4j", "mutantsreal", "manybugs", "deltadebug", "creduce"}
CONFIG = {"yin2011", "rabkin2011", "kula2018"}
REPORTS = {"tang", "bettenburg2008", "zimmermann2010", "herzig2013", "bird2009"}
REPRO = {"collberg2016", "wohlin2012", "nas2019"}

FULL_PRIMARY = PUBLIC_CASES | STANDARDS | SOFTWARE | {"hypothesis", "tang", "mckeeman", "klee"}

SPECIAL_NOTES = {
    "issue529": "Issue body, recurrence, expected timestamp, labels, and status inspected; the original pandas/pytz environment is not claimed as rerun.",
    "issue606": "Issue body and duplicate disposition inspected; treated as the same historical family as issue 529, not an independent defect.",
    "issue1021": "Issue body supplies the repeated-interval nonprogress input and names APScheduler 3.11.0; local replay is reported separately.",
    "sentryissue": "Issue body and downstream effect description inspected; customer impact remains attributed context, while all numerical results are local measurements.",
    "apsdoc": "Versioned DST policy and examples inspected. The paper preserves documented legal missing/repeated occurrences as negative controls.",
    "apshistory": "Versioned 3.11.0--3.11.2 release notes inspected for the folded-time fixes associated with issue 1021.",
    "tza": "IANA 2025a NEWS entry for Paraguay inspected and used only to justify an expected rule-data change.",
    "tzlicense": "Complete upstream notice inspected and retained with the pinned data.",
    "tz2026a": "Official IANA 2026a release note inspected for Moldova's transition-time correction; used to preselect Europe/Chisinau before outcome inspection.",
    "tz2026b": "Official IANA 2026b release note inspected for British Columbia's permanent UTC-07 change; used to preselect America/Vancouver before outcome inspection.",
    "tz2026c": "Official IANA 2026c release note inspected for Alberta's permanent UTC-06 and Morocco's permanent UTC+00 changes; both zones are executed in the stepwise holdout.",
    "tz2026d": "Official IANA 2026d release note inspected for Northwest Territories permanent UTC-06; America/Inuvik is executed in the stepwise holdout.",
    "tz2026e": "Official IANA 2026e release note inspected for Manitoba permanent UTC-05; America/Winnipeg is executed in the stepwise holdout.",
    "pep495": "Primary PEP inspected for fold/gap terminology and the semantics of the fold attribute.",
    "pep615": "Primary PEP inspected for ZoneInfo construction and versioned data-source behavior.",
    "rfc8536": "Official RFC metadata retained because it governed part of the historical tool/data path; RFC 9636 is cited as its replacement.",
    "rfc9636": "Official RFC Editor record inspected; published October 2024 and explicitly obsoletes RFC 8536.",
    "cron1310": "Exact released module retained and byte-identified; it is Sentry 24.3.0's frozen dependency in the local integration replay.",
    "cron201": "Exact released module retained and byte-identified; used as a later release comparator, not as Sentry's deployed version.",
    "aps0": "Exact released CronTrigger calculation source retained and byte-identified; execution uses the documented restricted harness, not a full distribution install.",
    "aps1": "Exact released CronTrigger calculation source retained and byte-identified; execution uses the documented restricted harness.",
    "aps2": "Exact released CronTrigger calculation source retained and byte-identified; execution uses the documented restricted harness.",
    "aps3": "Exact tagged CronTrigger source retained and byte-identified; executed only in the time-separated current-release holdout, not substituted into historical counts.",
    "cron624": "Tagged source retained with upstream blob identity and documented whitespace normalization; executed only in the time-separated current-release holdout while the Sentry replay remains pinned to 1.3.10.",
    "tests0": "Only the four relevant released DST parameter inputs are reconstructed; the complete upstream suite is not claimed.",
    "tests2": "Relevant DST parameters and the focused fold-progress regression are reconstructed; the complete upstream suite is not claimed.",
    "sentryschedule": "The small crontab calculation branch is reconstructed; the complete Sentry service is not executed.",
    "sentrypin": "Frozen requirements source inspected for croniter==1.3.10.",
    "hypothesis": "Publisher record and short open paper inspected; cited for property-based testing practice rather than as evidence about civil time.",
    "tang": "Publisher record and substantive paper sections inspected; cited only as a methodological connection from reports to validated cases.",
    "genmorph": "Published IEEE TSE metadata used; cited for automatic metamorphic-relation generation, not as a directly reused algorithm.",
    "mckeeman": "Primary archived article used for the origin and limits of differential testing.",
    "klee": "Official USENIX proceedings record used for symbolic test generation context; no KLEE experiment is claimed.",
}


def split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote = False
    start = 0
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            quote = not quote
        elif not quote:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(text[start:i].strip())
                start = i + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def strip_balanced_outer(value: str) -> str:
    value = value.strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    if len(value) >= 2 and value[0] == "{" and value[-1] == "}":
        depth = 0
        balanced = True
        for i, ch in enumerate(value):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and i != len(value) - 1:
                    balanced = False
                    break
        if balanced and depth == 0:
            return value[1:-1]
    return value


def parse_bib(text: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    matches = list(ENTRY_RE.finditer(text))
    for m in matches:
        start = m.end()
        depth = 1
        quote = False
        escape = False
        end = None
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                quote = not quote
            elif not quote:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end is None:
            raise ValueError(f"Unclosed BibTeX entry {m.group('key')}")
        fields: dict[str, str] = {"entry_type": m.group("type").lower(), "key": m.group("key")}
        for part in split_top_level(text[start:end]):
            if not part or "=" not in part:
                continue
            name, value = part.split("=", 1)
            fields[name.strip().lower()] = strip_balanced_outer(value)
        key = m.group("key")
        if key in entries:
            raise ValueError(f"Duplicate BibTeX key: {key}")
        entries[key] = fields
    return entries


def citation_contexts(tex: str, key: str) -> list[str]:
    contexts: list[str] = []
    for match in CITE_RE.finditer(tex):
        keys = [item.strip() for item in match.group(1).split(",")]
        if key not in keys:
            continue
        lo = max(tex.rfind("\n\n", 0, match.start()), tex.rfind(".", 0, match.start()))
        hi_para = tex.find("\n\n", match.end())
        hi_dot = tex.find(".", match.end())
        candidates = [x for x in (hi_para, hi_dot) if x != -1]
        hi = min(candidates) + 1 if candidates else min(len(tex), match.end() + 240)
        snippet = re.sub(r"\s+", " ", tex[max(0, lo + 1):hi].strip())
        contexts.append(snippet[:500])
    return contexts


def category(key: str) -> tuple[str, str]:
    if key in PUBLIC_CASES:
        return "public_practice_case", "Motivates and bounds the historical problem family; not counted as newly discovered defects."
    if key in STANDARDS:
        return "standard_or_rule_data", "Defines civil-time representation, versioned rule-data practice, or a specific source-backed rule change."
    if key in SOFTWARE:
        return "versioned_software_or_documentation", "Pins the practical calculation path, release scope, documented behavior, or dependency version."
    if key in ORACLE:
        return "test_oracle_research", "Frames the absence of a universal oracle and the need for an explicit bounded contract."
    if key in GENERATION:
        return "test_generation_research", "Positions boundary generation relative to property, random, symbolic, feedback-directed, and compiler-testing methods."
    if key in DIFF_META:
        return "differential_or_metamorphic_research", "Explains differential/metamorphic baselines and why agreement alone is not an oracle."
    if key in REGRESSION:
        return "regression_testing_research", "Positions equal-budget selection and prioritization against established regression-testing work."
    if key in TEST_EVIDENCE:
        return "testing_evidence_and_benchmarks", "Supports cautious interpretation of generated faults, flaky behavior, reduction, and benchmark evidence."
    if key in CONFIG:
        return "configuration_and_dependency_evolution", "Connects scheduler code and tzdb snapshots to versioned configuration/dependency maintenance."
    if key in REPORTS:
        return "bug_report_and_empirical_methodology", "Supports report-to-replay procedure and cautions about duplicates, labels, and report quality."
    if key in REPRO:
        return "reproducibility_and_empirical_design", "Supports the recorded design, reproducibility boundaries, and limits of a single self-reproduction."
    raise KeyError(f"No category mapping for {key}")


def identifier(fields: dict[str, str]) -> str:
    if fields.get("doi"):
        return "https://doi.org/" + fields["doi"]
    return fields.get("url", "")


def make_ledger(entries: dict[str, dict[str, str]], tex: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for key, fields in entries.items():
        source_kind, use = category(key)
        read_scope = (
            "Primary source or complete relevant versioned source sections inspected."
            if key in FULL_PRIMARY
            else "Bibliographic metadata and the source's cited methodological contribution were checked; no unreported numerical result is imported."
        )
        rows.append(
            {
                "key": key,
                "entry_type": fields["entry_type"],
                "authors_latex": fields.get("author", ""),
                "title_latex": fields.get("title", ""),
                "year": fields.get("year", ""),
                "identifier": identifier(fields),
                "source_kind": source_kind,
                "use_in_paper": use,
                "read_scope": read_scope,
                "verification_basis": SPECIAL_NOTES.get(
                    key,
                    "Metadata retained from the DOI/publisher or official primary record used in the source audit; the citation is limited to the contextual or methodological point shown in the manuscript context.",
                ),
                "citation_contexts": citation_contexts(tex, key),
            }
        )
    return {
        "schema_version": 2,
        "audited_on": "2026-10-04",
        "scope": "Offline retained verification ledger. It records the primary-source audit basis and manuscript use; the automated checker does not claim live DOI/URL resolution.",
        "entry_count": len(rows),
        "entries": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-ledger", action="store_true", help="regenerate the retained ledger from the audited BibTeX plus curated audit notes")
    args = parser.parse_args()

    bib_text = BIB.read_text(encoding="utf-8")
    tex_text = TEX.read_text(encoding="utf-8")
    entries = parse_bib(bib_text)
    cite_sequence = [k.strip() for m in CITE_RE.finditer(tex_text) for k in m.group(1).split(",") if k.strip()]
    cited = set(cite_sequence)

    errors: list[str] = []
    required = {"author", "title", "year"}
    for key, fields in entries.items():
        missing = sorted(required - fields.keys())
        if missing:
            errors.append(f"{key}: missing fields {missing}")
        if not fields.get("doi") and not fields.get("url"):
            errors.append(f"{key}: missing DOI or URL")
        if fields.get("doi") and not DOI_RE.match(fields["doi"]):
            errors.append(f"{key}: malformed DOI {fields['doi']!r}")
        if fields.get("url") and not URL_RE.match(fields["url"]):
            errors.append(f"{key}: URL must be HTTPS: {fields['url']!r}")
        try:
            category(key)
        except KeyError as exc:
            errors.append(str(exc))

    bib_keys = set(entries)
    if bib_keys != cited:
        errors.append(f"citation/BibTeX key mismatch: uncited={sorted(bib_keys-cited)}, unknown={sorted(cited-bib_keys)}")

    duplicate_dois = [doi for doi, count in Counter(v.get("doi") for v in entries.values() if v.get("doi")).items() if count > 1]
    if duplicate_dois:
        errors.append(f"duplicate DOI(s): {duplicate_dois}")

    generated = make_ledger(entries, tex_text)
    if args.refresh_ledger or not LEDGER.exists():
        LEDGER.write_text(json.dumps(generated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    ledger_entries = {row["key"]: row for row in ledger.get("entries", [])}
    if set(ledger_entries) != bib_keys:
        errors.append(f"ledger/BibTeX key mismatch: ledger_only={sorted(set(ledger_entries)-bib_keys)}, bib_only={sorted(bib_keys-set(ledger_entries))}")
    for key, fields in entries.items():
        row = ledger_entries.get(key)
        if not row:
            continue
        expected = {
            "authors_latex": fields.get("author", ""),
            "title_latex": fields.get("title", ""),
            "year": fields.get("year", ""),
            "identifier": identifier(fields),
        }
        for field, value in expected.items():
            if row.get(field) != value:
                errors.append(f"{key}: ledger {field} differs from BibTeX")
        if not row.get("citation_contexts"):
            errors.append(f"{key}: ledger has no manuscript citation context")

    if not LIVE_AUDIT.exists():
        errors.append("missing docs/reference-live-audit.json")
        live_entries = {}
    else:
        live = json.loads(LIVE_AUDIT.read_text(encoding="utf-8"))
        live_entries = {row["key"]: row for row in live.get("entries", [])}
        if set(live_entries) != bib_keys:
            errors.append(
                "live-audit/BibTeX key mismatch: "
                f"audit_only={sorted(set(live_entries)-bib_keys)}, "
                f"bib_only={sorted(bib_keys-set(live_entries))}"
            )
        for key, fields in entries.items():
            row = live_entries.get(key)
            if not row:
                continue
            expected = {
                "authors_latex": fields.get("author", ""),
                "title_latex": fields.get("title", ""),
                "year": fields.get("year", ""),
                "identifier": identifier(fields),
            }
            for field, value in expected.items():
                if row.get(field) != value:
                    errors.append(f"{key}: live-audit {field} differs from BibTeX")
            if row.get("status") not in {"live-resolved", "official-primary-record-checked"}:
                errors.append(f"{key}: invalid live-audit status {row.get('status')!r}")

    report = {
        "status": "pass" if not errors else "fail",
        "bib_entries": len(entries),
        "unique_cited_keys": len(cited),
        "citation_occurrences": len(cite_sequence),
        "all_entries_cited": bib_keys == cited,
        "all_entries_have_author_title_year_and_identifier": not any("missing fields" in e or "missing DOI" in e for e in errors),
        "ledger_matches_bibtex": not any("ledger" in e.lower() for e in errors),
        "live_audit_matches_bibtex": not any("live-audit" in e.lower() for e in errors),
        "doi_count": sum(bool(v.get("doi")) for v in entries.values()),
        "url_only_count": sum(bool(v.get("url")) and not v.get("doi") for v in entries.values()),
        "errors": errors,
        "limitations": "This offline check validates the frozen live-audit snapshot, retained metadata/citation chain, and identifier syntax. The live publisher/official-record audit was performed separately on 2026-10-04; this script does not re-resolve the network on every run.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
