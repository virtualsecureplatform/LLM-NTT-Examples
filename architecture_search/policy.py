"""Bounded configuration ranking. LLM output can only reorder legal candidates."""
from __future__ import annotations
import json
import os
import time
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
    if not configurations:
        raise ValueError('LLM acquisition requires legal candidates')
    deadline=time.monotonic()+timeout
    def remaining():
        value=deadline-time.monotonic()
        if value<=0:raise TimeoutError('LLM acquisition time budget exhausted')
        return value
    endpoint=settings.get('endpoint','http://kunashiri.sato.lab:8080/v1').rstrip('/')
    headers={'Content-Type':'application/json'}
    key=os.environ.get(settings.get('api_key_env','NTT_LLM_API_KEY'))
    if key:
        headers['Authorization']='Bearer '+key
    model=settings.get('model')
    if not model:
        request=urllib.request.Request(endpoint+'/models',headers=headers)
        with urllib.request.urlopen(request,timeout=remaining()) as response:
            model=json.load(response)['data'][0]['id']
    indexed={digest(c)[:16]:c for c in configurations}
    count=settings.get('rank_count',len(indexed))
    if not isinstance(count,int) or isinstance(count,bool) or not 1<=count<=len(indexed):
        raise ValueError('rank_count must be within the legal candidate count')
    context=feedback(configurations,settings)
    request_body={'model':model,'temperature':0,'max_tokens':1024,'chat_template_kwargs':{'enable_thinking':False},'messages':[
        {'role':'system','content':'Rank legal FPGA NTT configurations to discover resource-feasible Pareto tradeoffs within the remaining evaluation budget. Resource caps are mandatory for a useful discovery: correctness and timing alone are insufficient. Prioritize likely feasible designs before speculative high-parallelism designs. With no observations, establish a small implementation as a calibration anchor. With observations, expand gradually using measured resource headroom, exceeded-limit feedback and advisory estimates; do not repeat a failed resource strategy just to maximize throughput. PE and stage_groups multiply physical replication. Estimates are uncertain and must not prune candidates. Return only a JSON object with an ordered list of candidate IDs in "order". Never invent configurations or report predicted metrics as measurements.'},
        {'role':'user','content':canonical({'workload':workload,'target':settings.get('target',{}),'resource_limits':settings.get('resource_limits',{}),'objectives':settings.get('objectives',{}),'requirements':settings.get('requirements',{}),'bandwidth':settings.get('bandwidth',{}),'evaluations_remaining':settings.get('evaluations_remaining'),'candidates':indexed,**context})}]}
    request_body['messages'][0]['content'] += f' Return exactly {count} distinct candidate IDs, best first. Do not list other candidates.'
    request_body['response_format']={'type':'json_schema','json_schema':{
        'name':'candidate_ranking','strict':True,'schema':{
            'type':'object','properties':{'order':{'type':'array','items':{'type':'string','enum':list(indexed)},
                                                   'minItems':count,'maxItems':count}},
            'required':['order'],'additionalProperties':False}}}
    errors=[]
    for attempt in range(2):
        write_json(directory/f'llm-request-attempt-{attempt+1}.json',request_body)
        if attempt==0:write_json(directory/'llm-request.json',request_body)
        request=urllib.request.Request(endpoint+'/chat/completions',data=json.dumps(request_body).encode(),headers=headers)
        with urllib.request.urlopen(request,timeout=remaining()) as response:
            raw=json.load(response)
        write_json(directory/f'llm-response-attempt-{attempt+1}.json',raw)
        if attempt==0:write_json(directory/'llm-response.json',raw)
        try:
            choice=raw['choices'][0]
            if choice.get('finish_reason') not in (None,'stop'):
                raise ValueError('LLM response did not finish normally')
            text=choice['message']['content'].strip()
            if text.startswith('```'):
                text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
            payload=json.loads(text)
            if not isinstance(payload,dict) or set(payload)!={'order'}:
                raise ValueError('LLM response must contain only order')
            order=payload['order']
            if not isinstance(order,list) or len(order)!=count:
                raise ValueError(f'LLM must return exactly {count} candidate IDs')
            if any(not isinstance(i,str) or i not in indexed for i in order):
                raise ValueError('LLM returned unknown candidate IDs')
            if len(order)!=len(set(order)):
                raise ValueError('LLM returned duplicate candidate IDs')
        except (ValueError,KeyError,TypeError,AttributeError,IndexError) as error:
            errors.append(str(error))
            write_json(directory/'llm-validation.json',{'accepted':False,'attempts':attempt+1,'errors':errors})
            if attempt==1:raise ValueError('LLM acquisition invalid after two attempts: '+str(error)) from error
            request_body['messages'].append({'role':'user','content':
                f'Your response failed validation: {error}. Return exactly {count} distinct IDs from candidates, using the required JSON schema.'})
            continue
        write_json(directory/'llm-validation.json',{'accepted':True,'attempts':attempt+1,'errors':errors,'selected_ids':order})
        # Only validated legal choices lead; omitted candidates retain their original order.
        return [indexed[i] for i in order]+[c for i,c in indexed.items() if i not in order]
