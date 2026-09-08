#!/usr/bin/env python3
"""Validate advisory resource models with whole architecture levels held out."""
import argparse
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.cost import calibrate,predict
from architecture_search.model import file_hash,metric_number,write_json

METRICS=('lut','ff','dsp','bram','uram')


def holdouts(samples):
    folds=[]
    for axis in ('pe','stage_groups'):
        for value in sorted({r['configuration'].get(axis,1) for r in samples}):
            training=[r for r in samples if r['configuration'].get(axis,1)!=value]
            held=[r for r in samples if r['configuration'].get(axis,1)==value]
            if not training:continue
            if {r['rtl_hash'] for r in training}&{r['rtl_hash'] for r in held}:raise ValueError('training/validation RTL overlap')
            methods={}
            for method in ('nearest','structural'):
                errors={metric:[] for metric in METRICS};predictions=[]
                for sample in held:
                    row={'configuration':sample['configuration'],'rtl_hash':sample['rtl_hash'],'predictions':{}}
                    for metric in METRICS:
                        result=predict(training,sample['configuration'],metric,method)
                        actual=sample['metrics'].get(metric)
                        row['predictions'][metric]={'prediction':result,'measured':actual}
                        if result.get('available') and metric_number(actual):errors[metric].append(abs(result['estimate']-actual))
                    predictions.append(row)
                methods[method]={'predictions':predictions,'errors':{metric:{'predicted':len(values),'held_out':len(held),
                                  'mean_absolute_error':statistics.mean(values) if values else None} for metric,values in errors.items()}}
            folds.append({'axis':axis,'held_out_value':value,'training_rtl_hashes':[r['rtl_hash'] for r in training],
                          'held_out_rtl_hashes':[r['rtl_hash'] for r in held],'methods':methods})
    return folds


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--reports',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();c=json.loads(a.campaign.read_text());reports=[json.loads(p.read_text()) for p in a.reports]
    model=calibrate(reports,c['workload'],c.get('target',{}))
    if len(model['samples'])<3:p.error('at least three eligible measurements required')
    write_json(a.output,{'schema':'ntt-cost-architecture-holdouts-v1','workload':c['workload'],'target':c.get('target',{}),
                        'evidence_integrity':model['evidence_integrity'],'rejected_records':model['rejected_records'],
                        'folds':holdouts(model['samples']),'inputs':{str(p.resolve()):file_hash(p) for p in [a.campaign,*a.reports]},
                        'limitation':'Same-workload architecture-level holdouts. Unavailable predictions are reported, never assigned zero error. Empirical errors provide no pruning certificate or cross-workload guarantee.'})
    print(a.output)

if __name__=='__main__':main()
