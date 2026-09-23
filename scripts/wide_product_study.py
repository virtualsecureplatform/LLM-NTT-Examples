#!/usr/bin/env python3
"""Run bounded version-2 arithmetic coverage and exact TFHEpp campaigns."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search import wide_products,release
from architecture_search.model import write_json,evidence_integrity
from architecture_search.search import main as search_main,report as search_report
from scripts.verify_tfhe_product import main as verify_tfhe


def campaigns(stage):
    points=[]
    if stage=='tfhe':points=[('tfhe-1024',wide_products.tfhe_workload(),dict(fractional_bits=[48]))]
    else:
        for ring in ('linear','cyclic','negacyclic'):
            for name,bound in [('direct',7),('split',127),('crt',32767)]:
                points.append((f'{ring}-{name}',wide_products.workload(16,bound,ring),dict(fractional_bits=[24,32,40,48],guard_bits=[0,2])))
        mixed=wide_products.workload(32,ring='negacyclic',modulus=65537)
        mixed.update(a_range=[-128,127],b_range=[0,255]);points.append(('mixed-signed-modular',mixed,dict(fractional_bits=[48])))
    result={}
    for name,w,space in points:
        configurations=wide_products.candidates(w,space);space['configurations']=configurations
        result[name]=dict(workload=w,space=space,target={**release.TARGET,'clock_period_ns':8,'input_hold_buffer_stages':1},
            stages=['simulation','synthesis'] if stage=='tfhe' else ['simulation'],
            evaluation=dict(simulator='verilator' if w['n']>=64 else 'iverilog',
                            timeout_seconds=28800 if stage=='tfhe' else (14400 if w['n']>=64 else 1800)),
            budget=dict(hours=24 if stage=='tfhe' else 8,functional=len(configurations),synthesis=len(configurations) if stage=='tfhe' else 0,route=0))
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True,choices=['coverage','tfhe'])
    p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--resume',action='store_true');a=p.parse_args(argv)
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.stage=='tfhe':verify_tfhe(['--output-dir',str(out/'tfhe-oracle')])
    result={};definitions=campaigns(a.stage)
    for name,c in definitions.items():
        path=out/(name+'.json');directory=out/name
        if path.exists() and json.loads(path.read_text())!=c:raise ValueError('campaign changed')
        write_json(path,c);mode='resume' if a.resume and (directory/'manifest.json').exists() else 'run'
        code=search_main(['--campaign',str(path),'--output-dir',str(directory),'--mode',mode])
        r=search_report(directory,c);records=r['candidates']
        accounted=len(records)==len(c['space']['configurations'])
        allowed={'complete','duplicate','numerically_unqualified','hardware_failed'}
        functional=accounted and all(x['status'] in allowed for x in records)
        families={x['configuration']['generator'] for x in records if x.get('correct')}
        synthesis=(a.stage!='tfhe' or all(x.get('evidence',{}).get('synthesis',{}).get('implementation_passed') and evidence_integrity(x['evidence']['synthesis'])=='verified' for x in records if x.get('correct')))
        corpus_matched=True
        if a.stage=='tfhe':
            oracle=json.loads((out/'tfhe-oracle/verification.json').read_text())
            corpus_matched=all(x.get('evaluation',{}).get('corpus_sha256')==oracle['corpus_sha256'] for x in records if x.get('correct'))
        passed=functional and families=={'ngen','sgen'} and synthesis and corpus_matched
        result[name]=dict(passed=passed,corpus_matched=corpus_matched,exit_code=code,report=str(directory/'report.json'))
        write_json(out/(a.stage+'.json'),dict(complete=len(result)==len(definitions) and all(x['passed'] for x in result.values()),campaigns=result))
        if not passed:return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
