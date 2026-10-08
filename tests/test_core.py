from pathlib import Path
from datetime import datetime,timedelta,timezone
import json,pytest
from zoneshift.contracts import (
    Contract,
    elapsed_reference,
    policy_completion_frontier,
    qualify,
    reference,
    required,
)
from zoneshift.attribution import classify_upgrade_square, minimal_sufficient_changes
from zoneshift.profiles import PROFILES
from zoneshift.tzif import TZif,wall_seconds
from zoneshift.execution import load_zone,run_trace
from zoneshift.repair import wall_next
from zoneshift.adapters import aps_class
ROOT=Path(__file__).resolve().parents[1]
def ref(name,v='2024a'): return TZif(ROOT/'data/tzdb'/v/name)
def trace(times):return [{'timestamp':x} for x in times]

@pytest.mark.parametrize('version',['2024a','2025b'])
@pytest.mark.parametrize('name,label,multiplicity',[
 ('America/New_York','2024-03-10T02:30:00',0),
 ('America/New_York','2024-11-03T01:30:00',2),
 ('America/New_York','2024-03-10T05:00:00',1),
 ('Australia/Lord_Howe','2024-10-06T02:15:00',0),
 ('Australia/Lord_Howe','2024-04-07T01:45:00',2),
 ('Pacific/Apia','2011-12-30T05:00:00',0),
 ('Asia/Kathmandu','2024-02-29T05:00:00',1),
 ('Etc/UTC','2024-01-01T00:00:00',1)])
def test_resolution(version,name,label,multiplicity):
    z=ref(name,version);d=datetime.fromisoformat(label);times=z.resolve(d)
    assert len(times)==multiplicity
    assert all(z.wall(t)==d for t in times)

@pytest.mark.parametrize('policy',['both','first','second'])
@pytest.mark.parametrize('name,start,hour,minute',[
 ('America/New_York','2024-11-02T01:30',1,30),
 ('Australia/Lord_Howe','2024-04-06T01:45',1,45),
 ('Pacific/Apia','2011-12-29T05:00',5,0),
 ('America/New_York','2024-03-09T02:30',2,30)])
def test_repaired_explicit_policies(policy,name,start,hour,minute):
    z=load_zone('2024a',name);o=ref(name)
    d=datetime.fromisoformat(start).replace(tzinfo=z);begin=d.timestamp()
    c=Contract((hour,),(minute,),gap='skip',fold=policy);xs=[]
    for _ in range(8):d=wall_next(d,c);xs.append({'timestamp':d.timestamp()})
    assert qualify(o,c,begin,xs)['status']=='PASS'
    events,_=reference(o,c,begin,8)
    assert [x['timestamp'] for x in xs]==required(events,c)[:8]

@pytest.mark.parametrize('name',['America/New_York','Australia/Lord_Howe','Pacific/Apia','Asia/Kathmandu'])
@pytest.mark.parametrize('version',['2024a','2025b'])
def test_minute_scan_reference(name,version):
    o=ref(name,version);z=load_zone(version,name)
    t=next((tr.utc for tr in o.transitions if datetime(2024,1,1,tzinfo=timezone.utc).timestamp()<tr.utc<datetime(2025,1,1,tzinfo=timezone.utc).timestamp()),1705305600)
    begin=t-18*3600;end=t+18*3600
    c=Contract(tuple(range(24)),(0,30),gap='skip',fold='both')
    events,_=reference(o,c,begin,80)
    enumerated=[e['timestamp'] for e in events if e['timestamp']<=end]
    scanned=[s for s in range(begin+60,end+1,60) if c.matches(datetime.fromtimestamp(s,z).replace(tzinfo=None))]
    assert enumerated==scanned

@pytest.mark.parametrize('mutation',['drop','repeat','off','reverse','empty'])
def test_checker_detects_mutations(mutation):
    o=ref('Etc/UTC');c=Contract((5,),(0,),gap='skip',fold='both');start=1700000000
    ev,_=reference(o,c,start);ts=required(ev,c)[:8]
    if mutation=='drop':ts.pop(2)
    elif mutation=='repeat':ts.insert(2,ts[1])
    elif mutation=='off':ts[2]+=60
    elif mutation=='reverse':ts[2],ts[3]=ts[3],ts[2]
    else:ts=[]
    assert qualify(o,c,start,trace(ts))['status']=='VIOLATION'

