"""Bounded configuration ranking. LLM output can only reorder legal candidates."""
from __future__ import annotations
import json
import os
import urllib.request
from .model import canonical, digest, write_json


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
    request_body={'model':model,'temperature':0,'max_tokens':1024,'chat_template_kwargs':{'enable_thinking':False},'messages':[
        {'role':'system','content':'Rank legal FPGA NTT configurations for exploration of latency, throughput, and resource tradeoffs. Return only a JSON object with an ordered list of candidate IDs in "order". Never invent configurations or report predicted metrics as measurements.'},
        {'role':'user','content':canonical({'workload':workload,'target':settings.get('target',{}),'candidates':indexed})}]}
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
