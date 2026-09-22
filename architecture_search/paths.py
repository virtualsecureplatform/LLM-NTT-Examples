"""Repository-local generator defaults; external checkouts require an override."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NGEN = ROOT / 'third_party' / 'NGen'
SGEN = ROOT / 'third_party' / 'SGen'


def require_checkout(root: Path, name: str) -> None:
    if not (root / 'build.sbt').is_file():
        raise ValueError(f'{name} checkout missing at {root}; run git submodule update --init --recursive')
