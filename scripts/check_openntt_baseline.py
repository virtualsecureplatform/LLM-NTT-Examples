#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.openntt import evaluate,evaluate_stream
p=argparse.ArgumentParser(description='Independently verify a prepared OpenNTT reference.')
p.add_argument('--baseline-dir',type=Path,required=True)
p.add_argument('--stream',action='store_true')
p.add_argument('--timeout',type=float,default=600)
a=p.parse_args();r=(evaluate_stream if a.stream else evaluate)(a.baseline_dir.resolve(),a.timeout)
print({'correct':r['correct'],'metrics':r['metrics'],'results_dir':str(a.baseline_dir/('stream' if a.stream else 'independent'))})
raise SystemExit(0 if r['correct'] else 1)
