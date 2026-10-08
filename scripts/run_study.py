#!/usr/bin/env python3
"""Generate and execute the predeclared local, bounded scheduler study."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import argparse,collections,csv,hashlib,json,platform,random,time
from datetime import datetime,timedelta,timezone
from zoneshift.adapters import aps_class,sentry_next
from zoneshift.execution import run_trace,load_zone
from zoneshift.contracts import Contract, reference, qualify, elapsed_reference
from zoneshift.profiles import PROFILES
from zoneshift.tzif import TZif

P=json.loads((ROOT/'configs/protocol.json').read_text())
UTC=timezone.utc


def save_json(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')


def anchors(zone,year):
    lo=int(datetime(year,1,1,tzinfo=UTC).timestamp())
    hi=int(datetime(year+1,1,1,tzinfo=UTC).timestamp())
    ts=[t for t in zone.transitions if lo<=t.utc<hi]
    if ts:
        return [(t.utc+o,'transition',t.delta,o) for t in ts for o in P['transition_anchor_offsets_seconds']]
    return [(int(datetime(year,m,15,12,tzinfo=UTC).timestamp()),'ordinary',0,0) for m in [1,7]]


def oracle_validation(out):
    """Independent UTC offset/roundtrip check at transition boundaries and random instants."""
    rng=random.Random(7907);n=0;trans=0; failures=[]
    for row in json.loads((ROOT/'data/tzdb/manifest.json').read_text()):
        version,name=row['version'],row['zone']
        ref=TZif(ROOT/'data/tzdb'/version/name); lib=load_zone(version,name)
        stamps=[rng.randrange(1262304000,1798761600) for _ in range(200)]
        for tr in ref.transitions:
            if 1262304000<=tr.utc<1798761600:
                trans+=1;stamps += [tr.utc-1,tr.utc,tr.utc+1,tr.utc+1800]
        for t in stamps:
            a=ref.wall(t); b=datetime.fromtimestamp(t,lib).replace(tzinfo=None)
            candidates=ref.resolve(a)
            if a!=b or t not in candidates:failures.append((version,name,t,str(a),str(b),candidates))
            n+=1
    result={'checks':n,'transition_records':trans,'failures':failures,
            'qualification':'Independent conversion algorithms over shared public TZif data, not independent rule truth'}
    save_json(out/'oracle-validation.json',result)
    assert not failures,failures[:2]
    return result


def benchmark(out,only_transition=False):
    zones=P['discovery_zones']+P['extension_zones']+P['negative_control_zones']
    cases=[]
    for name in zones:
        ref=TZif(ROOT/'data/tzdb/2024a'/name)
        for year in P['years']:
            for index,(start,kind,delta,offset) in enumerate(anchors(ref,year)):
                for profile in P['profiles']:
                    cases.append(dict(case_id=f'{name}:{year}:{index}:{profile}',zone=name,year=year,profile=profile,start=start,kind=kind,transition_delta=delta,anchor_offset=offset))
    save_json(out/'design.json',{'cases_per_strategy':len(cases),'protocol_sha256':hashlib.sha256((ROOT/'configs/protocol.json').read_bytes()).hexdigest(),'case_specification':cases})
    strategies=[('boundary',None)] + ([] if only_transition else [('uniform',s) for s in P['uniform_seeds']])
    # TZif parsing and ZoneInfo construction are immutable inputs for this study.
    # Cache them per zone so the experiment measures scheduler calls rather than
    # repeatedly reopening the same 16 files tens of thousands of times.
    ref_cache={name:TZif(ROOT/'data/tzdb/2024a'/name) for name in zones}
    zone_cache={name:load_zone('2024a',name) for name in zones}
    counters=collections.Counter();timings=collections.defaultdict(list)
    with (out/'runs.jsonl').open('w') as f:
        for strategy,seed in strategies:
            rng=random.Random(seed)
            for impl in P['implementations']:
                # Reset RNG so each implementation receives identical matched starts.
                rng=random.Random(seed)
                for case in cases:
                    spec=case.copy()
                    if strategy=='uniform':
                        lo=int(datetime(case['year'],1,1,tzinfo=UTC).timestamp())
                        hi=int(datetime(case['year']+1,1,1,tzinfo=UTC).timestamp())
                        spec['start']=rng.randrange(lo,hi)
                        spec.update(kind='uniform', transition_delta=None, anchor_offset=None)
                    name=spec['zone']; c=PROFILES[spec['profile']]
                    ref=ref_cache[name]
                    zone=zone_cache[name]
                    r=run_trace(impl,zone,c,spec['start'])
                    q=qualify(ref,c,spec['start'],r['trace'],r['error'])
                    expected,_=reference(ref,c,spec['start'],8)
                    # Policy-blind comparator: exactly one (first) instant per civil label.
                    strict=[e['timestamp'] for e in expected if e['branch']==0][:8]
                    r.update(spec);r.update(implementation=impl,strategy=strategy,seed=seed,tzdb='2024a',qualification=q,
                         policy_blind_alarm=([x['timestamp'] for x in r['trace']]!=strict),expected_first_branch=strict)
                    f.write(json.dumps(r,separators=(',',':'))+'\n')
                    counters[(strategy,seed,impl,q['status'])]+=1
                    timings[(strategy,seed,impl)].append(r['elapsed_ns'])
                f.flush(); print(strategy,seed,impl,{st:counters[strategy,seed,impl,st] for st in ['PASS','VIOLATION','UNDERSPECIFIED']},flush=True)
    summary=[]
    for (strategy,seed,impl),ts in timings.items():
        ts=sorted(ts)
        summary.append(dict(strategy=strategy,seed=seed,implementation=impl,n=len(ts),
           **{st.lower():counters[strategy,seed,impl,st] for st in ['PASS','VIOLATION','UNDERSPECIFIED']},
           total_api_seconds=sum(ts)/1e9,median_us=ts[len(ts)//2]/1000,p95_us=ts[int(.95*(len(ts)-1))]/1000))
    save_json(out/'benchmark-summary.json',summary)
    return summary


def historical(out):
    raw=[]
    specs=[('APS-529-family','America/Chicago',(2021,3,14,0,0),Contract((0,), (0,), gap='skip', fold='both'),0),
           ('APS-1021-fold','Europe/Helsinki',(2017,10,29,3,45),Contract(tuple(range(24)), (30,), gap='skip', fold='both'),1),
           ('SENTRY-66868-spring','America/New_York',(2024,3,9,5,0),Contract((5,), (0,), gap='skip', fold='both'),0),
           ('SENTRY-66868-autumn','America/New_York',(2024,11,2,5,0),Contract((5,), (0,), gap='skip', fold='both'),0)]
    for ident,name,args,c,fold in specs:
        z=load_zone('2024a',name);ref=TZif(ROOT/'data/tzdb/2024a'/name)
        start=datetime(*args,tzinfo=z,fold=fold).timestamp()
        for impl in (P['implementations'][:3] if ident.startswith('APS') else ['sentry-adapter']):
            r=run_trace(impl,z,c,start);q=qualify(ref,c,start,r['trace'],r['error'])
            raw.append(dict(case_id=ident,implementation=impl,start=datetime.fromtimestamp(start,z).isoformat(),start_epoch=start,zone=name,contract=c.to_dict(),**r,qualification=q))
    save_json(out/'historical.json',raw)
    return raw


def upstream_inputs(out):
    # Exactly four parameter tuples in test_dst_change at upstream 3.11.0.
    cases=[('absolute_spring',{'hour':8},(2013,3,9,12,0),0,(2013,3,10,8,0),1),
           ('absolute_autumn',{'hour':8},(2013,11,2,12,0),1,(2013,11,3,8,0),1),
           ('interval_spring',{'minute':'*/30'},(2013,3,10,1,35),1,(2013,3,10,3,0),1),
           ('interval_autumn',{'minute':'*/30'},(2013,11,3,1,35),0,(2013,11,3,1,0),1)]
    result=[]
    z=load_zone('2024a','America/New_York')
    for v in ['3.11.0','3.11.1','3.11.2']:
        for name,args,start,fold,exp,efold in cases:
            trigger=aps_class(v)(**args,timezone=z)
            actual=trigger.get_next_fire_time(None,datetime(*start,tzinfo=z,fold=fold))
            expected=datetime(*exp,tzinfo=z,fold=efold)
            result.append(dict(suite='upstream-3.11.0-DST-inputs',name=name,version=v,expected=str(expected),actual=str(actual),passed=str(actual)==str(expected)))
        # Strongest cheap baseline: directly transplant the published regression.
        zh=load_zone('2024a','Europe/Helsinki')
        trigger=aps_class(v)(minute=30,timezone=zh)
        d=datetime(2017,10,29,3,30,0,5,tzinfo=zh,fold=1)
        expected=datetime(2017,10,29,4,30,tzinfo=zh)
        actual=trigger.get_next_fire_time(None,d)
        result.append(dict(suite='upstream-3.11.2-regression-input',name='fold_microseconds',version=v,expected=str(expected),actual=str(actual),passed=str(actual)==str(expected)))
    save_json(out/'upstream-inputs.json',result)
    return result


def rule_change(out):
    result=[]
    c=Contract((5,),(0,),gap='skip',fold='both')
    name='America/Asuncion'
    for month,day in [(3,15),(3,22),(3,23),(4,1),(6,1),(9,1),(10,6),(12,1)]:
        for impl in P['implementations']:
            traces={}
            for tz in ['2024a','2025b']:
                z=load_zone(tz,name);ref=TZif(ROOT/'data/tzdb'/tz/name)
                # Compare the same instant, not differently interpreted starting wall labels.
                start=datetime(2025,month,day,12,tzinfo=UTC).timestamp()
                r=run_trace(impl,z,c,start);r['qualification']=qualify(ref,c,start,r['trace'],r['error']);traces[tz]=r
            changed=[x['timestamp'] for x in traces['2024a']['trace']]!=[x['timestamp'] for x in traces['2025b']['trace']]
            both_pass=all(r['qualification']['status']=='PASS' for r in traces.values())
            verdict='EXPECTED_CHANGE' if changed and both_pass else 'VIOLATION' if not both_pass else 'UNCHANGED'
            result.append(dict(implementation=impl,start_utc=f'2025-{month:02}-{day:02}T12:00:00Z',changed=changed,verdict=verdict,
                  explanation='IANA tz 2025a NEWS: Paraguay permanent -03 after 2024-10-06; future timestamp changes start 2025-03-22',runs=traces))
    save_json(out/'tzdb-update.json',result)
    return result


def controls_and_intervention(out):
    rows=[]
    # Legal duplicated civil labels at distinct instants and a legal missing gap label.
    for name,date in [('America/New_York',(2024,3,10,1,30)),('America/New_York',(2024,11,3,0,30)),('Australia/Lord_Howe',(2024,10,6,1,30)),('Australia/Lord_Howe',(2024,4,7,0,30))]:
        z=load_zone('2024a',name);ref=TZif(ROOT/'data/tzdb/2024a'/name)
        c=Contract(tuple(range(24)),(0,30),gap='skip',fold='both')
        start=datetime(*date,tzinfo=z).timestamp();r=run_trace('aps-3.11.2',z,c,start)
        q=qualify(ref,c,start,r['trace'],r['error'])
        exp,_=reference(ref,c,start,8)
        first=[e['timestamp'] for e in exp if e['branch']==0][:8]
        naive=[x['timestamp'] for x in r['trace']]!=first
        rows.append(dict(kind='documented-wall-clock-control',zone=name,start=start,contract=c.to_dict(),**r,qualification=q,policy_blind_alarm=naive))
    # Explicit underspecification check on a daily label inside a gap.
    name='America/New_York';z=load_zone('2024a',name);ref=TZif(ROOT/'data/tzdb/2024a'/name)
    c=Contract((2,),(30,));start=datetime(2024,3,9,2,30,tzinfo=z).timestamp()
    r=run_trace('aps-3.11.2',z,c,start);rows.append(dict(kind='underspecified-gap-normalization',zone=name,start=start,contract=c.to_dict(),**r,qualification=qualify(ref,c,start,r['trace'],r['error'])))
    # Local adapter intervention: bounded fixed-time wall recurrence, not an upstream patch.
    intervention=[]
    for name in P['discovery_zones']+P['extension_zones']:
        ref=TZif(ROOT/'data/tzdb/2024a'/name);z=load_zone('2024a',name)
        for year in P['years']:
            for start,kind,delta,off in anchors(ref,year):
                if off!=-86400:continue
                c=Contract((5,),(0,),gap='skip',fold='both')
                before=run_trace('sentry-adapter',z,c,start)
                # Distinct implementation: ZoneInfo roundtrip repair, not the TZif oracle.
                from zoneshift.repair import wall_next
                repaired=[];cur=start;tim=time.perf_counter_ns()
                for _ in range(8):
                    value=wall_next(datetime.fromtimestamp(cur,z),c)
                    cur=value.timestamp();repaired.append({'timestamp':cur,'iso':value.isoformat(),'fold':value.fold})
                after_ns=time.perf_counter_ns()-tim
                intervention.append(dict(zone=name,year=year,start=start,transition_delta=delta,before=before,
                     before_qualification=qualify(ref,c,start,before['trace'],before['error']),after=repaired,
                     after_qualification=qualify(ref,c,start,repaired),after_elapsed_ns=after_ns))
    save_json(out/'controls.json',rows);save_json(out/'intervention.json',intervention)
    # Mutation sensitivity, generated only from an independently validated ordinary trace.
    c=Contract((5,),(0,),gap='skip',fold='both');start=datetime(2024,1,10,5,tzinfo=z).timestamp()
    base=[];cur=start
    from zoneshift.repair import wall_next
    for _ in range(8):
        value=wall_next(datetime.fromtimestamp(cur,z),c);cur=value.timestamp();base.append({'timestamp':cur,'iso':value.isoformat(),'fold':value.fold})
    variants={
      'drop_valid':base[:2]+base[3:],
      'repeat_instant':base[:2]+[base[1]]+base[2:],
      'move_one_hour':[dict(x,timestamp=x['timestamp']+3600) for x in base],
      'reverse_pair':base[:1]+[base[2],base[1]]+base[3:],
      'wrong_minute':[dict(x,timestamp=x['timestamp']+60) for x in base],
      'empty':[],
    }
    mutations=[dict(name=k,qualification=qualify(ref,c,start,v)) for k,v in variants.items()]
    save_json(out/'mutations.json',mutations)
    return rows,intervention


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'results');p.add_argument('--only-transition',action='store_true');args=p.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    begin=time.perf_counter();env={'python':sys.version,'platform':platform.platform(),'processor':platform.processor(),'utc_execution':datetime.now(UTC).isoformat(),'protocol_sha256':hashlib.sha256((ROOT/'configs/protocol.json').read_bytes()).hexdigest()}
    import dateutil,pytz
    env.update(dateutil=dateutil.__version__,pytz=pytz.__version__)
    save_json(out/'environment.json',env)
    oracle_validation(out);historical(out);upstream_inputs(out);rule_change(out);controls_and_intervention(out)
    benchmark(out,args.only_transition)
    env['study_wall_seconds']=time.perf_counter()-begin;save_json(out/'environment.json',env)
    print('DONE',env['study_wall_seconds'],flush=True)
if __name__=='__main__':main()
