"""Persistent measurement index; missing or modified artifacts are cache misses."""
import json
from pathlib import Path
from .model import digest,evidence_integrity,write_json


def key(identity,workload,configuration,rtl_hash,target,stage,metrics,constraints):
    return dict(schema='product-measurement-cache-v1',identity=identity,workload=workload,
                configuration=configuration,rtl_sha256=rtl_hash,target=target,stage=stage,
                functional_metrics=metrics,constraints=constraints)


def get(root,identity):
    path=Path(root)/(digest(identity)+'.json')
    try:
        entry=json.loads(path.read_text())
        if entry['key']!=identity or entry['sha256']!=digest({'key':identity,'evidence':entry['evidence']}):return None
        if evidence_integrity(entry['evidence'])!='verified':return None
        return entry['evidence']
    except (ValueError,KeyError,TypeError,OSError):return None


def put(root,identity,evidence):
    if evidence_integrity(evidence)!='verified':return False
    if get(root,identity) is not None:return True
    body=dict(key=identity,evidence=evidence)
    write_json(Path(root)/(digest(identity)+'.json'),{**body,'sha256':digest(body)})
    return True
