#!/usr/bin/env python3
"""Entry point for reproducible architecture search."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from architecture_search.search import main
from check_ngen_build import verify


def checked_main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    # Planning and historical reporting do not execute NGen. Full argument
    # validation remains in search.main after this executable freshness gate.
    preflight=argparse.ArgumentParser(add_help=False)
    preflight.add_argument('--mode',default='plan')
    preflight.add_argument('--ngen-root',type=Path,default=Path(__file__).resolve().parents[2]/'NGen')
    options,_=preflight.parse_known_args(argv)
    if options.mode in ('run','resume') and '--help' not in argv and '-h' not in argv:
        identity=verify(options.ngen_root)
        if not identity['verified']:
            print('NGen build verification failed: '+json.dumps(identity),file=sys.stderr)
            print('Rebuild this checkout with sbt assembly before executing a new campaign.',file=sys.stderr)
            return 2
    return main(argv)

if __name__ == '__main__':
    raise SystemExit(checked_main())
