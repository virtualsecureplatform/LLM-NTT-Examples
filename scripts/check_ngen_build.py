#!/usr/bin/env python3
"""Verify the assembled NGen source manifest against its current checkout."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from architecture_search.build_identity import RESOURCE,source_files,verify

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngen-root',type=Path,required=True)
    p.add_argument('--binary',type=Path)
    a=p.parse_args();result=verify(a.ngen_root,a.binary)
    print(json.dumps(result,indent=2));return 0 if result['verified'] else 1

if __name__=='__main__':raise SystemExit(main())
