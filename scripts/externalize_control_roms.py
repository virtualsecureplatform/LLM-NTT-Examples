#!/usr/bin/env python3
"""Move NGen explicit control ROM words to equivalent readmemh files."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.rom import externalize

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('rtl',type=Path);a=p.parse_args();print(json.dumps(externalize(a.rtl.resolve()),indent=2))
