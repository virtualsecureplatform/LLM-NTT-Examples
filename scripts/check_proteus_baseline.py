#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.proteus import evaluate,evaluate_stream
p=argparse.ArgumentParser(description='Verify an exact-field Proteus reference against the independent oracle.')
p.add_argument('--baseline-dir',type=Path,required=True)
p.add_argument('--timeout',type=float,default=600)
p.add_argument('--simulator',choices=['verilator','icarus'],default='verilator')
p.add_argument('--stream',action='store_true')
a=p.parse_args();r=(evaluate_stream if a.stream else evaluate)(a.baseline_dir.resolve(),a.timeout,a.simulator)
print({'correct':r['correct'],'metrics':r['metrics'],'results':str(a.baseline_dir/('stream' if a.stream else 'independent')/'results.json')})
raise SystemExit(0 if r['correct'] else 1)
