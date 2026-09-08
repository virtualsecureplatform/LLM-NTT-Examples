#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.cost import calibrate
from architecture_search.model import write_json
p=argparse.ArgumentParser(description='Fit advisory costs from actual implementation reports with leave-one-out validation.')
p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--reports',type=Path,nargs='+',required=True)
p.add_argument('--stage',choices=['synthesis','route'],default='synthesis')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--method',choices=['nearest','structural'],default='nearest')
a=p.parse_args();c=json.loads(a.campaign.read_text())
write_json(a.output,calibrate([json.loads(f.read_text()) for f in a.reports],c['workload'],c.get('target',{}),a.stage,a.method))