def test_fold_underspecified_not_false_bug():
    o=ref('America/New_York');z=load_zone('2024a','America/New_York');s=datetime(2024,11,2,1,30,tzinfo=z).timestamp()
    c=Contract((1,),(30,));events,_=reference(o,c,s)
    xs=[x['timestamp'] for x in events if x['branch']==0][:8]
    assert qualify(o,c,s,trace(xs))['status']=='UNDERSPECIFIED'
    both=Contract((1,),(30,),fold='both')
    assert qualify(o,both,s,trace(xs))['status']=='VIOLATION'

def test_gap_underspecified_not_false_bug():
    z=load_zone('2024a','America/New_York');c=Contract((2,),(30,));s=datetime(2024,3,9,2,30,tzinfo=z).timestamp()
    r=run_trace('aps-3.11.2',z,c,s)
    assert qualify(ref('America/New_York'),c,s,r['trace'],r['error'])['status']=='UNDERSPECIFIED'

def test_same_wall_label_different_instants():
    z=load_zone('2024a','America/New_York');a=datetime(2024,11,3,1,30,tzinfo=z);b=a.replace(fold=1)
    assert a==b # Python wall equality must not be the assertion used for progress.
    assert b.timestamp()-a.timestamp()==3600

def test_elapsed_not_wall():
    z=load_zone('2024a','America/New_York');start=datetime(2024,3,9,5,tzinfo=z).timestamp()
    assert datetime.fromtimestamp(elapsed_reference(start,86400,1)[0],z).hour==6
    assert wall_next(datetime.fromtimestamp(start,z),Contract((5,),(0,),gap='skip',fold='both')).hour==5

@pytest.mark.parametrize('version,passes',[('3.11.0',False),('3.11.1',True),('3.11.2',True),('3.11.3',True)])
def test_historical_fold(version,passes):
    z=load_zone('2024a','Europe/Helsinki');d=datetime(2017,10,29,3,45,tzinfo=z,fold=1)
    t=aps_class(version)(minute=30,timezone=z);n=t.get_next_fire_time(d,d)
    assert (n.timestamp()>d.timestamp())==passes

@pytest.mark.parametrize('version',['3.11.0','3.11.1','3.11.2','3.11.3'])
def test_original_529_weekdays(version):
    z=load_zone('2024a','America/Chicago');d=datetime(2021,3,12,0,0,0,1,tzinfo=z)
    t=aps_class(version).from_crontab('0 0 * * 0-4',timezone=z)
    n=t.get_next_fire_time(None,d)
    assert str(n)=='2021-03-16 00:00:00-05:00' # Characterization: historical bug persists.

def test_rule_update_not_global_whitelist():
    rows=json.loads((ROOT/'results/tzdb-update.json').read_text())
    assert sum(x['verdict']=='EXPECTED_CHANGE' for x in rows)==26
    assert sum(x['verdict']=='VIOLATION' for x in rows)==4
    assert sum(x['verdict']=='UNCHANGED' for x in rows)==10

@pytest.mark.parametrize('kw',[{'hours':()}, {'hours':(24,)},{'minutes':(60,)},{'hours':(2,1)}, {'fold':'guess'},{'gap':'guess'},{'recurrence':'elapsed'},{'weekdays':(7,)}])
def test_reject_unsupported_contract(kw):
    args=dict(hours=(5,),minutes=(0,));args.update(kw)
    with pytest.raises(ValueError):Contract(**args)

def test_reject_range_and_ambient():
    with pytest.raises(ValueError):ref('Etc/UTC').offset_at(-1)
    with pytest.raises(ValueError):ref('Etc/UTC').offset_at(2208988800)
    with pytest.raises(ValueError):wall_seconds(datetime(2024,1,1,tzinfo=timezone.utc))
    with pytest.raises(RuntimeError):aps_class('3.11.2')()
    with pytest.raises(ValueError):wall_next(datetime(2024,1,1),Contract((5,),(0,),gap='skip',fold='both'))

def test_exact_sentry_pin_in_primary_matrix():
    protocol=json.loads((ROOT/'configs/protocol.json').read_text())
    assert 'croniter-1.3.10' in protocol['implementations']

def test_extended_factorial_is_bounded_and_complete():
    data=json.loads((ROOT/'results/version-data-matrix.json').read_text())
    s=data['summary']
    assert s['traces']==10400
    assert s['timeouts']==0
    assert s['design']['same_utc_start_across_cells'] is True
    assert len(data['runs'])==s['traces']

