#!/usr/bin/env python3
"""Emit exact, reproducible FHE workloads; each campaign has its own hardware budget."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.oracle import field
from architecture_search.model import write_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--sizes',type=int,nargs='+',default=[16384,65536,131072])
p.add_argument('--bits',type=int,nargs='+',default=[32,54,64])
p.add_argument('--lanes',type=int,default=4)
p.add_argument('--stages',nargs='+',choices=['simulation','synthesis','route'],default=['simulation'])
a=p.parse_args()
if a.output_dir.exists() and any(a.output_dir.iterdir()):p.error('output directory must be empty')
for n in a.sizes:
    if a.lanes<1 or a.lanes&(a.lanes-1) or n%a.lanes:p.error('lanes must be a power of two dividing N')
    for bits in a.bits:
        domain=field(n,bits)
        for direction in ('forward','inverse'):
            campaign={'workload':{'kind':'generic',**domain,'direction':direction,'negacyclic':True,'lanes':a.lanes},
                      'target':{'part':'xcu280-fsvh2892-2L-e','tool_version':'2023.2','clock_period_ns':4.0},
                      'stages':a.stages,'budget':{'hours':12,'functional':64,'synthesis':12,'route':4},
                      'space':{'pe':[1,2,4,8],'radix':[2,4],'reductions':['barrett','montgomery','shoup'],'stage_groups':[1,2,4]}}
            write_json(a.output_dir/f'n{n}-q{bits}-{direction}.json',campaign)
print(a.output_dir)
