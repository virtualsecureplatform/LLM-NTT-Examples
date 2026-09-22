"""Bounded research campaigns and explicit milestone evidence gates."""
from pathlib import Path
from . import release, product_backend
from .model import write_json, digest


def hardware_campaign(n, period=8):
    if n not in (16,64,256) or period not in (8,16):raise ValueError('unsupported research hardware point')
    campaign=release.campaign(n,hardware=True,period=period)
    campaign['budget'].update(hours=24)
    return campaign


def timing_repair_campaign():
    from . import products
    space={'generators':['ngen'],'ngen_backends':['fully-parallel'],'profiles':['baseline','split-barrett']}
    space['configurations']=products.candidates(products.workload(16),space)
    campaign=hardware_campaign(16,8)
    campaign.update(space=space,budget=dict(hours=12,functional=2,synthesis=2,route=2),route_selection='all')
    return campaign


def assurance_accept(report,campaign):
    result=release.accept(report,campaign);failed=[]
    for r in report.get('candidates',[]):
        if r.get('correct') and r['configuration']['generator']=='sgen':
            d=r.get('declared',{})
            if d.get('certificate',{}).get('schema')!='fft-arithmetic-certificate-v2' or not product_backend.qualification_valid(
                    campaign['workload'],d,Path(r.get('rtl_path',''))):failed.append(r['id'])
    return {**result,'passed':result['passed'] and not failed,'missing_layered_assurance':failed}


def freeze_search(out):
    """Freeze development decisions before any held-out hardware acquisition."""
    from . import product_search
    from .model import file_hash
    body=dict(schema='product-policy-freeze-v1',model_sha256=file_hash(Path(product_search.__file__)),
              development_sizes=[16,64],held_out_sizes=[256],policies=['enumerate','random','analytical','cost'],
              replay_budgets=[4,8,16],replay_seeds=list(range(20)),fresh_seeds=[0,1,2],
              fresh_budget=dict(synthesis=4,hours=6),objectives={'lut':'min','initiation_interval_cycles':'min'})
    result={**body,'freeze_sha256':digest(body)}
    path=out/'search-freeze.json'
    if path.exists():
        import json
        if json.loads(path.read_text())!=result:raise ValueError('search settings differ from frozen study')
    else:write_json(path,result)
    return result
