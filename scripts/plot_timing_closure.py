#!/usr/bin/env python3
"""Plot measured timing closure attempts in one registered-harness context."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);args=p.parse_args()
    result=json.loads((args.campaign/'results.json').read_text())
    manifest=json.loads((args.campaign/'manifest.json').read_text());target=manifest['target']
    rows=[r for r in result['attempts'] if r['stage']=='routed' and r['passed']]
    if not rows:raise ValueError('no completed routing measurements')
    fig,(timing,resources)=plt.subplots(1,2,figsize=(11,4.6))
    x=list(range(len(rows)))
    for delta,key,label,color in [(-.18,'setup_slack_ns','Setup','#0072B2'),(.18,'hold_slack_ns','Hold','#D55E00')]:
        timing.bar([i+delta for i in x],[r[key] for r in rows],width=.34,label=label,color=color)
    timing.axhline(0,color='black',linewidth=.8);timing.set_ylabel('Routed slack (ns); both must be nonnegative')
    timing.set_xticks(x,[r['profile']+'\n'+r['recipe'] for r in rows]);timing.legend()
    for r,i in zip(rows,x):
        if r['feasible']:timing.annotate('Qualified',(i,max(r['setup_slack_ns'],r['hold_slack_ns'])),xytext=(0,8),textcoords='offset points',ha='center',color='#00723B')
    for i,r in enumerate(rows):
        keys=['lut','ff','dsp','bram36','uram']
        budgets={k:target.get('resource_limits',{}).get(k,int(target['capacity'][k]*target['resource_fraction'])) for k in keys}
        resources.plot(keys,[100*r[k]/budgets[k] if budgets[k] else 0 for k in keys],marker='o',label=r['profile']+' / '+r['recipe'])
    resources.set_ylabel('Total harness resources (% of allowed budget)');resources.legend(fontsize=8)
    for ax in (timing,resources):ax.grid(axis='y',alpha=.25);ax.set_axisbelow(True)
    fig.suptitle('N=512 full × ternary Montgomery product: 250 MHz kernel harness')
    fig.tight_layout()
    for suffix in ('svg','png'):fig.savefig(args.campaign/('timing-closure.'+suffix),dpi=180,bbox_inches='tight')
    plt.close(fig)


if __name__=='__main__':main()
