"""Compile once and check complete product corpora in bounded simulator shards."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import time
from . import product_evaluate
from .model import digest, file_hash, write_json


def compile_simulator(w, c, rtl, directory, timeout, corpus, oracle, optimization='-O3'):
    directory = directory.resolve()
    result = product_evaluate.evaluate(w, c, rtl, directory, timeout, 'verilator',
        _corpus=corpus, _first_pass=0, _end_pass=4, _output_oracle=oracle,
        _compile_only=True, _optimization=optimization)
    if result['build']['returncode']:
        return result, None
    executable = directory / 'obj_dir/Vtest'
    bench = directory / 'test.sv'
    bundle = dict(workload_sha256=digest(w), configuration_sha256=digest(c),
                  rtl_sha256=file_hash(rtl), max_frames=len(corpus), optimization=optimization,
                  executable=str(executable), executable_sha256=file_hash(executable),
                  testbench=str(bench), testbench_sha256=file_hash(bench))
    write_json(directory / 'compiled.json', bundle)
    return result, bundle


def protocol_tasks(corpus, shard_size):
    """Keep all 64 bubble frames and eight frames for each stalled/reset pass."""
    prefix = corpus[:64]
    tasks = []
    # Put each original stalled/reset frame first in a shard, and distribute
    # the remaining bubble frames without dropping or duplicating any.
    size = min(4, shard_size)
    reset_count = min(8, len(prefix))
    cursor = reset_count
    for i in range(reset_count):
        tail = prefix[cursor:cursor + size - 1]
        cursor += len(tail)
        frames = [prefix[i], *tail]
        args = ('+steady_frames=1', '+bubble_frames=' + str(len(frames)), '+stall_frames=1')
        tasks.append((f'protocol-{len(tasks):03d}', frames, 0, 4, args))
    for start in range(cursor, len(prefix), size):
        frames = prefix[start:start + size]
        tasks.append((f'protocol-{len(tasks):03d}', frames, 1, 2,
                      ('+bubble_frames=' + str(len(frames)),)))
    return tasks


def reusable_shard(result, frames, first, last, args, compiled):
    return (result.get('correct') and result.get('compiled_signature') == digest(compiled)
            and result.get('corpus_sha256') == digest(frames)
            and result.get('pass_range') == [first, last]
            and result.get('runtime_args') == list(args)
            and bool(result.get('verification'))
            and all(Path(p).is_file() and file_hash(Path(p)) == h
                    for p, h in result['verification'].items()))


def evaluate_shards(w, c, rtl, directory, timeout, corpus, oracle, compiled,
                    workers=16, shard_size=4, protocol=False):
    """A single stage wall limit includes all queued and running shards."""
    if workers < 1 or shard_size < 1 or shard_size > compiled['max_frames']:
        raise ValueError('invalid simulator shard limits')
    directory = directory.resolve(); directory.mkdir(parents=True, exist_ok=True)
    tasks = protocol_tasks(corpus, shard_size) if protocol else [
        (f'corpus-{i // shard_size:03d}', corpus[i:i + shard_size], 0, 1, ())
        for i in range(0, len(corpus), shard_size)]
    if not tasks:
        raise ValueError('empty simulator shard corpus')
    started = time.monotonic()
    def check(task):
        name, frames, first, last, args = task
        target = directory / name
        previous = target / 'results.json'
        if previous.is_file():
            try:
                result = json.loads(previous.read_text())
                if reusable_shard(result, frames, first, last, args, compiled):
                    return name, {**result, 'resumed': True}
            except (OSError, ValueError, KeyError, TypeError):
                pass
        remaining = max(0, timeout - (time.monotonic() - started))
        print(f'  {directory.name}/{name}: {len(frames)} frames', flush=True)
        result = product_evaluate.evaluate(w, c, rtl, target, remaining, 'verilator',
            _corpus=frames, _first_pass=first, _end_pass=last, _output_oracle=oracle,
            _compiled=compiled, _runtime_args=args)
        return name, result
    with ThreadPoolExecutor(max_workers=min(workers, len(tasks))) as pool:
        checked = dict(pool.map(check, tasks))
    correct = all(r['correct'] for r in checked.values())
    verification = {p: h for r in checked.values() for p, h in r['verification'].items()}
    used_corpus = corpus[:64] if protocol else corpus
    completed = sum(len(frames) for name, frames, _, _, _ in tasks if checked[name]['correct'])
    result = dict(correct=correct, mode='compiled-protocol-shards' if protocol else 'compiled-corpus-shards',
        inputs_unchanged=all(r['inputs_unchanged'] for r in checked.values()),
        corpus_sha256=digest(used_corpus), requested_frames=len(used_corpus), checked_frames=completed,
        metrics={} if protocol else {'completed_products': completed},
        build={'returncode': 0, 'mode': 'shared-compiled-simulator'},
        test={'returncode': 0 if correct else 1,
              'timed_out': any(r.get('test', {}).get('timed_out', False) for r in checked.values())},
        compiled_signature=digest(compiled), verification=verification, shards=checked,
        shard_size=shard_size, workers=min(workers, len(tasks)), wall_seconds=time.monotonic() - started,
        oracle='independent-python-integer-schoolbook')
    write_json(directory / 'results.json', result)
    return result