def test_tzdb_byte_change_not_equated_with_behavior_change():
    s=json.loads((ROOT/'results/version-data-matrix.json').read_text())['summary']
    counts=s['data_effect_counts']
    assert counts['aps-3.11.2|byte_change_no_observed_behavior_change']>0
    assert counts['aps-3.11.2|accepted_data_effect']>0

def test_code_data_interactions_are_explicit():
    s=json.loads((ROOT/'results/version-data-matrix.json').read_text())['summary']
    assert s['interaction_count']==len(s['interactions'])==4
    assert {x['zone'] for x in s['interactions']}=={'America/Asuncion'}

def test_policy_matrix_separates_pass_unknown_and_violation():
    p=json.loads((ROOT/'results/policy-matrix.json').read_text())
    assert p['fold_counts']['first|first|PASS']==44
    assert p['fold_counts']['first|unspecified|UNDERSPECIFIED']==44
    assert p['fold_counts']['first|both|VIOLATION']==44
    assert p['gap_counts']['shift_forward|unspecified|UNDERSPECIFIED']==44
    assert p['gap_counts']['shift_forward|shift_forward|PASS']==44
    assert p['gap_counts']['shift_forward|skip|VIOLATION']==44
    assert p['gap_counts']['shift_backward|shift_backward|PASS']==44

def test_mutation_study_reports_sensitivity_and_specificity():
    m=json.loads((ROOT/'results/mutation-study.json').read_text())
    assert m['detected']==m['mutants']==651
    assert sum(v for k,v in m['benign_counts'].items() if k.endswith('|PASS'))==m['benign_cases']==384

def test_policy_blind_baseline_has_observed_false_alarms():
    c=json.loads((ROOT/'results/comparator-analysis.json').read_text())
    assert c['policy_blind_first_branch']['false_alarms_on_pass']==304
    assert c['policy_blind_first_branch']['missed_violations']==144

def test_release_diff_can_miss_shared_failure():
    c=json.loads((ROOT/'results/comparator-analysis.json').read_text())
    assert c['release_differential_aps']['counts']['shared_or_equal_missed_violations']==64
    assert c['release_differential_croniter']['counts']['shared_or_equal_missed_violations']==472


def test_posix_footer_expansion_matches_zoneinfo():
    for version,name in [('2026b','Europe/Chisinau'),('2026b','America/Vancouver')]:
        oracle=ref(name,version);lib=load_zone(version,name)
        for year in [2022,2026,2027]:
            for month in range(1,13):
                t=datetime(year,month,15,12,tzinfo=timezone.utc).timestamp()
                assert oracle.offset_at(t)==int(datetime.fromtimestamp(t,lib).utcoffset().total_seconds())
        for tr in oracle.transitions:
            if datetime(2022,1,1,tzinfo=timezone.utc).timestamp() <= tr.utc < datetime(2037,1,1,tzinfo=timezone.utc).timestamp():
                for t in [tr.utc-1,tr.utc,tr.utc+1]:
                    assert oracle.offset_at(t)==int(datetime.fromtimestamp(t,lib).utcoffset().total_seconds())


def test_current_release_holdout_is_executed_and_separate():
    s=json.loads((ROOT/'results/current-release-holdout.json').read_text())['summary']
    assert s['traces']==4224 and s['api_calls']==33456 and s['timeouts']==0
    assert s['release_comparisons']['aps-3.11.2->aps-3.11.3']['changed']==0
    assert s['release_comparisons']['croniter-2.0.1->croniter-6.2.4']['changed']==320
    assert s['status_counts']['croniter-6.2.4|VIOLATION']==8
    assert s['status_counts']['aps-3.11.3|VIOLATION']==40


def test_current_tzdb_holdout_classifies_source_named_changes():
    s=json.loads((ROOT/'results/current-tzdb-holdout.json').read_text())['summary']
    assert s['traces']==1056 and s['api_calls']==8448 and s['timeouts']==0
    assert s['effect_counts']['aps-3.11.3|accepted_data_effect']==15
    assert s['effect_counts']['croniter-6.2.4|accepted_data_effect']==16
    assert s['zone_effect_counts']['America/Vancouver|accepted_data_effect']==31


