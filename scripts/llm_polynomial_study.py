#!/usr/bin/env python3
"""Replay or run a small adaptive N512 polynomial multiplication search."""
import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from architecture_search import device, llm_dse
from architecture_search.model import digest, file_hash, write_json


def qualify(request_file):
    """Container worker: use the unchanged full product-screening procedure."""
    from architecture_search.build_identity import verify
    from architecture_search.paths import NGEN
    from scripts.polynomial_study import corpus, screen
    request = json.loads(request_file.read_text())
    row, out = request['row'], Path(request['output_dir'])
    out.mkdir(parents=True, exist_ok=True)
    generator = verify(NGEN)
    if not generator['verified']:
        raise ValueError('unverified NGen assembly')
    manifest = dict(schema='llm-qualification-v1', generators={'ngen': generator},
        image_sha256=os.environ.get('FHE512_IMAGE_SHA256'),
        corpora={'full-ternary': digest(corpus(row['workload']))},
        sources={str(p.relative_to(ROOT)): file_hash(p) for p in [
            *sorted((ROOT/'architecture_search').glob('*.py')), ROOT/'scripts/polynomial_study.py',
            Path(__file__), ROOT/'scripts/fhe512_preroute.py', ROOT/'scripts/fhe512_sgen_precision.py']})
    write_json(out/'manifest.json', manifest)
    screen(row, out, request['timeout'], 'verilator')
    row['evidence_root'] = str(out)
    row['rtl_path'] = str(out/row['name']/'SearchTop.sv')
    write_json(out/'row.json', row)
    return 0


