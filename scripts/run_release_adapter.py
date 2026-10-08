#!/usr/bin/env python3
"""Post-freeze replication using Sentry 24.3.0's exact croniter pin."""
from pathlib import Path
import sys,argparse,json,collections,time,statistics
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from datetime import datetime
from zoneshift.adapters import aps_class
from zoneshift.contracts import Contract,qualify
from zoneshift.execution import run_trace,load_zone
from zoneshift.repair import wall_next
from zoneshift.tzif import TZif
from run_study import anchors,P,save_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'results');args=p.parse_args();out=args.output;out.mkdir(exist_ok=True,parents=True)
    rows=[];hist=[]
    c=Contract((5,),(0,),gap='skip',fold='both')
    for name in P['discovery_zones']+P['extension_zones']:
        z=load_zone('2024a',name);ref=TZif(ROOT/'data/tzdb/2024a'/name)
        for year in P['years']:
            for start,kind,delta,off in anchors(ref,year):
                if off!=-86400:continue
                before=run_trace('sentry-24.3.0',z,c,start)
                after=[];cur=start;t=time.perf_counter_ns()
                for _ in range(8):
                    d=wall_next(datetime.fromtimestamp(cur,z),c);cur=d.timestamp();after.append(dict(timestamp=cur,iso=d.isoformat(),fold=d.fold))
                ns=time.perf_counter_ns()-t
                rows.append(dict(zone=name,year=year,start=start,before=before,before_qualification=qualify(ref,c,start,before['trace'],before['error']),after=after,after_qualification=qualify(ref,c,start,after),after_elapsed_ns=ns))
    name='America/New_York';z=load_zone('2024a',name);ref=TZif(ROOT/'data/tzdb/2024a'/name)
    for season,month,day in [('spring',3,9),('autumn',11,2)]:
        d=datetime(2024,month,day,5,tzinfo=z);r=run_trace('sentry-24.3.0',z,c,d.timestamp());hist.append(dict(season=season,start=d.isoformat(),**r,qualification=qualify(ref,c,d.timestamp(),r['trace'],r['error'])))
    result=dict(source='Sentry 24.3.0 requirements-frozen.txt: croniter==1.3.10; crontab branch reconstructed, not full application',design='Post-freeze exact-pin replication; not a new historical family',historical=hist,runs=rows,summary=dict(n=len(rows),before=dict(collections.Counter(x['before_qualification']['status'] for x in rows)),after=dict(collections.Counter(x['after_qualification']['status'] for x in rows)),before_median_us=statistics.median(x['before']['elapsed_ns']/1000 for x in rows),after_median_us=statistics.median(x['after_elapsed_ns']/1000 for x in rows)))
    save_json(out/'released-sentry.json',result)
    direct=[];z=load_zone('2024a','Europe/Helsinki')
    for v in ['3.11.0','3.11.1','3.11.2']:
        tr=aps_class(v)(minute=30,timezone=z);d=datetime(2017,10,29,3,45,tzinfo=z,fold=1);seq=[]
        for _ in range(2):
            val=tr.get_next_fire_time(d,d);seq.append(dict(previous=d.isoformat(),next=val.isoformat(),delta_seconds=val.timestamp()-d.timestamp()));d=val
        direct.append(dict(version=v,steps=seq))
    save_json(out/'direct-fold-replay.json',direct)
    print(json.dumps(result['summary'],indent=2))
if __name__=='__main__':main()