def test_decision_record_pack_is_replayable_and_pinned():
    pack=json.loads((ROOT/'results/regression-pack.json').read_text())
    assert pack['schema']=='zoneshift.regression-pack'
    assert len(pack['records'])==13
    rec=next(x for x in pack['records'] if x['implementation']=='croniter-6.2.4' and x['verdict']=='VIOLATION')
    assert len(rec['implementation_source_sha256'])==64
    assert len(rec['zone_file_sha256'])==64
    assert rec['expected_trace']


def test_current_release_scope_reports_execution_not_inference():
    c=json.loads((ROOT/'results/current-release-scope.json').read_text())
    assert c['apscheduler']['experiment_status'].startswith('executed')
    assert c['croniter']['experiment_status'].startswith('executed')
    assert c['tzdb']['executed_current_holdout']=='2026e'
    assert c['tzdb']['latest_verified_release_at_check']=='2026e'


def test_release_series_reaches_iana_2026e_with_exact_pinned_pairs():
    data=json.loads((ROOT/'results/rule-release-series.json').read_text())
    s=data['summary']
    assert s['release_pairs']==6 and s['affected_zones']==6
    assert s['traces']==3504 and s['api_calls']==28032
    assert s['timeouts']==0 and s['nonprogress']==0
    assert s['design']['pairs'][-1]['new']=='2026e'
    assert {x['new'] for x in s['design']['pairs']}=={'2026a','2026b','2026c','2026d','2026e'}


def test_release_series_never_waives_a_contract_violation_as_data_effect():
    rows=json.loads((ROOT/'results/rule-release-series.json').read_text())['classifications']
    accepted=[x for x in rows if x['classification']=='accepted_data_effect']
    blocked=[x for x in rows if x['classification']=='changed_with_violation_or_uncertainty']
    assert len(accepted)==256 and all(x['statuses']==['PASS','PASS'] for x in accepted)
    assert len(blocked)==28 and all('VIOLATION' in x['statuses'] or 'UNDERSPECIFIED' in x['statuses'] for x in blocked)


def test_latest_tzif_release_chain_cross_checks_zoneinfo_at_transitions():
    pairs=[
        ('2025b-py','Europe/Chisinau'),('2026a','Europe/Chisinau'),
        ('2026a','America/Vancouver'),('2026b','America/Vancouver'),
        ('2026b','America/Edmonton'),('2026c','America/Edmonton'),
        ('2026b','Africa/Casablanca'),('2026c','Africa/Casablanca'),
        ('2026c','America/Inuvik'),('2026d','America/Inuvik'),
        ('2026d','America/Winnipeg'),('2026e','America/Winnipeg'),
    ]
    lo=datetime(2022,1,1,tzinfo=timezone.utc).timestamp()
    hi=datetime(2037,1,1,tzinfo=timezone.utc).timestamp()
    for version,name in pairs:
        oracle=ref(name,version); lib=load_zone(version,name)
        for tr in oracle.transitions:
            if lo <= tr.utc < hi:
                for t in (tr.utc-1,tr.utc,tr.utc+1):
                    assert oracle.offset_at(t)==int(datetime.fromtimestamp(t,lib).utcoffset().total_seconds())


def test_signature_analysis_removes_zone_year_and_case_identity():
    s=json.loads((ROOT/'results/signature-budget.json').read_text())
    excluded=set(s['signature_definition']['excluded'])
    assert {'zone','year','raw timestamp','case id'} <= excluded
    for impl, full in s['full_pool'].items():
        assert full['boundary_unique_signatures'] <= full['boundary_violations']
        assert all(x['unique_signatures'] <= x['violations'] for x in full['uniform'])


def test_transition_sampling_improves_decorrelated_signature_yield():
    s=json.loads((ROOT/'results/signature-budget.json').read_text())
    auc=s['budget_averaged_unique_signatures']
    for impl in ('aps-3.11.0','aps-3.11.1','aps-3.11.2','croniter-1.3.10','croniter-2.0.1'):
        assert auc[f'{impl}|boundary'] > auc[f'{impl}|uniform']
    rows={(x['implementation'],x['strategy'],x['budget']):x for x in s['curve']}
    assert rows['aps-3.11.0','boundary',16]['detect_any_rate'] >= 0.95
    assert rows['croniter-1.3.10','boundary',16]['unique_signatures_mean'] > rows['croniter-1.3.10','uniform',16]['unique_signatures_mean']


