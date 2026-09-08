"""Provenance, process execution, and evidence-aware comparison."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temp.replace(path)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_identity(root: Path) -> dict:
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    files = git('ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    hashes = {}
    for name in sorted(set(files)):
        if not name:
            continue
        path = root / os.fsdecode(name)
        if path.is_file():
            hashes[os.fsdecode(name)] = file_hash(path)
        elif path.is_dir():
            hashes[os.fsdecode(name)] = source_identity(path)
        else:
            hashes[os.fsdecode(name)] = 'missing'
    return {'revision': git('rev-parse', 'HEAD').decode().strip(), 'source_hash': digest(hashes)}


def run(command: list[str], cwd: Path, log: Path, timeout: float) -> dict:
    if timeout <= 0:
        return {'returncode': 124, 'timed_out': True, 'seconds': 0, 'command': command}
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    timed_out = False
    with log.open('w') as out:
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            out.write(str(error))
            return {'returncode': 127, 'seconds': time.monotonic() - start, 'command': command}
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
    return {'returncode': code, 'timed_out': timed_out, 'seconds': time.monotonic() - start,
            'command': command, 'log': str(log)}


def metric_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def frontier(records: list[dict], objectives: dict[str, str], stage: str, target: dict,
             limits: dict | None = None) -> list[str]:
    """Call per workload. Missing objectives are ineligible, never interpreted as zero."""
    if not objectives or any(v not in ('min', 'max') for v in objectives.values()):
        raise ValueError('objectives require min/max directions')
    eligible = []
    for record in records:
        if record.get('correct') is not True or record.get('mode') != 'functional':
            continue
        evidence = record.get('evidence', {}).get(stage, {})
        if evidence.get('passed') is not True or evidence.get('target') != target:
            continue
        metrics = evidence.get('metrics', {})
        if any(not metric_number(metrics.get(k)) for k in objectives):
            continue
        if any(not metric_number(metrics.get(k)) or metrics[k] > v for k, v in (limits or {}).items()):
            continue
        eligible.append((record['id'], metrics))
    def dominates(a, b):
        pairs = [(a[k], b[k]) if d == 'min' else (-a[k], -b[k]) for k, d in objectives.items()]
        return all(x <= y for x, y in pairs) and any(x < y for x, y in pairs)
    return [key for key, values in eligible if not any(dominates(other, values) for k, other in eligible if k != key)]
