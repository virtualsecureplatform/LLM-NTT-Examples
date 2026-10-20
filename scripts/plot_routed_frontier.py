#!/usr/bin/env python3
"""Plot only routed 250 MHz feasible products, marking the full Pareto set."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);args=p.parse_args()
    with (args.campaign/'points.csv').open() as stream:rows=[r for r in csv.DictReader(stream) if r['feasible']=='True']
    if not rows:raise ValueError('no routed timing-qualified products')
    fig,axes=plt.subplots(1,2,figsize=(11,4.8),sharey=True)
    for ax,key,title in zip(axes,('lut','dsp'),('Routed LUTs','Routed DSPs')):
        for r in rows:
            label=('pipelined' if r['profile']=='pipelined' else 'registered')+f" L{r['lanes']} PE{r['pe']}"
            ax.scatter(float(r[key]),float(r['modeled_products_per_second']),s=55,label=label,marker='o' if r['profile']=='pipelined' else 's')
            if r['pareto']=='True':ax.scatter(float(r[key]),float(r['modeled_products_per_second']),s=125,facecolors='none',edgecolors='black',linewidths=1)
        ax.set_xlabel(title);ax.grid(alpha=.25);ax.set_axisbelow(True)
    axes[0].set_ylabel('Modeled products/s at routed 250 MHz')
    axes[1].legend(fontsize=8)
    fig.suptitle('N=512 full × ternary: routed 250 MHz feasible designs\nRings mark the complete resource/error/latency/throughput Pareto set')
    fig.tight_layout()
    for ext in ('svg','png'):
        path=args.campaign/('frontier.'+ext)
        fig.savefig(path,dpi=180,bbox_inches='tight',metadata={'Date':None} if ext=='svg' else None)
        if ext=='svg':path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
    plt.close(fig)


if __name__=='__main__':main()
