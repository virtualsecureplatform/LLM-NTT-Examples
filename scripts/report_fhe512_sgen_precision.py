#!/usr/bin/env python3
"""Combine pinned SGen precision runs into a complete N=512 evidence matrix."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.fhe512_sgen_precision import frontier, markdown
from architecture_search.model import digest, write_json


def combine(paths,fractions=(30,32),omissions=(0,1,2)):
    expected={(f,o) for f in fractions for o in omissions}
    allowed=expected|{(24,0)}
    rows={};reference=None;manifests=[]
    for path in paths:
        result=json.loads(path.read_text());manifest=result['manifest']
        comparable={key:manifest[key] for key in ('workload','error_limit','corpus_sha256',
                                                  'simulator','image_sha256','source_sha256',
                                                  'yosys_sha256','simulator_version')}
        if reference is None:reference=comparable
        elif comparable!=reference:raise ValueError(f'incompatible campaign {path}')
        manifests.append(digest(manifest))
        for point in result['points']:
            key=(point['fractional_bits'],point['omit_low_diagonals'])
            if key not in allowed:continue
            if key in rows:raise ValueError(f'duplicate SGen configuration {key}')
            row=point.copy()
            if not row['leaf_certificate']['qualified']:
                row['max_abs_error']=None
            rows[key]=row
    if not expected<=set(rows):raise ValueError(f'missing SGen configurations: {sorted(expected-set(rows))}')
    if reference['workload']['n']!=512:raise ValueError('the evidence matrix requires N=512')
    return [rows[key] for key in sorted(rows)],reference,manifests


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('results',type=Path,nargs='+')
    p.add_argument('--output-md',type=Path,required=True)
    p.add_argument('--output-csv',type=Path,required=True)
    p.add_argument('--evidence-file',type=Path,required=True)
    a=p.parse_args(argv)
    rows,reference,manifests=combine(a.results)
    a.output_md.write_text(markdown(rows,reference['workload'],reference['error_limit']))
    fields=('name','fractional_bits','omit_low_diagonals','digit_products','max_abs_error',
            'observed_max_abs_error','rms_error','signed_bias','yosys_cells','memory_bits',
            'register_bits','multipliers','latency_cycles',
            'initiation_interval_cycles','throughput_products_per_1000_cycles','simulation_passed',
            'yosys_passed','status','rtl_sha256')
    with a.output_csv.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    keep=fields+('error','generation_assurance_passed')
    evidence=dict(schema='fhe512-sgen-precision-evidence-v1',reference=reference,
                  campaign_manifest_sha256=manifests,
                  frontier=frontier(rows),
                  points=[{key:row[key] for key in keep if key in row} |
                          {'leaf_final_error_bound':row['leaf_certificate']['final_error_bound']}
                          for row in rows],
                  limitation='Exploratory torus-error bounds and coarse Yosys counts; no FHE noise qualification or U280 timing')
    write_json(a.evidence_file,evidence)
    print(f'{len(rows)} configurations: {a.output_md}')


if __name__=='__main__':main()
