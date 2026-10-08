#!/usr/bin/env python3
"""Deterministic table/figure generation from raw runs (no fabricated values)."""
from pathlib import Path
import sys,json,collections,statistics,csv
ROOT=Path(__file__).resolve().parents[1]
def main():
    r=ROOT/'results'; out=ROOT/'paper/generated';out.mkdir(exist_ok=True,parents=True)
    runs=[json.loads(x) for x in (r/'runs.jsonl').read_text().splitlines()]
    groups=collections.defaultdict(list)
    for x in runs:groups[x['strategy'],x['implementation']].append(x)
    summaries=json.loads((r/'benchmark-summary.json').read_text());table=[]
    for impl in ['aps-3.11.0','aps-3.11.1','aps-3.11.2','croniter-1.3.10','croniter-2.0.1']:
        b=next(s for s in summaries if s['strategy']=='boundary' and s['implementation']==impl)
        u=[s['violation'] for s in summaries if s['strategy']=='uniform' and s['implementation']==impl]
        row=dict(implementation=impl,boundary_v=b['violation'],boundary_u=b['underspecified'],uniform_mean=statistics.mean(u),uniform_min=min(u),uniform_max=max(u),boundary_calls=sum(x['calls'] for x in groups['boundary',impl]),boundary_policy_blind=sum(x['policy_blind_alarm'] for x in groups['boundary',impl]),boundary_median_us=b['median_us'])
        table.append(row)
    pairs=collections.defaultdict(dict)
    for x in runs:
        if x['strategy']=='boundary':pairs[x['case_id']][x['implementation']]=x
    comparisons=[]
    for a,b in [('aps-3.11.0','aps-3.11.1'),('aps-3.11.1','aps-3.11.2'),('croniter-1.3.10','croniter-2.0.1'),('aps-3.11.2','croniter-2.0.1')]:
        c=collections.Counter()
        for p in pairs.values():
            x,y=p[a],p[b]
            same=[e['timestamp'] for e in x['trace']]==[e['timestamp'] for e in y['trace']]
            s1,s2=x['qualification']['status'],y['qualification']['status']
            c['same' if same else 'different']+=1
            c[('same' if same else 'different')+':'+s1+':'+s2]+=1
        comparisons.append(dict(left=a,right=b,counts=dict(c)))
    anchor=collections.Counter();reason=collections.Counter();profiles=collections.Counter();scopes=collections.Counter()
    protocol=json.loads((ROOT/'configs/protocol.json').read_text())
    for x in runs:
        if x['strategy']!='boundary':continue
        label='ordinary' if x['kind']=='ordinary' else str(x['anchor_offset'])
        st=x['qualification']['status'];impl=x['implementation']
        anchor[impl,label,st]+=1
        profiles[impl,x['profile'],st]+=1
        for why in x['qualification']['reasons']:reason[impl,why]+=1
        scope='discovery' if x['zone'] in protocol['discovery_zones'] else 'extension' if x['zone'] in protocol['extension_zones'] else 'control'
        scopes[impl,scope,st]+=1
    inter=json.loads((r/'intervention.json').read_text())
    cost=dict(before_median_us=statistics.median(x['before']['elapsed_ns']/1000 for x in inter),after_median_us=statistics.median(x['after_elapsed_ns']/1000 for x in inter),before_total_ms=sum(x['before']['elapsed_ns'] for x in inter)/1e6,after_total_ms=sum(x['after_elapsed_ns'] for x in inter)/1e6,windows=len(inter))
    findings=dict(table=table,comparisons=comparisons,anchor={':'.join(k):v for k,v in anchor.items()},reason={':'.join(k):v for k,v in reason.items()},profiles={':'.join(k):v for k,v in profiles.items()},scopes={':'.join(k):v for k,v in scopes.items()},intervention_cost=cost,total_runs=len(runs),total_calls=sum(x['calls'] for x in runs),timeouts=sum(x['error']=='timeout' for x in runs),errors=dict(collections.Counter(x['error'] for x in runs if x['error'])))
    (r/'analysis.json').write_text(json.dumps(findings,indent=2)+'\n')
    with (r/'principal-table.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    tex=[]
    for x in table:
        label=x['implementation'].replace('aps-','APS ').replace('croniter-','croniter ')
        tex.append(f"{label} & {x['boundary_v']} & {x['boundary_u']} & {x['uniform_mean']:.1f} [{x['uniform_min']},{x['uniform_max']}] & {x['boundary_calls']:,} \\\\")
    (out/'benchmark-rows.tex').write_text('\n'.join(tex)+'\n')
    header=r"""\begin{tabular}{lrrrr}
\toprule
Calculation module & Boundary V & U & Uniform V & Calls$^a$\\
\midrule
"""
    footer=r"""\bottomrule
\multicolumn{5}{l}{$^a$Actual next-occurrence calls in the boundary matrix.}
\end{tabular}
"""
    (out/'benchmark-table.tex').write_text(header+'\n'.join(tex)+'\n'+footer)
    names=['aps-3.11.0','aps-3.11.2','croniter-2.0.1']
    with (out/'anchors.dat').open('w') as f:
        f.write('anchor APS0 APS2 Croniter\n')
        for i,k in enumerate(['-86400','-3600','1','ordinary']):
            f.write(str(i)+' '+' '.join(str(anchor[n,k,'VIOLATION']) for n in names)+'\n')
    print(json.dumps(findings,indent=2))
if __name__=='__main__':main()