def test_minimized_witnesses_are_pinned_replayed_and_decision_preserving():
    data=json.loads((ROOT/'results/minimized-witnesses.json').read_text())
    s=data['summary']
    assert s['witnesses']==43 and s['blocked']==31 and s['accepted_data_effects']==12
    assert s['all_preserve_real_executed_prefixes']
    assert s['all_replayed_exactly'] and s['all_decisions_preserved']
    assert s['replay_validation_api_calls']==426
    assert s['median_event_reduction'] >= 0.70
    for w in data['witnesses']:
        assert len(w['implementation_source_sha256'])==64
        assert w['replayed_exactly'] and w['decision_preserved']


def test_manifest_includes_full_stepwise_release_inputs():
    m=json.loads((ROOT/'data/tzdb/manifest.json').read_text())
    assert len(m)==47
    present={(x['version'],x['zone']) for x in m}
    required={
        ('2025b-py','Europe/Chisinau'),('2026a','Europe/Chisinau'),
        ('2026a','America/Vancouver'),('2026b','America/Vancouver'),
        ('2026b','America/Edmonton'),('2026c','America/Edmonton'),
        ('2026b','Africa/Casablanca'),('2026c','Africa/Casablanca'),
        ('2026c','America/Inuvik'),('2026d','America/Inuvik'),
        ('2026d','America/Winnipeg'),('2026e','America/Winnipeg'),
    }
    assert required <= present


def test_release_analysis_aggregate_matches_primary_results():
    x=json.loads((ROOT/'results/release-analysis.json').read_text())
    assert x['release_series']['traces']==3504
    assert x['release_series']['api_calls']==28032
    assert x['minimized_witnesses']['all_replayed_exactly']


def test_release_series_conversion_validation_has_no_mismatch():
    x=json.loads((ROOT/'results/release-series-validation.json').read_text())
    assert x['inputs']==12
    assert x['checks']==3*x['transition_records']
    assert x['checks']>0 and x['mismatches']==[]


def test_rule_release_decision_records_are_complete_and_pinned():
    records=[json.loads(x) for x in (ROOT/'results/release-series-decisions.jsonl').read_text().splitlines() if x]
    assert len(records)==1752
    assert all(x['schema']=='zoneshift.rule-release-decision' for x in records)
    assert all(len(x['implementation_source_sha256'])==64 for x in records)
    assert all(len(x['old_zone_file_sha256'])==64 and len(x['new_zone_file_sha256'])==64 for x in records)
    assert {x['new'] for x in records}=={'2026a','2026b','2026c','2026d','2026e'}


@pytest.mark.parametrize("gap_policy,expected_local", [
    ("shift_forward", "2024-03-10T03:30:00-04:00"),
    ("shift_backward", "2024-03-10T01:30:00-05:00"),
])
def test_explicit_gap_projection_policies(gap_policy, expected_local):
    zone = load_zone("2024a", "America/New_York")
    oracle = ref("America/New_York")
    start = datetime(2024, 3, 9, 2, 30, tzinfo=zone).timestamp()
    contract = Contract((2,), (30,), gap=gap_policy, fold="both")
    events, gaps = reference(oracle, contract, start, 8)
    assert gaps and gap_policy in gaps[0]
    first = required(events, contract)[0]
    assert datetime.fromtimestamp(first, zone).isoformat() == expected_local
    assert qualify(oracle, contract, start, trace(required(events, contract)[:8]))["status"] == "PASS"


def test_policy_completion_frontier_returns_exact_gap_support():
    zone = load_zone("2024a", "America/New_York")
    oracle = ref("America/New_York")
    start = datetime(2024, 3, 9, 2, 30, tzinfo=zone).timestamp()
    contract = Contract((2,), (30,), gap="unspecified", fold="both")
    run = run_trace("aps-3.11.2", zone, contract, start)
    frontier = policy_completion_frontier(oracle, contract, start, run["trace"], run["error"])
    assert frontier["classification"] == "policy_sensitive"
    assert frontier["passing_completions"] == [
        {"gap": "shift_forward", "fold": "both"}
    ]
    result = qualify(oracle, contract, start, run["trace"], run["error"])
    assert result["status"] == "UNDERSPECIFIED"
    assert result["reasons"] == ["policy_completion_required"]


