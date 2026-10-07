#!/usr/bin/env python3
"""Plot measured tradeoffs from the committed study CSV snapshots."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter


STYLES = {'NTT streamed': ('#0072B2', 'o'),
          'NTT stage-parallel': ('#D55E00', 's'),
          'FFT compact': ('#009E73', '^'),
          'FFT full-throughput': ('#CC79A7', 'D')}
WORKLOADS = ('full-full', 'full-byte', 'full-ternary')


def load(path):
    with path.open() as stream:
        rows = [r for r in csv.DictReader(stream) if r['status'] == 'screened']
    for r in rows:
        r['configuration'] = json.loads(r['configuration_json'])
        for k in ('quant_bits', 'max_abs_error', 'yosys_cells', 'initiation_interval_cycles'):
            r[k] = int(r[k])
        r['pareto'] = r['pareto'] == 'True'
    return rows


def family(row):
    c = row['configuration']
    return ('NTT ' if c['generator'] == 'ngen' else 'FFT ') + c['backend']


def save(fig, folder, name):
    svg = folder / (name + '.svg')
    fig.savefig(svg, bbox_inches='tight', metadata={'Date': None})
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    fig.savefig(folder / (name + '.png'), dpi=200, bbox_inches='tight')
    plt.close(fig)


def resource_plot(rows, n, output):
    workloads = [w for w in WORKLOADS if any(r['workload_name'] == w for r in rows)]
    fig, axes = plt.subplots(1, len(workloads), figsize=(5 * len(workloads), 4.6), squeeze=False, sharey=True)
    for ax, workload in zip(axes[0], workloads):
        subset = [r for r in rows if r['workload_name'] == workload]
        for name, (color, marker) in STYLES.items():
            points = [r for r in subset if family(r) == name]
            ax.scatter([r['yosys_cells'] for r in points],
                       [r['initiation_interval_cycles'] for r in points],
                       c=color, marker=marker, s=46, alpha=.7, edgecolors='white', linewidths=.4)
        pareto = [r for r in subset if r['pareto']]
        ax.scatter([r['yosys_cells'] for r in pareto],
                   [r['initiation_interval_cycles'] for r in pareto],
                   facecolors='none', edgecolors='#222222', marker='o', s=115, linewidths=1)
        ax.set(xscale='log', yscale='log', title=f'{workload} ({len(subset)} qualified)',
               xlabel='Generic Yosys cells (log scale)', ylabel='Cycles per product (log scale)')
        ax.grid(True, which='both', linewidth=.5, alpha=.25)
    handles = [Line2D([], [], color=color, marker=marker, linestyle='none', label=name)
               for name, (color, marker) in STYLES.items() if any(family(r) == name for r in rows)]
    handles.append(Line2D([], [], marker='o', markerfacecolor='none', markeredgecolor='#222222',
                          linestyle='none', label='Seven-objective Pareto point'))
    title = f'N={n}: resource / throughput tradeoff'
    fig.suptitle(title + ('\nLower and left are better' if n == 32 else ' — lower and left are better'), fontsize=13)
    fig.legend(handles=handles, loc='lower center', ncol=2 if n == 32 else len(handles), frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, .14 if n == 32 else .10, 1, .92))
    save(fig, output, f'torus{n}-resource-throughput')


def omission_plot(rows, output):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    legend = {}
    for ax, workload in zip(axes, WORKLOADS):
        points = [r for r in rows if r['workload_name'] == workload
                  and r['configuration']['generator'] == 'sgen'
                  and r['configuration']['fractional_bits'] == 30 and r['quant_bits'] == 0]
        groups = {}
        for r in points:
            c = r['configuration']
            groups.setdefault((c['backend'],c['lanes'],c['guard_bits']),[]).append(r)
        for (backend, lanes, guard), group in groups.items():
            group.sort(key=lambda r:r['configuration'].get('omit_low_diagonals',0))
            color, marker = STYLES['FFT ' + backend]
            label = f'{backend}, L{lanes}, g{guard}'
            line, = ax.plot([r['max_abs_error'] for r in group],
                            [r['initiation_interval_cycles'] for r in group],
                            color=color, marker=marker, linestyle='--' if lanes==4 else '-', linewidth=1.5)
            legend[label] = line
        ax.set_yscale('log')
        ax.set_xscale('symlog', linthresh=8)
        ax.set_xticks([0, 1e2, 1e4, 1e6], ['0', r'$10^2$', r'$10^4$', r'$10^6$'])
        ax.set(title=workload, xlabel='Analytical error bound (torus units; symlog)',
               ylabel='Cycles per product (log scale)')
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:,.0f}'))
        ax.set_ylim(min(r['initiation_interval_cycles'] for r in points) * .92,
                    max(r['initiation_interval_cycles'] for r in points) * 1.12)
        ax.set_xlim(-1, max(r['max_abs_error'] for r in points) * 25)
        ax.grid(True, which='both', linewidth=.5, alpha=.25)
    fig.suptitle('N=512 FFT, f30: accepting bounded error reduces product interval', fontsize=13)
    fig.legend(list(legend.values()),list(legend),loc='lower center',ncol=len(legend),frameon=False,fontsize=9)
    fig.tight_layout(rect=(0, .10, 1, .92))
    save(fig, output, 'torus512-error-throughput')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', type=Path, default=Path('docs/results'))
    args = parser.parse_args()
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none',
                         'svg.hashsalt': 'polynomial-study-v1'})
    for n in (512, 32):
        rows = load(args.results_dir / f'torus{n}-points.csv')
        resource_plot(rows, n, args.results_dir)
        if n == 512:
            omission_plot(rows, args.results_dir)