def report(out, states, target, mode):
    from scripts.extend_timing_frontier import nondominated
    out = Path(out)
    summaries, all_points = [], []
    for state in states:
        points = llm_dse.feasible_points(state, target)
        full = nondominated(points)
        calls = []
        for path in sorted((out/state['policy']/'llm').glob('selection-*/call-*.json')):
            calls.append(json.loads(path.read_text()))
        summary = dict(policy=state['policy'], status=state['status'], **state['progress'],
            physical_qualified=sum(h['stage']=='qualified' and not h['cache_hit'] for h in state['history']),
            physical_mapped=sum(h['stage']=='mapped' and not h['cache_hit'] for h in state['history']),
            physical_routed=sum(h['stage']=='routed' and not h['cache_hit'] for h in state['history']),
            cache_hits=sum(h['cache_hit'] for h in state['history']),
            failures=sum(not h['passed'] or (h['stage']=='routed' and not h['feasible']) for h in state['history']),
            physical_seconds=sum(h['physical_seconds'] for h in state['history']),
            hardware_seconds=sum(h['hardware_seconds'] for h in state['history']),
            llm_requests=len(calls), llm_seconds=sum(c.get('seconds', 0) for c in calls),
            llm_tokens=sum(c.get('response', {}).get('usage', {}).get('total_tokens', 0) or 0 for c in calls),
            full_objective_frontier=full)
        summaries.append(summary)
        all_points.extend(dict(policy=state['policy'], pareto=p['name'] in summary['frontier'],
            full_objective_pareto=p['name'] in full,
            configuration=state['observations'][p['name']]['qualified']['row']['configuration'],
            rtl_sha256=state['observations'][p['name']]['qualified']['row']['rtl_sha256'], **p) for p in points)
    write_json(out/'comparison.json', dict(schema='llm-dse-comparison-v1', mode=mode,
        limitation='Exploratory single-seed comparison; replay uses only five existing measured points. '
        'No full-grid recall or demonstrated search-reduction claim.', target=target,
        policies=summaries, points=all_points, runs=[dict(policy=s['policy'],
            manifest=json.loads((out/s['policy']/'manifest.json').read_text()),
            results=str((out/s['policy']/'results.json').resolve()),
            results_sha256=file_hash(out/s['policy']/'results.json'),
            transcripts={str(p.relative_to(out)): file_hash(p) for p in sorted(
                (out/s['policy']/'llm').glob('selection-*/call-*.json'))}) for s in states]))
    for filename, rows in [('comparison.csv', summaries), ('points.csv', all_points)]:
        if rows:
            with (out/filename).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, list(rows[0]), lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
    lines = ['# LLM-guided polynomial multiplication DSE', '',
        f'Mode: **{mode}**. Exact N=512 full32 × ternary products modulo 2^32; '
        'U280, registered harness v2, Default implementation, 250 MHz. '
        'Each policy receives the same passing seed as disclosed prior evidence.', '',
        '| Policy | Status | New candidates | Maps | Routes | Feasible incl. seed | Best modeled products/s | Hypervolume | New physical maps/routes |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for s in summaries:
        lines.append(f"| {s['policy']} | {s['status']} | {s['candidates']} | {s['mapped']} | {s['routed']} | "
            f"{s['feasible']} | {s['best_products_per_second']:.1f} | {s['hypervolume']:.4f} | "
            f"{s['physical_mapped']}/{s['physical_routed']} |")
    lines += ['', '| Policy | Achieved design | LUT | FF | DSP | BRAM36 | Modeled products/s | Setup ns | Hold ns |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for p in all_points:
        c = p['configuration']
        label = f"{c['product_profile']} {c['reduction']} L{c['lanes']} PE{c['pe']}"
        lines.append(f"| {p['policy']} | {label} | {p['lut']:g} | {p['ff']:g} | {p['dsp']:g} | "
            f"{p['bram36']:g} | {p['modeled_products_per_second']:.1f} | "
            f"{p['setup_slack_ns']:g} | {p['hold_slack_ns']:g} |")
    lines += ['', 'Hypervolume minimizes LUT and maximizes modeled throughput; fixed reference is the '
        'target LUT limit and zero throughput, normalized by LUT limit × common-seed throughput. '
        'Cache hits consume logical budgets. Physical execution counts depend on shared-cache reuse and policy order.', '',
        'This is an exploratory single-seed demonstration, not evidence of a statistically established search advantage. '
        'Replay is a closed five-design integration fixture; no complete 24-design reference frontier was measured. '
        'Products/s are modeled from qualified cycles and the bandwidth assumption, not board measurements.', '',
        '[Comparison CSV](comparison.csv) · [Point CSV](points.csv) · [Provenance and metrics](comparison.json)', '',
        '![Area and search progress](comparison.svg)', '']
    (out/'summary.md').write_text('\n'.join(lines))


def plot(out, states, target):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4))
    for state in states:
        policy = state['policy']
        points = llm_dse.feasible_points(state, target)
        names = set(llm_dse.frontier(points))
        line = axes[0].scatter([p['lut'] for p in points],
                              [p['modeled_products_per_second']/1000 for p in points], label=policy, alpha=.65)
        selected = sorted((p for p in points if p['name'] in names), key=lambda p: p['lut'])
        axes[0].plot([p['lut'] for p in selected], [p['modeled_products_per_second']/1000 for p in selected],
                     color=line.get_facecolor()[0], alpha=.6)
        seed_obs = {state['seed_name']: state['observations'][state['seed_name']]}
        initial = dict(state, observations=seed_obs, selected=[], attempts=dict(qualified=0, mapped=0, routed=0))
        trace = [llm_dse.progress(initial, target), *[h['progress'] for h in state['history']]]
        for ax, x in zip(axes[1:], ('candidates', 'routed')):
            ax.step([p[x] for p in trace], [p['hypervolume'] for p in trace], where='post', label=policy)
    axes[0].set(xlabel='Routed LUTs', ylabel='Modeled products/s (thousands)')
    axes[1].set(xlabel='New candidate attempts', ylabel='Normalized LUT/throughput hypervolume')
    axes[2].set(xlabel='Logical routing attempts', ylabel='Normalized LUT/throughput hypervolume')
    for ax in axes:
        ax.grid(alpha=.25)
        ax.legend(fontsize=8)
    fig.suptitle('Exact N512 products: routed 250 MHz frontier and budgeted search progress\n'
                 'Common disclosed seed; exploratory comparison')
    fig.tight_layout()
    for ext in ('svg', 'png'):
        path = Path(out)/('comparison.'+ext)
        fig.savefig(path, dpi=160, bbox_inches='tight', metadata={'Date': None} if ext == 'svg' else None)
        if ext == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, default=ROOT/'studies/torus512-llm-demo.json')
    parser.add_argument('--target', type=Path, default=ROOT/'studies/u280-kernel-harness.json')
    parser.add_argument('--reference', type=Path, default=ROOT/'build/device-pareto250-512')
    parser.add_argument('--cache-dir', type=Path, default=ROOT/'build/llm-dse-cache')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--mode', choices=['replay', 'live'], default='replay')
    parser.add_argument('--policy', choices=['llm', 'random', 'analytical', 'compare'], default='compare')
    parser.add_argument('--max-candidates', type=int, default=4)
    parser.add_argument('--route-budget', type=int, default=2)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--timeout', type=int, default=3600)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--base-url', default=os.environ.get('LLM_DSE_BASE_URL', llm_dse.BASE_URL))
    parser.add_argument('--model', default=os.environ.get('LLM_DSE_MODEL', llm_dse.MODEL))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--plot-only', action='store_true')
    parser.add_argument('--qualify-request', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    lock = None
    try:
        if args.qualify_request:
            return qualify(args.qualify_request)
        if args.status or args.plot_only:
            if args.output_dir is None:
                raise ValueError('--output-dir is required')
            states = [json.loads(p.read_text()) for p in sorted(args.output_dir.glob('*/results.json'))]
            if args.plot_only:
                plot(args.output_dir, states, device.load_target(args.target))
            else:
                snapshots = [{k: s.get(k) for k in ('policy', 'status', 'active', 'attempts', 'progress', 'error')}
                             for s in states]
                for s in snapshots:
                    if s['active']:
                        s['active']['elapsed_seconds'] = max(0, time.time()-s['active']['started_at'])
                print(json.dumps(snapshots, indent=2))
            return 0
        rows = llm_dse.catalog(json.loads(args.spec.read_text()))
        target = device.load_target(args.target)
        from architecture_search.llm_evaluate import EvaluationStore, require_target
        require_target(target)
        if args.max_candidates < 1 or not 0 <= args.route_budget <= args.max_candidates//2 \
                or args.timeout <= 0 or not 1 <= args.threads <= 32:
            raise ValueError('invalid candidate, routing, timeout, or thread budget')
        if args.mode == 'replay':
            reference = json.loads((args.reference/'results.json').read_text())
            rows = [r for r in rows if r['name'] in reference['routed']]
        if args.dry_run:
            print(json.dumps(dict(mode=args.mode, candidates=len(rows), seed=llm_dse.seed_name(rows),
                max_candidates=args.max_candidates, route_budget=args.route_budget,
                policies=['llm', 'random', 'analytical'] if args.policy == 'compare' else [args.policy],
                catalog=rows), indent=2))
            return 0
        if args.output_dir is None:
            raise ValueError('--output-dir is required')
        client = llm_dse.LLMClient(args.base_url, args.model) if args.policy in ('llm', 'compare') else None
        # Keep the credential in the HTTP client only; hardware workers inherit no key.
        os.environ.pop('LLM_DSE_API_KEY', None)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        lock = (args.output_dir/'.lock').open('w')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = EvaluationStore(rows, target, args.cache_dir, args.mode, args.reference, args.timeout, args.threads)
        policies = ['llm', 'random', 'analytical'] if args.policy == 'compare' else [args.policy]
        states = []
        settings = dict(base_url=args.base_url, model=args.model) if client else {}
        for policy in policies:
            try:
                state = llm_dse.run_search(rows, target, store, args.output_dir/policy, policy,
                    args.seed, args.max_candidates, args.route_budget, client, args.resume, settings)
                states.append(state)
            except llm_dse.LLMAuthenticationError:
                raise
            except llm_dse.LLMError:
                # Preserve a visible failed LLM run and still complete the independent baselines.
                states.append(json.loads((args.output_dir/policy/'results.json').read_text()))
            report(args.output_dir, states, target, args.mode)
        try:
            plot(args.output_dir, states, target)
        except ImportError:
            print('Plots pending: use --plot-only with scripts/polynomial-report-requirements.txt installed.', flush=True)
        print(f'Completed {args.mode} comparison: '+', '.join(
            s['policy']+'='+s['status'] for s in states), flush=True)
        return 0 if all(s['status'] == 'complete' for s in states) else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    finally:
        if lock is not None:
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