def test_policy_frontier_study_uses_real_scheduler_calls():
    summary = json.loads((ROOT / "results/policy-frontiers.json").read_text())["summary"]
    assert summary["traces"] == 616
    assert summary["api_calls"] == 4752
    assert summary["timeouts"] == 0
    assert summary["classification_counts"]["aps-3.11.0|fold|robust_violation"] == 44
    assert summary["classification_counts"]["croniter-6.2.4|fold|policy_sensitive"] == 44
    assert summary["support_pattern_counts"]["croniter-6.2.4|gap|shift_forward+both"] == 44


def test_upgrade_sufficiency_certificate_unit_cases():
    code_only = {
        "old_code_old_data": "VIOLATION",
        "new_code_old_data": "PASS",
        "old_code_new_data": "VIOLATION",
        "new_code_new_data": "PASS",
    }
    assert minimal_sufficient_changes(code_only) == [["code"]]
    assert classify_upgrade_square(code_only)["decision"] == "code_change_sufficient"

    both = {
        "old_code_old_data": "VIOLATION",
        "new_code_old_data": "VIOLATION",
        "old_code_new_data": "VIOLATION",
        "new_code_new_data": "PASS",
    }
    assert minimal_sufficient_changes(both) == [["code", "data"]]
    assert classify_upgrade_square(both)["decision"] == "both_changes_required"


def test_upgrade_sufficiency_results_match_executed_square():
    summary = json.loads((ROOT / "results/upgrade-sufficiency.json").read_text())["summary"]
    assert summary["certificates"] == 2080
    assert summary["noncommutative_observations"] == 4
    counts = summary["decision_counts"]
    assert counts["aps-3.11.0->aps-3.11.2|code_change_sufficient"] == 84
    assert counts["aps-3.11.0->aps-3.11.2|either_single_change_sufficient"] == 4
    assert counts["croniter-1.3.10->croniter-2.0.1|data_change_sufficient"] == 12
    assert counts["croniter-1.3.10->croniter-2.0.1|no_passing_target"] == 248


def test_named_study_profiles_are_complete_and_shared():
    assert set(PROFILES) == {"midnight", "five_am", "hourly_30", "half_hourly"}
    assert all(contract.complete for contract in PROFILES.values())
    assert all(contract.gap == "skip" and contract.fold == "both" for contract in PROFILES.values())

@pytest.mark.parametrize(
    "gap_policy,expected_local",
    [
        ("shift_forward", "2024-03-10T03:30:00-04:00"),
        ("shift_backward", "2024-03-10T01:30:00-05:00"),
    ],
)
def test_intervention_executes_both_gap_projection_policies(gap_policy, expected_local):
    zone = load_zone("2024a", "America/New_York")
    previous = datetime(2024, 3, 9, 2, 30, tzinfo=zone)
    contract = Contract((2,), (30,), gap=gap_policy, fold="both")
    occurrence = wall_next(previous, contract)
    assert occurrence.isoformat() == expected_local
    assert qualify(
        ref("America/New_York"),
        contract,
        previous.timestamp(),
        [{"timestamp": occurrence.timestamp()}],
    )["status"] == "PASS"


def test_robust_policy_frontier_can_pass_without_inventing_irrelevant_policy():
    oracle = ref("Etc/UTC")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    incomplete = Contract((5,), (0,), gap="unspecified", fold="unspecified")
    explicit = Contract((5,), (0,), gap="skip", fold="both")
    events, _ = reference(oracle, explicit, start, 8)
    result = qualify(oracle, incomplete, start, trace(required(events, explicit)[:8]))
    assert result["status"] == "PASS"
    assert result["policy_frontier"]["classification"] == "robust_pass"
    assert result["policy_frontier"]["completion_count"] == 9


def test_upgrade_cli_executes_four_cells_and_emits_sufficiency_certificate(tmp_path, capsys):
    from zoneshift.__main__ import main

    output = tmp_path / "upgrade.json"
    code = main([str(ROOT / "configs/upgrade-square.json"), "--output", str(output)])
    capsys.readouterr()
    result = json.loads(output.read_text())
    assert code == 0
    assert set(result["cells"]) == {
        "old_code_old_data",
        "new_code_old_data",
        "old_code_new_data",
        "new_code_new_data",
    }
    assert result["certificate"]["decision"] == "either_single_change_sufficient"
    assert result["certificate"]["noncommutative_observation"] is True
