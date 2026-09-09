"""Bounded configuration ranking. LLM output can only reorder legal candidates."""
from __future__ import annotations
import json
import os
import urllib.request
from .model import canonical, digest, write_json, metric_number
from . import cost


def feedback(configurations: list[dict], settings: dict) -> dict:
    """Expose observed feasibility and advisory estimates, never hidden outcomes."""
    limits=settings.get('resource_limits',{})
    observations=[];samples=[]
    for row in settings.get('observations',[]):
        measured=row.get('correct') is True and row.get('implementation_passed') is True
        metrics=row.get('metrics',{}) if measured else {}
        missing=[k for k in limits if not metric_number(metrics.get(k))]
        exceeded={k:{'measured':metrics[k],'limit':cap} for k,cap in limits.items()
                  if metric_number(metrics.get(k)) and metrics[k]>cap}
        observations.append({**row,'metrics':metrics,'resource_feasible':not exceeded if measured and not missing else None,
                             'exceeded_limits':exceeded,'missing_resource_metrics':missing})
        if measured:samples.append({'configuration':row['configuration'],'metrics':metrics})
    advisory={}
    family=('generator','backend','reduction','profile','transpose','radix','lanes','boundary')
    for config in configurations:
        matching=[r for r in samples if all(r['configuration'].get(k)==config.get(k) for k in family)]
        estimates={}
        for metric,cap in limits.items():
            estimate=cost.predict(matching,config,metric,'structural')
            if not estimate.get('available') and metric in ('lut','ff','dsp'):
                # Cold-start extrapolation exposes replication risk. It is not a
                # lower bound: shared resources and mapping can break scaling.
                points=[r for r in matching if metric_number(r['metrics'].get(metric))]
                if points:
                    nearest=min(points,key=lambda r:cost.distance(r['configuration'],config))
                    old=nearest['configuration'];scale=(config.get('pe',1)*config.get('stage_groups',1))/(old.get('pe',1)*old.get('stage_groups',1))
                    estimate={'available':True,'estimate':nearest['metrics'][metric]*scale,'method':'replication heuristic','samples':len(points)}
            if estimate.get('available'):
                estimates[metric]={**estimate,'limit':cap,'estimated_over_limit':estimate['estimate']>cap}
        advisory[digest(config)[:16]]={'resource_estimates':estimates,'physical_pe_count':config.get('pe',1)*config.get('stage_groups',1)}
    return {'observations':observations,'candidate_advice':advisory,
            'estimate_limitation':'Advisory extrapolations from this trial only, not measurements or safe pruning bounds. Unknown does not mean zero. All legal candidates remain available.'}


def rank(configurations: list[dict], workload: dict, settings: dict, directory, timeout=60) -> list[dict]:
    endpoint=settings.get('endpoint','http://kunashiri.sato.lab:8080/v1').rstrip('/')
    headers={'Content-Type':'application/json'}
    key=os.environ.get(settings.get('api_key_env','NTT_LLM_API_KEY'))
    if key:
        headers['Authorization']='Bearer '+key
    model=settings.get('model')
    if not model:
        request=urllib.request.Request(endpoint+'/models',headers=headers)
        with urllib.request.urlopen(request,timeout=timeout) as response:
            model=json.load(response)['data'][0]['id']
    indexed={digest(c)[:16]:c for c in configurations}
    context=feedback(configurations,settings)
    request_body={'model':model,'temperature':0,'max_tokens':1024,'chat_template_kwargs':{'enable_thinking':False},'messages':[
        {'role':'system','content':'Rank legal FPGA NTT configurations to discover resource-feasible Pareto tradeoffs within the remaining evaluation budget. Resource caps are mandatory for a useful discovery: correctness and timing alone are insufficient. Prioritize likely feasible designs before speculative high-parallelism designs. With no observations, establish a small implementation as a calibration anchor. With observations, expand gradually using measured resource headroom, exceeded-limit feedback and advisory estimates; do not repeat a failed resource strategy just to maximize throughput. PE and stage_groups multiply physical replication. Estimates are uncertain and must not prune candidates. Return only a JSON object with an ordered list of candidate IDs in "order". Never invent configurations or report predicted metrics as measurements.'},
        {'role':'user','content':canonical({'workload':workload,'target':settings.get('target',{}),'resource_limits':settings.get('resource_limits',{}),'objectives':settings.get('objectives',{}),'requirements':settings.get('requirements',{}),'bandwidth':settings.get('bandwidth',{}),'evaluations_remaining':settings.get('evaluations_remaining'),'candidates':indexed,**context})}]}
    write_json(directory/'llm-request.json',request_body)
    request=urllib.request.Request(endpoint+'/chat/completions',data=json.dumps(request_body).encode(),headers=headers)
    with urllib.request.urlopen(request,timeout=timeout) as response:
        raw=json.load(response)
    write_json(directory/'llm-response.json',raw)
    text=raw['choices'][0]['message']['content'].strip()
    if text.startswith('```'):
        text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    order=json.loads(text)['order']
    if not isinstance(order,list) or any(not isinstance(i,str) or i not in indexed for i in order) or len(order)!=len(set(order)):
        raise ValueError('LLM returned unknown or duplicate candidate IDs')
    # Unmentioned legal choices remain available. No shell, code, or metric output is accepted.
    return [indexed[i] for i in order]+[c for i,c in indexed.items() if i not in order]
