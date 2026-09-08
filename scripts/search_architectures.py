#!/usr/bin/env python3
"""Entry point for reproducible architecture search."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from architecture_search.search import main
if __name__ == '__main__':
    raise SystemExit(main())
