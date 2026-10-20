#!/usr/bin/env python3
"""Plot routed resources and search progress; compare only compatible campaigns."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,action='append',required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    runs=[];reference=None
    for folder in args.campaign:
        manifest=json.loads((folder/'manifest.json').read_text())
        compatible={k:manifest[k] for k in ('target','sources','plan','error_limit','tool')}
        if reference is not None and compatible!=reference:
            p.error('comparison requires identical pool, warmup, budgets, device, and error constraint')
        reference=compatible
        runs.append((folder.name,json.loads((folder/'results.json').read_text())))
    args.output_dir.mkdir(parents=True,exist_ok=True)
    workloads=sorted(runs[0][1]['frontiers'])
    for axis_key,label,name in [('evaluation_count','Mapped + routed evaluations','evaluation-progress'),
                                ('elapsed_seconds','Wall time (seconds)','wall-progress')]:
        fig,axes=plt.subplots(1,len(workloads),figsize=(max(7,5*len(workloads)),4),squeeze=False)
        for ax,workload in zip(axes[0],workloads):
            for run_name,data in runs:
                history=data['history']
                rates=[h.get('best_feasible_rates',{}).get(workload) for h in history]
                ax.step([h[axis_key] for h in history],[r if r is not None else 0 for r in rates],where='post',
                        label=f'{data["policy"]}, seed {data["seed"]} ({run_name})')
            ax.set(title=workload,xlabel=label,ylabel='Best routed-feasible modeled products/s')
            ax.set_ylim(bottom=0)
            if not any(h.get('best_feasible_rates',{}).get(workload) for _,d in runs for h in d['history']):
                ax.set_ylim(0,1)
                ax.text(.5,.5,'No timing-qualified result',ha='center',transform=ax.transAxes)
            ax.grid(alpha=.25);ax.legend(fontsize=7)
        fig.suptitle('Search progress\nZero = no routed feasible design found yet')
        fig.tight_layout(rect=(0,0,1,.9))
        for extension in ('png','svg'):fig.savefig(args.output_dir/f'{name}.{extension}',bbox_inches='tight',dpi=180)
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4.5))
    for run_name,data in runs:
        for workload in workloads:
            # Rates are stored per point in the CSV, avoiding access to hidden pool measurements.
            import csv
            folder=next(f for f in args.campaign if f.name==run_name)
            with (folder/'points.csv').open() as stream:
                rows=[r for r in csv.DictReader(stream) if r['feasible']=='True' and r['workload']==workload]
            if rows:
                ax.scatter([float(r['lut']) for r in rows],[float(r['modeled_products_per_second']) for r in rows],
                           label=f'{data["policy"]}: {workload}')
    ax.set(xlabel='Routed LUTs',ylabel='Modeled products/s at a timing-qualified clock',
           title='Routed feasible products: resource / throughput tradeoff')
    ax.grid(alpha=.25)
    if ax.has_data():ax.legend(fontsize=8)
    else:ax.text(.5,.5,'No routed feasible designs found',ha='center',transform=ax.transAxes)
    fig.tight_layout()
    for extension in ('png','svg'):fig.savefig(args.output_dir/f'resource-throughput.{extension}',bbox_inches='tight',dpi=180)
    plt.close(fig)


if __name__=='__main__':main()
