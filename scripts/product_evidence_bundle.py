#!/usr/bin/env python3
"""Export or verify portable product-research evidence without changing provenance."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.evidence_bundle import export,verify
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path)
p.add_argument('--reports',nargs='+',type=Path);p.add_argument('--verify',action='store_true');a=p.parse_args()
if a.verify:result=verify(a.output_dir)
else:
    if not a.reports:p.error('--reports is required for export')
    export(a.reports,a.output_dir,[Path(__file__).resolve().parents[1]]);result=verify(a.output_dir)
print(json.dumps(result,indent=2))
